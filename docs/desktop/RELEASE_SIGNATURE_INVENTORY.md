# Which releases are signed, and what "signed" means

This page states plainly what cryptographic guarantees an OpenConstructionERP
download does and does not carry. It exists because "is it signed?" has four
different answers here and they do not agree with each other, so a single yes or
no would be misleading whichever way it went.

Numbers on this page are dated. To get current ones, run the command at the
bottom rather than trusting the text.

## The four mechanisms

They are produced by different jobs, they protect different things, and a
release can carry any subset of them.

| | Mechanism | What it proves | Who checks it |
| --- | --- | --- | --- |
| 1 | git tag signature | who cut the tag | anyone running `git tag -v` |
| 2 | Sigstore / cosign | these are the bytes we published | anyone running `cosign verify-blob` |
| 3 | macOS Developer ID and notarisation | who published the app, and that Apple scanned it | Gatekeeper, on every Mac |
| 4 | Windows Authenticode | who published the installer | SmartScreen, on every PC |

## Where we stand, as of 2026-08-12

**1. No git tag in this repository is signed.** Not one, across 325 tags, read
off the tag objects in a full clone. Tag protection on GitHub restricts who may
push a tag, which is a different thing: it is an access control, not an
attestation, and it leaves no artifact you can check afterwards. Worth stating
alongside it that `PYPI_API_TOKEN` is the only Actions secret configured, so
what tag protection currently guards is one publishing path, and nothing about
it attests to anything.

**2. Every release from v14.0.0 through v14.8.1 carries a Sigstore signature.**
Measured 2026-08-19, over 245 published releases. It is deliberately not phrased
as "from v14.0.0 onward". Nothing gates a release on carrying one. The signing
workflow has silently stopped producing them before, for a long stretch that
nobody noticed at the time, so a rule stated forward would quietly become false
the next time it happens rather than showing up as the gap it is.

Note what moved since the 2026-08-12 reading, because it is a lesson about the
measurement rather than about the releases. That reading named v14.5.0 as the
start of the stretch; the stretch in fact reaches back to v14.0.0 and has since
extended forward to v14.8.1. Read from the head of the release list, the answer
comes out short in a way that looks confident, which is why this page tells you
to run the command instead of trusting the text.

Across the whole history 38 of the 245 releases carry all three files, in 22
alternating stretches. The current one is the longest by a wide margin: before
v14.0.0 there is a gap of 129 consecutive unsigned releases running back to
v4.10.0, and everything earlier alternates every few releases. Treat a missing
signature on an older release as ordinary, not as a sign that something went
wrong with that release.

**Backfilling older releases was considered on 2026-08-19 and declined.** The
supported line is signed and that is what we guarantee. The reason is the one
set out under "Regenerating this" below, plus a second that is easy to miss: a
Sigstore certificate is short lived and the transparency log records the time of
signing, so a signature applied today attests that these are the bytes on the
release today. That defends against tampering from now on, which is worth
having, but it is not what a reader assumes a release signature means, and it is
the reader's assumption that decides whether the guarantee is honest. Sign the
line we support, say where it starts, and do not dress a weak claim as a strong
one.

**3. No macOS build has ever been signed with a Developer ID certificate or
notarised by Apple.** The "ever" is established from the workflow history, not
from today's configuration: no file under `.github/` has ever contained an
`APPLE_` credential reference in any commit on any branch, apart from the status
step added on 2026-08-12 whose whole purpose is to report their absence. A
credential that never reaches the build cannot sign anything, whether or not it
existed as a secret, so this covers the entire history rather than the present.
Check it with `git log --all -S'APPLE_' -- .github/`.

The `.dmg` and `.app` are ad-hoc signed. An ad-hoc signature seals the bundle,
so its contents cannot be altered without breaking the seal, and that part is
real and is worth having. It does not identify a publisher and Gatekeeper does
not accept it. That is why the release notes ask you to clear the quarantine
attribute by hand: the app is not broken, it is unsigned in the sense macOS
cares about.

**4. No published Windows installer carries an Authenticode signature.** This
one is measured on the bytes we actually published. Every one of the 113
releases that ships a Windows installer had its `.exe` read on 2026-08-12, and
none of them carries a certificate. Each of those releases carries exactly one
`.exe` and exactly one `.msi`. The `.msi` was not read separately because one
signing step covers both in a single pass, over the glob
`signing/*.exe signing/*.msi`, so a step that produced no signature on the
`.exe` produced none on the `.msi` either. From 15.2.0 the `.msi` is no longer
built, so the glob reads `signing/*.exe` and a certificate, when one exists,
covers the single installer we ship.

The measurement matters because the argument available otherwise is weaker than
it looks. The Azure signing step has been wired since 2026-06-09, and the secret
list can only be read as it stands today, so "the secrets are not configured"
cannot by itself rule out a release signed while a credential existed and was
later removed. Reading the installers does rule it out.

