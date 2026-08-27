# OpenConstructionERP - One-Line Installer for Windows
#
# Usage:
#   irm https://raw.githubusercontent.com/datadrivenconstruction/OpenConstructionERP/main/scripts/install.ps1 | iex
#
# What it does:
#   1. If Docker Desktop is running → runs via docker compose
#   2. If Python 3.12+ is installed → installs via pip
#   3. Otherwise → installs uv → installs via uv

# Native commands (uv, python, docker) write progress to stderr by design.
# In Windows PowerShell 5.1, `$ErrorActionPreference = "Stop"` combined with
# `irm | iex` execution turns every stderr line into a NativeCommandError
# terminating exception — so a successful "Resolved 64 packages in 1.28s"
# from uv aborts the script before the install actually runs (issue #87).
# We rely on explicit `$LASTEXITCODE` checks after every native call instead.
$ErrorActionPreference = "Continue"

# Belt-and-braces for users on PowerShell 7.3+: also disable native-command
# error preference so `& uv ...` never escalates stderr to a terminating error.
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$OE_VERSION = if ($env:OE_VERSION) { $env:OE_VERSION } else { "latest" }
$OE_INSTALL_DIR = if ($env:OE_INSTALL_DIR) { $env:OE_INSTALL_DIR } else { "$env:LOCALAPPDATA\OpenConstructionERP" }
$OE_PORT = if ($env:OE_PORT) { $env:OE_PORT } else { "8080" }
$OE_REPO = "https://github.com/datadrivenconstruction/OpenConstructionERP"

# Helper: run a native command, suppress PS's stderr-as-error wrapping,
# and check $LASTEXITCODE explicitly. Returns the merged stdout+stderr
# as a string array so the caller can log progress to the host.
function Invoke-Native {
    param(
        [Parameter(Mandatory)] [scriptblock] $Block,
        [Parameter(Mandatory)] [string]      $Description,
        [switch]                              $TolerateNonZero
    )
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Merge stderr into stdout so the script can keep running even when
        # the native command emits progress text. ForEach-Object unwraps
        # ErrorRecord objects so they print as plain text instead of being
        # surfaced as PS errors.
        & $Block 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.Exception.Message
            } else {
                Write-Host $_
            }
        }
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevPref
    }
    if ($exit -ne 0 -and -not $TolerateNonZero) {
        Write-Err "${Description}: exit code $exit"
        exit 1
    }
    return $exit
}

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Blue }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Add-ToUserPath($dir) {
    # Put $dir on the USER PATH so the command works in every new terminal.
    # Uses the registry-backed user environment via .NET rather than setx,
    # which silently truncates a PATH longer than 1024 characters. Idempotent,
    # and also updates the current session so the command works right away.
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    $parts = @($userPath -split ';' | Where-Object { $_ -ne "" })
    if ($parts -notcontains $dir) {
        $newPath = (@($parts) + $dir) -join ';'
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Ok "Added to PATH: $dir"
    }
    if (@($env:Path -split ';') -notcontains $dir) {
        $env:Path = "$env:Path;$dir"
    }
}

