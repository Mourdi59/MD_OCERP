# 004. Case role cells are drawn marks, not photographs

Status: Accepted
Date: 2026-08-26

## Context

A case card and a case detail page name the professional roles a playbook is
written for. Those cells used to be photographs, cast by a script that lives on
the marketing site, under a path this repository does not track.

The casting could not have been right. The pool of portraits is organised by
company type while the cell is keyed by profession, so a lookup either found
nobody or found a face that had been cast for a different job. Falling back to
the nearest available portrait is not an injective mapping, so distinct
professions collapsed onto one face and a row of different jobs read as the
same person in different shades. The tracked mirror of that casting logic,
`frontend/src/features/cases/caseFaces.ts`, says so in its own header and
records which side of the split is the wrong one.

## Decision

A role cell is an inline vector mark: the role's glyph on a tinted disc in the
role's accent colour. The rule is written where the drawing happens, in
`frontend/src/features/cases/RoleArt.tsx`, which states that this is a flat and
clear vector mark with no raster portrait and no brand asset. The vocabulary is
`ROLE_META` in `frontend/src/features/cases/roles.ts`. The marketing site draws
the same marks from that same vocabulary and has a parity check that fails when
the two drift apart, though both the generator and the check live beside the
retired scripts and are not tracked here either. That check also verifies that
the marks stay injective, one distinct drawing per role, which is precisely the
property whose absence caused the defect this decision removed.

This retires two scripts, both in `marketing-site/scripts/`. `put_case_face.py`
cast the photographs. `patch_case_person_axis.py` was written to repair the
axis split, four of its five edits had already been applied, and the fifth drew
a bust that the marks replace.

## Consequences

Both scripts stay on disk with a note at the top saying they are superseded and
must not be run. Deleting them was the obvious move and it is the wrong one: a
script that disappears without a reason gets written again by the next person
who notices the gap it left.

Neither could run today in any case, which is worth knowing before someone
tries to revive one. `put_case_face.py` looks for gallery cards shaped as an
anchor with an href, the markup is now an article with a data attribute, so it
parses no cards at all and its own check for unknown roles then passes because
it has nothing to check. `patch_case_person_axis.py` exits while loading,
because the JSON files it reads no longer exist, and its guards would overwrite
every generated mark if it ever got past that.

`caseFaces.ts` still mirrors the retired script's logic. Its header already
says it mirrors the logic rather than the behaviour, and it is left alone here
so that the app keeps a single description of how casting once worked.

This is one record rather than two. The scripts are two instruments of one
decision, and splitting the decision across two files would leave each half
looking smaller than it is. Anyone who comes looking for a second ADR finds the
reason here instead.

The photographs themselves are untouched and tracked under
`frontend/public/assets/people/`, so reversing this means rewriting the cell,
not recovering assets.

The reason this record exists at all is that the decision was made in files the
repository does not track, and a note inside such a file reaches only a reader
who already opened it. This directory is the first place the decision is
durable.