SmartScreen warns about these installers, and that warning is correct. The
pipeline is ready and will sign them as soon as a certificate exists; see
[WINDOWS_SIGNING.md](WINDOWS_SIGNING.md) for exactly what has to be created. The
missing piece is the certificate, not the automation.

There is a difference between 3 and 4 worth keeping straight. Windows signing is
wired and waiting on a credential. macOS signing is not wired at all: the build
step is never handed the Apple credentials, so creating them would change
nothing on its own. See [MACOS_NOTARIZATION.md](MACOS_NOTARIZATION.md).

## What we do not claim

We do not claim that any published `.exe`, `.msi`, `.dmg` or `.app` is signed by
a certificate that identifies us. We do not claim any release is notarised. If
you see a page of ours saying otherwise, that page is wrong and we would like to
know about it.

We do claim, for a release that actually carries the three files, that the
Sigstore signature over `SHA256SUMS` was produced by our release workflow and
covers the bytes we published. That signature is made over the artifacts as they
were uploaded, not over a rebuild, so verifying a download against it is
meaningful. Check whether the release you are holding carries them rather than
inferring it from its version number.

## Verifying a download yourself

For a release that carries the three files:

```
cosign verify-blob \
  --certificate SHA256SUMS.pem \
  --signature SHA256SUMS.sig \
  --certificate-identity-regexp 'https://github.com/datadrivenconstruction/OpenConstructionERP/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  SHA256SUMS

sha256sum -c SHA256SUMS
```

The first command establishes that the checksum manifest is ours. The second
establishes that your download matches it. Both have to pass; the first alone
says nothing about the file you downloaded.

To look at a platform signature directly, on macOS:

```
codesign -dv --verbose=4 /Applications/OpenConstructionERP.app
spctl --assess --type execute -vv /Applications/OpenConstructionERP.app
```

and on Windows, with the SDK's `signtool`:

```
signtool verify /pa /v OpenConstructionERP_x64-setup.exe
```

Today both of those report the absence described above. That is the expected
result, not a failed download.

## Backfilling a signature onto an older release

A release published without a Sigstore signature can be given one afterwards.
The signature is made over the assets already on the release, so it attests to
the bytes people have been downloading rather than to a rebuild. That holds
structurally rather than by intention: the signing job contains no
`actions/checkout`, so it has no source tree and could not rebuild an installer
even by accident.

```
gh workflow run release-signing.yml -f tag=v14.3.0 -f backfill=true
```

The run ends by reading the three files back off the release and goes red if
they are not there, so a green run means the signature arrived rather than that
every step reported success. Those are not the same thing: the job that signs
depends on the job that skips, and a run in which the signing job never starts
has nothing to report a failure. This checks the release, not the run. It does
not, and cannot, tell you about a release nobody dispatched, which is the other
way a release ends up unsigned and the reason claim 2 above is dated rather than
stated as a rule.

`backfill=true` skips the SBOM job, and that is the part worth understanding
before running it. The SBOM is generated when the workflow runs, from whatever
the dependency ranges resolve to that day. On a current release that is
accurate. On a release from six weeks ago it would describe software that
release never contained, and since the manifest covers every asset, the
signature would then attest to that description too. A release with no component
list is missing something. A release with a signed and incorrect one is worse,
because a signature is precisely the thing that stops people checking.

Backfilling is not reversible in any tidy way, so it is worth being deliberate
about scope. Signing the supported line only keeps the claim per release
unambiguous and avoids older release pages quietly gaining assets they never
had, which is a visible change to public pages that nobody asked for.

## Regenerating this

```
python scripts/release_signature_inventory.py                    # summary
python scripts/release_signature_inventory.py --all              # every release
python scripts/release_signature_inventory.py --check-artifacts  # read the bytes
```

The script reads the release list from the GitHub API, the tag objects from your
clone, and the credential wiring from the workflow files, and it labels every
answer with how it was obtained. It refuses to print an inventory if the API
page comes back short, because a truncated fetch looks exactly like a healthy
repository with fewer releases, and for the same reason it refuses to say "no
tag is signed" from a clone that is missing tags.

`--check-artifacts` is what turns claim 4 from an argument into an observation.
It fetches the first 8 KB of every published Windows installer and reads the
certificate table out of the PE header, which is where the pointer to an
Authenticode signature lives, so it settles the question without downloading any
payload. Before judging anything it checks that the reader can recognise a
signature it was handed, because a reader that could only ever answer "unsigned"
would produce this exact report and look like a finding.

What it still cannot do, stated so that a clean run is not over-read. There is
no equivalent for macOS from a machine that is not a Mac: notarisation lives in
a stapled ticket, so mechanism 3 is answered from the workflow history and the
credential wiring rather than from the artifact. And tag signatures are
invisible to the GitHub API, so run it inside a checkout with `git fetch --tags`
already done.
