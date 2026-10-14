# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The permits and design demo seeds leave a project whose frame is already binding alone, quietly."""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest

from app.modules.design_management import seed as design_seed
from app.modules.permits import seed as permits_seed
from app.modules.permits.service import PermitService


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return None


class _Session:
    def __init__(self, pid):
        self._pid = pid
        self.nested = 0

    async def execute(self, stmt):
        text = str(stmt)
        if "projects" in text and "SELECT" in text and "roadmap" not in text and "setup" not in text:
            return _Result([(self._pid, {"demo_id": "x"})])
        return _Result([])

    def begin_nested(self):
        self.nested += 1
        raise AssertionError("a binding frame must not be seeded")


@pytest.mark.asyncio
async def test_permits_seed_skips_binding_frame(monkeypatch, caplog):
    pid = uuid.uuid4()
    monkeypatch.setattr("app.core.demo_marker.demo_id_of", lambda meta: "x")

    async def doc(self, project_id):
        return SimpleNamespace(status="binding")

    monkeypatch.setattr(PermitService, "_roadmap_document", doc)
    session = _Session(pid)
    with caplog.at_level(logging.INFO):
        totals = await permits_seed.seed_permits_demo(session, [pid])
    assert totals["projects"] == 0 and session.nested == 0
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.asyncio
async def test_design_seed_skips_binding_frame(monkeypatch, caplog):
    from app.modules.design_management.service import DesignService

    pid = uuid.uuid4()
    monkeypatch.setattr("app.core.demo_marker.demo_id_of", lambda meta: "x")

    async def refusal(self, project_id):
        return object()

    async def catalogue(session, project_id):
        return object()

    monkeypatch.setattr(DesignService, "binding_refusal", refusal)
    monkeypatch.setattr("app.modules.project_governance.public.project_catalogue", catalogue)
    session = _Session(pid)
    with caplog.at_level(logging.INFO):
        totals = await design_seed.seed_design_management_demo(session, [pid])
    assert totals["projects"] == 0 and session.nested == 0
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
