# Backup freshness monitoring

A backup that stops running does not announce itself. It emits no error, because
nothing failed: a job that was unscheduled, disabled, or lost with a rebuilt host
simply stops, and everything that watches for failures keeps reporting green. A
backup that fails on a schedule is barely better if its refusal goes to a log,
because a refusal that nobody reads accumulates, and the missing alarm gets read as
evidence that the backup ran.

`scripts/check_backup_freshness.py` is built for that. It does not watch the job. It
looks at the newest dump on disk and complains when it is too old, too small, or not
there. That question has an answer whether the job failed, was never scheduled, or
never existed, which is the only phrasing that covers all three.

This page is the operational half: where to run it, what to run it with, how often,
and what to do with each answer.

## Where it runs decides what it can tell you

Run it on the machine that writes the dumps and it dies with the host it was meant to
report on. A dead host does not report badly. It reports nothing, and nothing looks
exactly like fine.

Run it against a copy of the dumps held somewhere else, and the same dead host
produces an alarm instead of silence. The artefact stops being refreshed, its age
keeps climbing, and the check goes stale on schedule. Nothing has to notice that the
host died, because staleness is a property of the artefact and not of the machine
that made it. That is the whole argument for where this belongs, and it is worth more
than any amount of care taken over the check itself.

That leaves one honest gap. Whatever runs the check off-box is itself unwatched, and
this page does not pretend to solve that. The check's job is to hand a meaningful exit
code to something that already pages a human. If nothing does, the exit code goes
nowhere and you are back where you started.

Whether a second copy of the dumps exists at all, and where it lives, is a deployment
decision this page does not make. Until one exists, the check can only run beside the
backups it is watching, and you should read its green as covering ordinary rollback,
not the loss of the host.

## What has to exist on the host that runs it

- A Python 3.12 or newer interpreter.
- `scripts/check_backup_freshness.py`, copied to that machine.
- Read access to the directory holding the finished dumps.

Nothing else. The script imports only the standard library, never imports the
application, and reads no configuration file, environment variable or database. That
is what lets it live on a monitoring box that has none of this platform installed, and
it is the property to preserve if the script is ever changed.

## Invocation

```bash
# --min-bytes is the one value here you should not copy. It has to come from the
# size of a good dump on your own install; the number below is a placeholder.
python3 check_backup_freshness.py \
    --dir /var/backups/postgresql \
    --pattern '*.dump' \
    --max-age-hours 26 \
    --min-bytes 50000000
```

| Flag | Default | What it is |
|---|---|---|
| `--dir` | required | Directory holding the finished dumps. |
| `--pattern` | `*.dump` | Glob matched against file names. Must match only finished dumps. |
| `--max-age-hours` | `26` | Age at which the newest dump counts as stale. |
| `--min-bytes` | `1` | Smallest size a dump may have and still count as usable. |

One requirement on whatever writes the dumps: it must write to a temporary name and
rename into place once the dump is complete. A dump written directly under its final
name is visible to this check while it is still growing, and would be reported as
truncated every night. Point `--pattern` at the finished name, not at the temporary
one.

## How often

Every few minutes is fine and costs nothing: the check stats the files in one
directory and exits. There is no benefit in running it more often than your alert
route can act, and no harm in running it more often than the backup.

Running it far less often than the backup is the mistake worth avoiding. A check that
runs once a day can be up to a day late on top of a threshold that is already a day
wide, so an outage can be two days old before anyone hears about it.

## Setting the threshold, and why the default is 26

**26 hours assumes a daily dump.** If the real schedule is not daily, that number is
wrong, and it is wrong in the direction that never announces itself.

The threshold has to exceed three things added together:

    dump interval + typical dump duration + however late the check may run

The age of the newest dump climbs to roughly one full interval just before the next
one starts, the dump itself takes minutes to finish, and the checker may not run at
the instant the dump lands. Anything less than that sum produces a stale alarm on a
backup regime that is working perfectly, and an alarm that cries wolf gets silenced
within a week, after which it catches nothing at all.

| Dump schedule | Reasonable `--max-age-hours` |
|---|---|
| Every 6 hours | 8 |
| Twice daily | 14 |
| Daily | 26 (the default) |
| Weekly | 176 |