function Test-Docker {
    try {
        $null = & docker info 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-Python312 {
    # Must treat future major versions (Python 4.x) as satisfying "3.12+":
    # the naive ``$major -ge 3 -and $minor -ge 12`` fails for 4.0-4.11
    # because 4.0 < 3.12 component-wise. Use proper major/minor compare.
    try {
        $ver = & python --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            return ($major -gt 3) -or (($major -eq 3) -and ($minor -ge 12))
        }
        return $false
    } catch {
        return $false
    }
}

function Test-Uv {
    try {
        $null = & uv --version 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function New-ComposeSecret {
    # Windows has no openssl, so the bytes come from the OS cryptographic
    # generator through System.Security.Cryptography.RandomNumberGenerator and
    # are rendered as 64 hex characters. That is 256 bits, more than the 192
    # the POSIX installer takes from `openssl rand -base64 24`, and hex cannot
    # emit the "@" that would break the connection URL the stack builds from
    # the password: a URL splits its user info at the first "@", so a literal
    # one moves the rest of the password into the host.
    #
    # Create() rather than the newer Fill(), because Windows PowerShell 5.1
    # runs on .NET Framework, where Fill() does not exist.
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $bytes = [byte[]]::new(32)
        $rng.GetBytes($bytes)
        return ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
    } finally {
        $rng.Dispose()
    }
}

function Write-ComposeSecrets {
    # Write the two secrets the quickstart compose file will not start without.
    # It reads POSTGRES_PASSWORD and JWT_SECRET with compose's fail-fast form
    # on purpose, so that nobody runs a stack whose JWT signing key is shared
    # with every other reader of the file. Without a .env beside the compose
    # file, `docker compose up` stops on an interpolation error and starts
    # nothing, which is what this installer did for everyone who had Docker.
    #
    # The check is per key, not per file. A .env holding one of the two is a
    # state a reader reaches easily, since the recipe in the README is two
    # separate lines, and a plain "the file is there, leave it alone" test
    # would keep the install broken for them. A key that is already present is
    # never rewritten: the password in it is the one PostgreSQL initialised its
    # data directory with, and generating a new one would lock the user out of
    # their own data.
    param([Parameter(Mandatory)] [string] $Path)

    $existing = @()
    if (Test-Path $Path) {
        $existing = @(Get-Content -Path $Path)
    }

    $missing = @()
    foreach ($key in @("POSTGRES_PASSWORD", "JWT_SECRET")) {
        if (-not ($existing | Where-Object { $_ -match "^$key=" })) {
            $missing += "$key=$(New-ComposeSecret)"
            Write-Ok "Generated $key in $Path"
        }
    }
    if ($missing.Count -eq 0) { return }

    if (Test-Path $Path) {
        # Add-Content writes after the last byte, so a file that does not end
        # in a newline would swallow the first new key onto the tail of its
        # last line. An empty value terminates that line and adds nothing else.
        $raw = Get-Content -Path $Path -Raw
        if ($raw -and -not $raw.EndsWith("`n")) {
            Add-Content -Path $Path -Value "" -Encoding ascii
        }
        Add-Content -Path $Path -Value $missing -Encoding ascii
    } else {
        # ascii, not utf8. Both secrets are ASCII by construction, and
        # Windows PowerShell writes utf8 with a byte order mark, which compose
        # would read as part of the name of the first key in the file.
        Set-Content -Path $Path -Value $missing -Encoding ascii
    }
}

function Set-ImageTagPin {
    # Record a pinned version in the .env as well, where the two secrets are.
    # Setting it in this process would only reach this process, and the commands
    # printed at the end of the install are typed later in a fresh shell, where
    # ${OE_IMAGE_TAG:-latest} would quietly mean latest. The .env is read on
    # every compose invocation in this directory, so the pin holds for the pull,
    # for the up, and for every start after that.
    #
    # Unlike the two secrets this key is replaced when a later run asks for a
    # different version. Overwriting a version pin loses nothing, where
    # overwriting the password would lock the user out of the data PostgreSQL
    # already wrote.
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $Tag
    )

    $kept = @()
    if (Test-Path $Path) {
        $kept = @(Get-Content -Path $Path | Where-Object { $_ -notmatch '^OE_IMAGE_TAG=' })
    }
    Set-Content -Path $Path -Value ($kept + "OE_IMAGE_TAG=$Tag") -Encoding ascii
}

function Install-Docker {
    Write-Info "Installing via Docker..."
    New-Item -ItemType Directory -Force -Path $OE_INSTALL_DIR | Out-Null
    Set-Location $OE_INSTALL_DIR

    # The image override is saved as docker-compose.override.yml, the name
    # compose merges by itself with no -f flags. Two reasons. The base file
    # builds the app from source and there is no source here, only these two
    # files, so on its own it would stop on a Dockerfile that is not there.
    # And because the name is the automatic one, every plain `docker compose`
    # command run in this directory afterwards, including the ones printed
    # below, keeps meaning the stack that was installed.
    #
    # OE_VERSION is honoured here the way the other install methods below
    # honour it, and the way scripts/install.sh does. It used to be read into
    # $OE_VERSION at the top of this file and then ignored by this branch, so
    # asking for a version and getting Docker gave you whatever was on main.
    $files = @{
        "docker-compose.quickstart.yml"       = "docker-compose.yml"
        "docker-compose.quickstart.image.yml" = "docker-compose.override.yml"
    }
    $ref = if ($OE_VERSION -eq "latest") { "main" } else { "v$OE_VERSION" }
    foreach ($source in $files.Keys) {
        try {
            Invoke-WebRequest -Uri "$OE_REPO/raw/$ref/$source" -OutFile $files[$source] -ErrorAction Stop
        } catch {
            Write-Err "Failed to download ${source}: $($_.Exception.Message)"
            exit 1
        }
    }

    $envPath = Join-Path $OE_INSTALL_DIR ".env"
    Write-ComposeSecrets -Path $envPath
    if ($OE_VERSION -ne "latest") {
        Set-ImageTagPin -Path $envPath -Tag $OE_VERSION
    }

    # Pulling is spelled out rather than left to `up`, the same way the
    # quickstart-image make target does it, so which artefact runs is stated by
    # the command instead of inferred from compose's build-versus-pull rules
    # for a service that carries both an image and a build section.
    Write-Info "Pulling the published image..."
    Invoke-Native -Description "docker compose pull app" -Block {
        & docker compose pull app
    } | Out-Null

    Write-Info "Starting OpenConstructionERP..."
    Invoke-Native -Description "docker compose up -d" -Block {
        & docker compose up -d
    } | Out-Null

    # Wait for health check
    Write-Info "Waiting for health check..."
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:$OE_PORT/api/health" -TimeoutSec 2
            if ($resp.status -eq "healthy") {
                $healthy = $true
                break
            }
        } catch {}
        Start-Sleep -Seconds 2
    }

    if ($healthy) {
        Write-Ok "OpenConstructionERP is running at http://localhost:$OE_PORT"
    } else {
        Write-Warn "Service started but health check did not pass within 60s"
        Write-Host "  Check logs: cd $OE_INSTALL_DIR; docker compose logs -f"
    }
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  cd $OE_INSTALL_DIR; docker compose logs -f   # View logs"
    Write-Host "  cd $OE_INSTALL_DIR; docker compose down      # Stop"
}

