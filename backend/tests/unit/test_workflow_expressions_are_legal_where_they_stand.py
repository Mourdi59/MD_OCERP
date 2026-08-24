"""A workflow GitHub refuses to parse does not go red, it stops existing.

This exists because of a specific failure that cost two commits of coverage on a
required lane. A job-level ``env:`` block named ``${{ runner.temp }}``. That is
valid YAML, it reads naturally, and every instrument we owned said the file was
fine: ``yaml.safe_load`` parsed it into four jobs, and the lane-coverage test
read it as text and found the job it was looking for. GitHub rejected the whole
file, and the result was not a red gate. It was a run named after the file path,
carrying zero jobs, with a required lane simply absent. Absence reads as "not
finished yet" rather than as "broken", which is why it survived two pushes.

The rule GitHub applies is that a context is only available where the value is
evaluated. A job-level ``env:`` block is evaluated before a runner is assigned,
so ``runner`` is not available there, and neither is ``env`` itself, ``steps``,
``job`` or ``jobs``. ``github``, ``needs``, ``strategy``, ``matrix``, ``vars``,
``inputs`` and ``secrets`` are. The same restriction applies to the other
job-level keys that are evaluated at the same moment.

So this checks the placement of a context rather than the shape of the file,
which is the property that actually decides whether the file runs. It is
deliberately narrow: it does not attempt to be a workflow validator, because a
partial validator that claims to be a whole one is worse than none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
# A context is the leading identifier of an expression term, e.g. the "runner"
# of "runner.temp". Matching on a word boundary rather than a bare substring so
# a string containing the word does not read as a context reference.
CONTEXT = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\.")

# Available before a runner exists, i.e. everywhere a job-level key is
# evaluated. Anything outside this set is a rejection, not a warning.
JOB_LEVEL_CONTEXTS = frozenset({"github", "needs", "strategy", "matrix", "vars", "inputs", "secrets"})

# The job-level keys evaluated at that same moment. `steps` is excluded on
# purpose: a step body is evaluated on the runner, where `runner` is legal, and
# that is exactly the distinction this file is about.
JOB_LEVEL_KEYS = ("env", "runs-on", "services", "container", "defaults", "timeout-minutes")


def _workflow_files() -> list[Path]:
    files = sorted(p for p in WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not files:
        pytest.fail(f"no workflow files found under {WORKFLOWS}; this check would pass vacuously")
    return files


def _illegal_contexts(value: object) -> list[str]:
    """Return every context named inside `value` that a job-level key cannot use."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_illegal_contexts(key))
            found.extend(_illegal_contexts(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_illegal_contexts(item))
    elif isinstance(value, str):
        for expression in EXPRESSION.findall(value):
            for context in CONTEXT.findall(expression):
                if context not in JOB_LEVEL_CONTEXTS:
                    found.append(context)
    return found


def _offences(document: dict) -> list[str]:
    offences: list[str] = []
    for job_name, job in (document.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for key in JOB_LEVEL_KEYS:
            if key not in job:
                continue
            for context in _illegal_contexts(job[key]):
                offences.append(
                    f"job '{job_name}' names the '{context}' context in its '{key}', "
                    f"which is evaluated before a runner exists. GitHub rejects the whole "
                    f"file for this, and every job in it stops running."
                )
    return offences


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_job_level_key_names_a_context_it_cannot_have(path: Path) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    offences = _offences(document)
    assert not offences, "\n".join(offences)


def test_the_check_catches_the_edit_that_caused_it_and_spares_the_repair() -> None:
    """The negative control, in both directions, on the real pair of values.

    A check that has never been shown to fail on the thing it exists to catch
    says nothing when it passes, and this one was written precisely because two
    other instruments passed while blind.
    """
    broken = yaml.safe_load(
        "jobs:\n  upgrade:\n    runs-on: ubuntu-latest\n    env:\n      OE_DATA_DIR: ${{ runner.temp }}/oe-data\n"
    )
    offences = _offences(broken)
    assert len(offences) == 1, offences
    assert "runner" in offences[0]

    repaired = yaml.safe_load(
        "jobs:\n  upgrade:\n    runs-on: ubuntu-latest\n    env:\n      OE_DATA_DIR: ${{ github.workspace }}/oe-data\n"
    )
    assert _offences(repaired) == []


def test_a_step_may_still_name_the_runner() -> None:
    """The rule is about placement, so the check must not convict a legal use.

    Steps run on the runner and may say so. A check that forbade the context
    everywhere would be enforced by deleting it, which is how a gate that cries
    wolf gets removed.
    """
    stepwise = yaml.safe_load(
        "jobs:\n  upgrade:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ runner.temp }}\n"
    )
    assert _offences(stepwise) == []