Setting it too loose is the more dangerous mistake, and it is the one this section
exists for. A threshold that is too wide is silent by construction. It produces no
warning, no noise and no symptom of any kind. The only thing it produces is an outage
that ran longer than it should have before anyone was told. So when the backup
schedule changes, this number has to change with it, and nothing in the system will
remind you.

## Setting the size floor

`--min-bytes` defaults to `1`, which catches only a zero-length file. That is a floor,
not a setting, and leaving it there means the check will pass a dump that died after
four kilobytes.

This matters because a dump killed part way through carries a *current* mtime. It
looks like the freshest thing in the directory, an age-only check waves it past, and
the truth surfaces at restore time when it is far too late to do anything about it.

Set it from the real size of a good dump on your install, low enough not to trip on
ordinary variation between days and high enough that a dump which died early cannot
clear it. Somewhere around half the usual size is a reasonable starting point.

## What the answers mean, and what to do with each

The check prints one line naming the directory it looked at, the file it judged, the
age it measured and the threshold it measured against, so whoever receives the alert
does not have to go back to the machine to work out what the word "stale" referred to.
The all-clear goes to stdout, every complaint goes to stderr, and the exit code is the
part your alert route should read.

| Exit | Status | What it means |
|---|---|---|
| 0 | `FRESH` | A dump exists, is within the threshold, and clears the size floor. |
| 1 | `STALE` | The newest dump is older than the threshold. |
| 1 | `MISSING` | No dump at all, or the directory is not there. |
| 1 | `TRUNCATED` | The newest dump is below the size floor. |
| 2 | `UNKNOWN` | The check could not tell. |

**Exit 1 means act on the backup.** Something is wrong with the dumps themselves.
`STALE` and `MISSING` both mean there is nothing recent to restore from, and `MISSING`
in particular covers the case where the job stopped being scheduled and therefore
never produced a failure for anything to catch. `TRUNCATED` means the newest dump is
unusable; the message names an older usable dump if one exists, so read it before
concluding you have nothing.

Note that `TRUNCATED` fires even when an older good dump is still within the
threshold. The recovery point is intact in that case, but the job is broken now, and
waiting for the good dump to age out would delay the alarm by a full retention window.

**Exit 2 means act on the check.** The check could not reach or read what it was
pointed at: a path that is not a directory, a directory it lacks permission to open,
an argument that makes no sense. Nothing has been learned about the backup either way.

**Do not collapse 1 and 2 into the same page.** The distinction is the point of having
two codes, and it only exists if the receiving end treats them differently. A route
that pages identically for both will one day send someone to rebuild a backup regime
that is running perfectly, because the real fault was a permission on the directory
and the alarm never said so. Route exit 2 to whoever owns the monitoring, and exit 1
to whoever owns the data.

What must never happen is exit 2 being treated as success. "I could not see anything"
and "everything is fine" are different answers, and an alert route that quietly drops
the first one converts silence into a green tick in exactly the environment where
something is already wrong. The check itself will never return 0 for a question it
could not answer; the same discipline has to hold on the other side of the exit code.

## Verifying it before you trust it

A check nobody has seen fail is a fact about the check. Before relying on it, point it
at a directory that should be red and confirm that it is:

- an empty directory, which should give `MISSING` and exit 1
- a directory holding only a dump older than the threshold, which should give `STALE`
  and exit 1
- a zero-length file matching the pattern, which should give `TRUNCATED` and exit 1
- a path that is a file rather than a directory, which should give `UNKNOWN` and exit 2

Use a scratch directory you create for the purpose, not the real one. Then confirm the
alert route carries each of those to a human, because a correct exit code delivered
nowhere is the failure this page exists to prevent.

## Related

- [Linux install guide](./INSTALL_LINUX.md) - setting the platform up on a server.
- [Email and SMTP setup](./email-setup.md) - configuring outbound mail. Worth reading
  before routing any alert through it: the platform's default transport writes mail to
  the application log and reports it as delivered, so an alert path built on an
  unconfigured mail setup produces a success flag and no message.