function Install-Uv {
    Write-Info "Installing via uv..."

    if (-not (Test-Uv)) {
        Write-Info "Installing uv package manager..."
        irm https://astral.sh/uv/install.ps1 | iex
        # astral's installer drops uv.exe into %USERPROFILE%\.local\bin
        # but does NOT refresh the current session's PATH. Without this
        # the immediate ``& uv tool install`` below can't find uv.exe.
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }

    # Prefer the full path — survives ``$env:Path`` being wiped by a
    # profile script mid-session.
    $uvPath = if (Test-Path "$env:USERPROFILE\.local\bin\uv.exe") {
        "$env:USERPROFILE\.local\bin\uv.exe"
    } else { "uv" }

    # Use Invoke-Native so uv's "Resolved N packages" stderr progress does
    # not terminate the script under `irm | iex` (GitHub issue #87).
    Invoke-Native -Description "uv tool install openconstructionerp" -Block {
        & $uvPath tool install openconstructionerp
    } | Out-Null
    Write-Ok "OpenConstructionERP installed!"
    Write-Host ""
    Write-Host "Run: openconstructionerp serve --port $OE_PORT --open"
}

function Install-Pip {
    Write-Host ""
    Write-Host "  +-------------------------------------------------+"
    Write-Host "  |  Installing OpenConstructionERP (pip mode)      |"
    Write-Host "  +-------------------------------------------------+"
    Write-Host ""

    # 1. Verify Python
    Write-Info "[1/5] Checking Python 3.12+..."
    if (-not (Test-Python312)) {
        Write-Err "Python 3.12+ is required."
        Write-Host "  Install from: https://www.python.org/downloads/"
        exit 1
    }
    $pyVer = & python --version 2>&1
    Write-Ok "[1/5] Found $pyVer"

    # 2. Create venv
    Write-Info "[2/5] Creating virtual environment at $OE_INSTALL_DIR\venv ..."
    New-Item -ItemType Directory -Force -Path $OE_INSTALL_DIR | Out-Null
    if (-not (Test-Path "$OE_INSTALL_DIR\venv\Scripts\python.exe")) {
        & python -m venv "$OE_INSTALL_DIR\venv"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to create venv (exit $LASTEXITCODE)"
            exit 1
        }
    }
    Write-Ok "[2/5] Virtual environment ready"

    # 3. Install package
    # Wrap in Invoke-Native: pip emits deprecation warnings + SSL retry
    # notices to stderr, which would re-trigger issue #87's NativeCommandError
    # under `irm | iex`. --quiet silences progress but not warnings.
    Write-Info "[3/5] Installing openconstructionerp from PyPI..."
    Invoke-Native -Description "pip install --upgrade pip" -Block {
        & "$OE_INSTALL_DIR\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    } | Out-Null
    Invoke-Native -Description "pip install openconstructionerp" -Block {
        & "$OE_INSTALL_DIR\venv\Scripts\python.exe" -m pip install --quiet --upgrade openconstructionerp
    } | Out-Null
    Write-Ok "[3/5] Package installed"

    # 4. Initialise database
    Write-Info "[4/5] Initialising local database..."
    $cliExe = if (Test-Path "$OE_INSTALL_DIR\venv\Scripts\openconstructionerp.exe") {
        "$OE_INSTALL_DIR\venv\Scripts\openconstructionerp.exe"
    } else {
        "$OE_INSTALL_DIR\venv\Scripts\openestimate.exe"
    }
    & $cliExe init-db 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "init-db reported a non-zero exit code, continuing anyway..."
    } else {
        Write-Ok "[4/5] Database ready"
    }

    # 5. Put the command on PATH + create launchers
    Write-Info "[5/5] Putting 'openconstructionerp' on your PATH..."

    # start.bat: double-click launcher that also opens the browser.
    @"
