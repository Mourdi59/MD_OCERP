"""Event-triggered custom-agent runs (Item 29).

This wires the platform event bus to the agent automation envelope: when a
platform event fires (an RFI is created, a document is uploaded), every custom
agent that subscribed to the matching trigger is run automatically with the
event's context. This is the piece the scheduler module's docstring deferred to
"a later wave" - it is now live, so the trigger catalogue in
:mod:`app.modules.ai_agents.triggers` marks those events ``available=True``.

Design choices (consistent with the rest of the module):

* **Reuse, no new machinery.** Each handler runs the subscribed agents through
  the same :meth:`AgentService.start_run` path the scheduler uses, tagged
  ``trigger_source="event:<trigger>"`` so the monitoring panel and audit trail
  can tell event-fired runs apart from manual/scheduled ones.
* **Human-confirmed, never auto-applied.** An event-fired run produces the same
  reviewable proposal as any other run - it writes nothing to the BOQ/project.
  The architecture guide's "AI-augmented, human-confirmed" rule is absolute.
* **Fail-soft.** A handler opens its own session (the publisher's session is
  long gone for a detached publish), awaits each subscribed agent's run
  sequentially to bound LLM concurrency, and never raises out - one bad agent
  must not poison the event bus for every other subscriber.
* **Runs on behalf of the agent's creator.** ``start_run`` resolves a
  ``custom:<id>`` slug only for its owner, so firing under ``agent.user_id``
  keeps the per-user ownership model intact.

Subscriptions are registered at import time (the module loader imports
``events`` during module load, same contract as every other module's events).
"""

from __future__ import annotations

import logging

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

# Map an event-bus event name to the agent trigger slug the builder UI lists.
# Only events that genuinely fire on the bus are mapped (rfi.created and
# document.uploaded are both published today); a slug with no publisher is
# intentionally absent so the catalogue can label it "coming soon".
_EVENT_TO_TRIGGER: dict[str, str] = {
    "rfi.created": "rfi_created",
    "document.uploaded": "document_uploaded",
}

# How the new context is summarised into the prompt fired at a subscribed agent.
# Kept short and factual - the agent's own system prompt drives what it does
# with it. The IDs let a tool-using agent fetch the full record if granted.
_TRIGGER_PROMPTS: dict[str, str] = {
    "rfi_created": (
        "A new RFI (number {rfi_number}) was just created on project {project_id}. "
        "RFI id: {rfi_id}. Do your task for this RFI and report the result."
    ),
    "document_uploaded": (
        "A new document '{name}' (category {category}) was just uploaded to "
        "project {project_id}. Document id: {document_id}. Do your task for this "
        "document and report the result."
    ),
}

# Generic fallback prompt when a trigger has no specific template.
_DEFAULT_TRIGGER_PROMPT = "A '{trigger}' event just fired. Run your task and report the result."


def _build_input(trigger: str, data: dict) -> str:  # type: ignore[type-arg]
    """Render the prompt a subscribed agent is fired with for this event."""
    template = _TRIGGER_PROMPTS.get(trigger, _DEFAULT_TRIGGER_PROMPT)
    safe = {"trigger": trigger}
    safe.update({k: ("" if v is None else str(v)) for k, v in data.items()})
    try:
        return template.format_map(_DefaultDict(safe))
    except Exception:  # noqa: BLE001 - never let a bad template break the bus
        return _DEFAULT_TRIGGER_PROMPT.format(trigger=trigger)


class _DefaultDict(dict):
    """``str.format_map`` helper: missing keys render empty instead of raising."""

    def __missing__(self, key: str) -> str:  # noqa: D401 - dunder
        return ""


async def _fire_subscribed_agents(trigger: str, data: dict) -> int:  # type: ignore[type-arg]
    """Run every custom agent subscribed to ``trigger`` with the event context.

    Returns the number of agents fired. Opens its own session; each agent run is
    awaited sequentially so one event does not spawn an unbounded burst of
    concurrent LLM calls on the single-process deploy.
    """
    from app.modules.ai_agents.service import AgentService

    project_id = _coerce_project_id(data.get("project_id"))
    user_input = _build_input(trigger, data)
    fired = 0
    async with async_session_factory() as session:
        service = AgentService(session)
        agents = await service.custom_repo.list_subscribed_to_trigger(trigger)
        for agent in agents:
            # Snapshot identity before start_run (its update_fields expires the
            # identity map; later attribute access would emit an illegal lazy
            # SELECT on the async session).
            agent_user_id = agent.user_id
            agent_name = agent.agent_name
            try:
                await service.start_run(
                    user_id=agent_user_id,
                    agent_name=agent_name,
                    user_input=user_input,
                    project_id=project_id,
                    trigger_source=f"event:{trigger}",
                )
                fired += 1
            except Exception:  # noqa: BLE001 - one bad agent never stalls the bus
                logger.exception("Event-triggered run for agent %s (%s) failed to start", agent_name, trigger)
        await session.commit()
    if fired:
        logger.info("ai_agents fired %d agent(s) on trigger %s", fired, trigger)
    return fired


def _coerce_project_id(raw: object) -> object:
    """Best-effort UUID coercion of an event's ``project_id`` (or None)."""
    import uuid

    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _make_handler(trigger: str):  # type: ignore[no-untyped-def]
    """Build an event-bus handler that fires the agents subscribed to ``trigger``."""

    async def _handler(event: Event) -> None:
        try:
            await _fire_subscribed_agents(trigger, event.data or {})
        except Exception:  # noqa: BLE001 - bus handlers must never raise out
            logger.exception("ai_agents event handler for %s failed", trigger)

    _handler.__qualname__ = f"ai_agents.on_{trigger}"
    return _handler


# Register one handler per mapped event at import time (module-load contract).
for _event_name, _trigger in _EVENT_TO_TRIGGER.items():
    event_bus.subscribe(_event_name, _make_handler(_trigger))
