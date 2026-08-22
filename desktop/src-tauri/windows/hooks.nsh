; OpenConstructionERP - NSIS installer hooks
;
; Windows keeps an exclusive lock on a running .exe. If the backend sidecar
; (openconstructionerp-server.exe) is still running when the installer tries to
; overwrite it, or when the uninstaller tries to delete it, the operation fails
; with "file in use by another process". That is the reinstall error users hit:
; after the app is closed or uninstalled the sidecar can linger in the
; background, and the next install cannot replace the locked file until the
; process is stopped by hand in Task Manager.
;
; These hooks stop that process before the installer writes files and before the
; uninstaller removes them, so the file lock is gone by the time it matters.
;
; Two things they must not do, and used to.
;
; They must not kill processes that are not ours to kill. The old hooks ran
; `taskkill /F /T /IM <name>`, and /IM matches by image name across the whole
; machine: an elevated installer stopped that image in EVERY logged-in user's
; session, and in every other installation of the product on the machine.
; Matching on the executable path instead scopes the stop to the installation
; being worked on. Another install, in another directory, is now none of our
; business - which it always was.
;
; And they must not force-kill when they can ask. A forced stop is an unclean
; stop for the embedded PostgreSQL cluster the backend runs, so the next start
; has a write-ahead log to replay, which on a large database takes minutes and
; is what users have been reading as "the application backend did not start in
; time" after an upgrade. Closing the app's window instead runs the launcher's
; own exit path, which asks the backend to shut down cleanly. So: ask first,
; wait, and force only what is left.
;
; The path comes through the environment rather than being pasted into the
; PowerShell command, so an install directory containing a quote or a dollar
; sign cannot break the script that is supposed to protect it.
;
; The taskkill lines are the fallback for a machine where PowerShell will not
; run at all. They are narrowed to this user's own processes, so they can never
; reach into another user's session the way the original did - and they run ONLY
; when PowerShell could not be started, because the USERNAME filter makes
; taskkill resolve the owner of every process on the machine, which was measured
; at 55 seconds per call. An installer may not spend two minutes on a step that
; usually has nothing to do.

; One more thing this has to get right, and it is invisible from the source: an
; NSIS installer is a 32-bit process, so `powershell` on its PATH resolves under
; WOW64 to the 32-bit copy in SysWOW64 - and a 32-bit process cannot read the
; module list of a 64-bit one, so `(Get-Process).Path` is empty for every
; process this hook cares about. Measured, not reasoned: with redirection left
; on, the filter matched 0 of 1 running processes and the hook was a silent
; no-op. Turning file-system redirection off for the call gets the 64-bit
; PowerShell, which matched 1 of 1.

!include LogicLib.nsh
!include x64.nsh

!macro OE_STOP_THIS_INSTALL
  Push $0
  DetailPrint "Closing OpenConstructionERP..."
  ; Hand the install directory to the script below without quoting it.
  System::Call 'kernel32::SetEnvironmentVariable(t "OE_STOP_DIR", t "$INSTDIR")'
  ; Close the app window (which stops its backend cleanly), give it a bounded
  ; wait, then force whatever is still running from this directory. The wait
  ; only happens if something actually had a window to close, so an orphaned
  ; backend with no app in front of it is dealt with immediately.
  ${If} ${RunningX64}
    ${DisableX64FSRedirection}
  ${EndIf}
  nsExec::Exec `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d = $$env:OE_STOP_DIR; if ($$d) { $$p = @(Get-Process -ErrorAction SilentlyContinue | Where-Object -Property Path -Like ($$d + '\*')); if ($$p.Count -gt 0) { if (@($$p.CloseMainWindow()) -contains $$true) { $$p | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue }; $$p | Stop-Process -Force -ErrorAction SilentlyContinue } }"`
  Pop $0
  ${If} ${RunningX64}
    ${EnableX64FSRedirection}
  ${EndIf}
  ${If} $0 != "0"
    ; PowerShell could not be run at all ("error", or a non-zero exit). The
    ; former product name is here too, because an upgrade from it is the one
    ; case a path match can miss: that install may live in another directory.
    DetailPrint "Falling back to stopping the processes by name..."
    nsExec::Exec `cmd /c taskkill /F /T /FI "IMAGENAME eq openconstructionerp-server.exe" /FI "USERNAME eq %USERNAME%"`
    Pop $0
    nsExec::Exec `cmd /c taskkill /F /T /FI "IMAGENAME eq openestimate-server.exe" /FI "USERNAME eq %USERNAME%"`
    Pop $0
  ${EndIf}
  ; A moment for Windows to release the file handles after the exits.
  Sleep 800
  Pop $0
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro OE_STOP_THIS_INSTALL
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro OE_STOP_THIS_INSTALL
!macroend