@echo off
REM OpenConstructionERP launcher (auto-generated by install.ps1)
"$cliExe" serve --port $OE_PORT --open %*
"@ | Set-Content "$OE_INSTALL_DIR\start.bat" -Encoding ASCII

    # bin\openconstructionerp.bat: a small shim so the bare command works in
    # any new terminal, without leaking the venv's python/pip onto PATH.
    $binDir = "$OE_INSTALL_DIR\bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    @"
@echo off
"$cliExe" %*
"@ | Set-Content "$binDir\openconstructionerp.bat" -Encoding ASCII
    Add-ToUserPath $binDir
    Write-Ok "[5/5] 'openconstructionerp' is ready"

    Write-Host ""
    Write-Host "  +-------------------------------------------------+"
    Write-Host "  |  OpenConstructionERP is installed               |"
    Write-Host "  +-------------------------------------------------+"
    Write-Host ""
    Write-Host "  Open a NEW terminal and run:"
    Write-Host "     openconstructionerp"
    Write-Host ""
    Write-Host "  That starts the server and opens http://localhost:$OE_PORT"
    Write-Host "  Sign in with:  demo@openconstructionerp.com  /  DemoPass1234!"
    Write-Host ""
    Write-Host "  Right now in this window you can also use:"
    Write-Host "     $OE_INSTALL_DIR\start.bat   (start and open the browser)"
    Write-Host "     $cliExe doctor   (health check)"
    Write-Host ""

    # Offer to start now (this session already has the command on PATH).
    $reply = Read-Host "Start OpenConstructionERP now? [Y/n]"
    if ($reply -eq "" -or $reply -eq "y" -or $reply -eq "Y") {
        & "$OE_INSTALL_DIR\start.bat"
    }
}

# ── Main ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +===============================================+"
Write-Host "  |      OpenConstructionERP Installer            |"
Write-Host "  |      Construction Cost Estimation Platform    |"
Write-Host "  +===============================================+"
Write-Host ""

if (Test-Docker) {
    Write-Info "Docker detected, using Docker Compose (recommended)"
    Install-Docker
} elseif (Test-Uv) {
    Write-Info "uv detected, installing as Python tool"
    Install-Uv
} elseif (Test-Python312) {
    Write-Info "Python 3.12+ detected, installing via pip"
    Install-Pip
} else {
    Write-Info "No Docker or Python found, installing uv first"
    Install-Uv
}

Write-Host ""
Write-Ok "Installation complete!"
Write-Host ""
