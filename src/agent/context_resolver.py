from __future__ import annotations

import structlog

from src.agent.session import SessionData
from src.domain.entities import extract_entities
from src.domain.properties import (
    PROPERTY_REGISTRY,
    PropertyID,
    Region,
    get_properties_for_region,
)
from src.domain.schemas import QueryScope

logger = structlog.get_logger()


class ResolvedContext:
    """Result of progressive context resolution."""

    def __init__(
        self,
        scope: QueryScope,
        *,
        property_id: PropertyID | None = None,
        property_ids: list[PropertyID] | None = None,
        region: Region | None = None,
    ):
        self.scope = scope
        self.property_id = property_id
        self.property_ids = property_ids or []
        self.region = region


def resolve_context(
    message: str,
    *,
    request_property_id: PropertyID | None = None,
    session: SessionData | None = None,
) -> ResolvedContext:
    """Progressive context resolution.

    Priority order:
    1. Explicit request property_id parameter
    2. Property/region detected in message text
    3. Session's active_property (conversation continuity)
    4. Session's active_region (region continuity)
    5. Group-level (collection-wide query)

    Comparison queries are detected and handled specially.
    Single-property regions auto-promote to PROPERTY scope.
    """
    entities = extract_entities(message)

    # 1. Explicit property_id from request
    if request_property_id and request_property_id != PropertyID.SHARED:
        region = _get_region(request_property_id)
        logger.debug("context_from_request", property_id=str(request_property_id))
        return ResolvedContext(
            scope=QueryScope.PROPERTY,
            property_id=request_property_id,
            property_ids=[request_property_id],
            region=region,
        )

    # 2. Comparison detected
    if entities.is_comparison and entities.is_multi_property:
        logger.debug(
            "context_comparison",
            properties=[str(p) for p in entities.properties],
        )
        return ResolvedContext(
            scope=QueryScope.CROSS_PROPERTY,
            property_ids=entities.properties,
            region=_get_region(entities.properties[0]) if entities.properties else None,
        )

    # 3. Single property in message
    if entities.has_property and len(entities.properties) == 1:
        pid = entities.properties[0]
        region = _get_region(pid)
        logger.debug("context_from_message_property", property_id=str(pid))
        return ResolvedContext(
            scope=QueryScope.PROPERTY,
            property_id=pid,
            property_ids=[pid],
            region=region,
        )

    # 4. Multiple properties in message (not comparison)
    if entities.has_property and len(entities.properties) > 1:
        logger.debug(
            "context_multi_property",
            properties=[str(p) for p in entities.properties],
        )
        return ResolvedContext(
            scope=QueryScope.CROSS_PROPERTY,
            property_ids=entities.properties,
        )

    # 5. Region in message — auto-promote single-property regions
    if entities.has_region:
        region = entities.regions[0]
        region_pids = get_properties_for_region(region)
        if len(region_pids) == 1:
            # Single-property region: auto-promote to PROPERTY scope
            pid = region_pids[0]
            logger.debug(
                "context_region_auto_promote",
                region=str(region),
                property_id=str(pid),
            )
            return ResolvedContext(
                scope=QueryScope.PROPERTY,
                property_id=pid,
                property_ids=[pid],
                region=region,
            )
        logger.debug("context_from_region", region=str(region))
        return ResolvedContext(
            scope=QueryScope.REGION,
            property_ids=region_pids,
            region=region,
        )

    # 6. Session continuity — use active_property
    if session and session.active_property:
        try:
            pid = PropertyID(session.active_property)
            region = _get_region(pid)
            logger.debug("context_from_session", property_id=str(pid))
            return ResolvedContext(
                scope=QueryScope.PROPERTY,
                property_id=pid,
                property_ids=[pid],
                region=region,
            )
        except ValueError:
            pass

    # 6b. Session continuity — use active_region
    if session and session.active_region:
        try:
            region = Region(session.active_region)
            region_pids = get_properties_for_region(region)
            if len(region_pids) == 1:
                pid = region_pids[0]
                logger.debug(
                    "context_session_region_promote",
                    region=str(region),
                    property_id=str(pid),
                )
                return ResolvedContext(
                    scope=QueryScope.PROPERTY,
                    property_id=pid,
                    property_ids=[pid],
                    region=region,
                )
            logger.debug("context_from_session_region", region=str(region))
            return ResolvedContext(
                scope=QueryScope.REGION,
                property_ids=region_pids,
                region=region,
            )
        except ValueError:
            pass

    # 7. Fallback — group-level (whole collection)
    logger.debug("context_group_fallback")
    return ResolvedContext(scope=QueryScope.GROUP)


def _get_region(property_id: PropertyID) -> Region | None:
    """Look up region for a property."""
    info = PROPERTY_REGISTRY.get(property_id)
    return info.region if info else None
