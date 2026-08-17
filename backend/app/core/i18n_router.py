# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""i18n API endpoints.

Serves the backend catalogue, backend/locales/*.json, to any HTTP consumer.

It does NOT serve this product's own UI, despite what the route names suggest.
The frontend builds its i18next store from bundled resources and lazy-loaded
locale chunks (frontend/src/app/i18n.ts, the ``resources: { en: enResource }``
init at line 264); there is no i18next-http-backend plugin, no ``loadPath``,
and nothing under frontend/src fetches these routes. So the two catalogues are
separate: roughly four hundred backend keys here, tens of thousands of UI keys
in frontend/src/app/locales/*.ts, and a key belongs to whichever side renders it.

That matters because reading this the other way invites someone to translate
the whole UI into these files to close a gap that does not exist. What the
backend catalogue is actually for is the strings the backend itself renders
through ``t()`` - validation messages, error text - plus any external client
that wants them.

Module translations are merged with core translations.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.i18n import (
    SUPPORTED_LOCALES,
    get_all_translations,
    get_available_locales,
    is_locale_loaded,
)

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.get("/locales")
async def list_locales() -> dict:
    """List all available languages."""
    return {"locales": get_available_locales()}


@router.get("/locales/{locale}/messages")
@router.get("/locales/{locale}/messages/")
async def get_locale_messages(locale: str) -> dict:
    """Get translation messages for a locale (BUG-API13).

    Mirrors the ``GET /i18n/{locale}`` endpoint but at the
    ``/i18n/locales/{code}/messages/`` path expected by
    ``i18next-http-backend`` and consumers that follow the
    ``/locales/{code}/messages`` convention. Returns 404 for unsupported
    locale codes; supplies the English fallback (with ``_meta.fallback``)
    for supported but unloaded locales.
    """
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"Locale '{locale}' is not supported. Supported codes: {', '.join(SUPPORTED_LOCALES)}"),
        )
    translations = get_all_translations(locale)
    meta: dict[str, object] = {"locale": locale, "fallback": not is_locale_loaded(locale)}
    if meta["fallback"]:
        meta["fallback_locale"] = "en"
    return {"_meta": meta, **translations}


@router.get("/{locale}")
async def get_translations(locale: str) -> dict:
    """Get all backend translations for a locale.

    Shaped for an i18next-http-backend style client, though this product's own
    frontend does not use one - see the module docstring.

    Returns 404 for unsupported locale codes. For supported locales whose
    bundle hasn't been loaded yet we still serve the English fallback but
    flag it explicitly via ``_meta.fallback`` so the client can surface a
    "translation incomplete" indicator instead of pretending the target
    language is complete.
    """
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Locale '{locale}' is not supported",
        )
    translations = get_all_translations(locale)
    meta: dict[str, object] = {"locale": locale, "fallback": not is_locale_loaded(locale)}
    if meta["fallback"]:
        meta["fallback_locale"] = "en"
    return {"_meta": meta, **translations}
