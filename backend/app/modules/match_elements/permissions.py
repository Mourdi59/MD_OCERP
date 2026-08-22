# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Match Elements permission definitions.

One route in this module acts on the host rather than on project data:
``POST /qdrant/install`` downloads the native Qdrant binary from GitHub
Releases into ``~/.openestimator/qdrant`` and starts it. Its own docstring
says it mirrors the converter-install pattern used by /takeoff and /bim, and
it did mirror everything about that pattern except the gate - the converter
install asks for ``takeoff.create`` while this one asked only that somebody
be logged in. Same class of action, two different bars.

ADMIN rather than EDITOR because this one writes a service binary to the
server's filesystem and leaves a process running, which is an install-level
act against the host, not a change to a project. The converter install sits
lower because a converter is a per-file tool the upload path installs on
demand; nothing here is on demand.

Everything else in this module reads or writes match data inside a project
and is scoped by the project the match run belongs to.
"""

from app.core.permissions import Role, permission_registry


def register_match_elements_permissions() -> None:
    """Register permissions for the Match Elements module."""
    permission_registry.register_module_permissions(
        "match_elements",
        {
            "match_elements.qdrant.install": Role.ADMIN,
        },
    )
