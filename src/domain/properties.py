from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class Region(StrEnum):
    """Geographic regions for The Oyster Collection properties."""

    FRANSCHHOEK = "franschhoek"
    CAPE_TOWN = "cape_town"
    ADDO = "addo"
    GRAHAMSTOWN = "grahamstown"
    SALEM = "salem"
    KENTON_ON_SEA = "kenton_on_sea"


class PropertyID(StrEnum):
    """Unique identifier for each Oyster Collection property."""

    LA_FONTAINE = "la_fontaine"
    AVONDROOD = "avondrood"
    PINK_DOOR = "pink_door"
    POD_CAMPS_BAY = "pod_camps_bay"
    BLACKHEATH_LODGE = "blackheath_lodge"
    CAMP_FIGTREE = "camp_figtree"
    THE_MILNER = "the_milner"
    EIGHT_A = "8a"
    PLEASANCE = "pleasance"
    BURLINGTON_BUSH = "burlington_bush"
    OYSTER_BOX = "oyster_box"
    KENTON_HOUSES = "kenton_houses"

    # Special value for shared/collection-wide docs
    SHARED = "shared"


class PropertyInfo(BaseModel):
    """Metadata for an Oyster Collection property."""

    id: PropertyID
    name: str
    full_name: str
    region: Region
    location: str
    aliases: list[str]
    kb_folders: list[str]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

PROPERTY_REGISTRY: dict[PropertyID, PropertyInfo] = {
    PropertyID.LA_FONTAINE: PropertyInfo(
        id=PropertyID.LA_FONTAINE,
        name="La Fontaine",
        full_name="La Fontaine Restaurant & Guest House",
        region=Region.FRANSCHHOEK,
        location="Franschhoek, Western Cape",
        aliases=[
            "la fontaine",
            "lafontaine",
            "la fontain",
            "fontaine",
            "la fontaine restaurant",
        ],
        kb_folders=["La Fontaine", "Franschhoek"],
    ),
    PropertyID.AVONDROOD: PropertyInfo(
        id=PropertyID.AVONDROOD,
        name="Avondrood",
        full_name="Avondrood Guest House",
        region=Region.FRANSCHHOEK,
        location="Franschhoek, Western Cape",
        aliases=[
            "avondrood",
            "avondrood guest house",
            "avondrod",
        ],
        kb_folders=["Avondrood", "Franschhoek"],
    ),
    PropertyID.PINK_DOOR: PropertyInfo(
        id=PropertyID.PINK_DOOR,
        name="The Pink Door",
        full_name="The Pink Door Guest House",
        region=Region.FRANSCHHOEK,
        location="Franschhoek, Western Cape",
        aliases=[
            "pink door",
            "the pink door",
            "pinkdoor",
        ],
        kb_folders=["The Pink Door", "Franschhoek"],
    ),
    PropertyID.POD_CAMPS_BAY: PropertyInfo(
        id=PropertyID.POD_CAMPS_BAY,
        name="POD Camps Bay",
        full_name="POD Camps Bay",
        region=Region.CAPE_TOWN,
        location="Camps Bay, Cape Town",
        aliases=[
            "pod",
            "pod camps bay",
            "camps bay",
            "pod camps",
        ],
        kb_folders=["POD Camps Bay", "Cape Town"],
    ),
    PropertyID.BLACKHEATH_LODGE: PropertyInfo(
        id=PropertyID.BLACKHEATH_LODGE,
        name="Blackheath Lodge",
        full_name="Blackheath Lodge",
        region=Region.CAPE_TOWN,
        location="Sea Point, Cape Town",
        aliases=[
            "blackheath",
            "blackheath lodge",
            "black heath",
        ],
        kb_folders=["Blackheath Lodge", "Cape Town"],
    ),
    PropertyID.CAMP_FIGTREE: PropertyInfo(
        id=PropertyID.CAMP_FIGTREE,
        name="Camp Figtree",
        full_name="Camp Figtree",
        region=Region.ADDO,
        location="Addo, Eastern Cape",
        aliases=[
            "camp figtree",
            "figtree",
            "fig tree",
            "camp fig tree",
        ],
        kb_folders=["Camp Figtree", "Addo"],
    ),
    PropertyID.THE_MILNER: PropertyInfo(
        id=PropertyID.THE_MILNER,
        name="The Milner",
        full_name="The Milner Hotel",
        region=Region.GRAHAMSTOWN,
        location="Makhanda (Grahamstown), Eastern Cape",
        aliases=[
            "the milner",
            "milner",
            "milner hotel",
        ],
        kb_folders=["The Milner", "Grahamstown"],
    ),
    PropertyID.EIGHT_A: PropertyInfo(
        id=PropertyID.EIGHT_A,
        name="8A Guest House",
        full_name="8A Guest House",
        region=Region.GRAHAMSTOWN,
        location="Makhanda (Grahamstown), Eastern Cape",
        aliases=[
            "8a",
            "8a guest house",
            "eight a",
            "8 a",
        ],
        kb_folders=["8A", "Grahamstown"],
    ),
    PropertyID.PLEASANCE: PropertyInfo(
        id=PropertyID.PLEASANCE,
        name="Pleasance",
        full_name="Pleasance",
        region=Region.GRAHAMSTOWN,
        location="Makhanda (Grahamstown), Eastern Cape",
        aliases=[
            "pleasance",
            "the pleasance",
        ],
        kb_folders=["Pleasance", "Grahamstown"],
    ),
    PropertyID.BURLINGTON_BUSH: PropertyInfo(
        id=PropertyID.BURLINGTON_BUSH,
        name="Burlington Bush",
        full_name="Burlington Bush Cottages",
        region=Region.SALEM,
        location="Salem, Eastern Cape",
        aliases=[
            "burlington",
            "burlington bush",
            "burlington bush cottages",
        ],
        kb_folders=["Burlington Bush", "Salem"],
    ),
    PropertyID.OYSTER_BOX: PropertyInfo(
        id=PropertyID.OYSTER_BOX,
        name="Oyster Box Beach House",
        full_name="Oyster Box Beach House",
        region=Region.KENTON_ON_SEA,
        location="Kenton-on-Sea, Eastern Cape",
        aliases=[
            "oyster box",
            "oyster box beach house",
            "beach house",
        ],
        kb_folders=["Oyster Box", "Kenton-on-Sea"],
    ),
    PropertyID.KENTON_HOUSES: PropertyInfo(
        id=PropertyID.KENTON_HOUSES,
        name="Kenton Houses",
        full_name="Kenton Houses",
        region=Region.KENTON_ON_SEA,
        location="Kenton-on-Sea, Eastern Cape",
        aliases=[
            "kenton houses",
            "kenton house",
        ],
        kb_folders=["Kenton Houses", "Kenton-on-Sea"],
    ),
}


# --------------------------------------------------------------------------- #
# Lookup helpers
# --------------------------------------------------------------------------- #

# Pre-built alias → PropertyID index for O(1) lookup
_ALIAS_INDEX: dict[str, PropertyID] = {}
for _pid, _info in PROPERTY_REGISTRY.items():
    for _alias in _info.aliases:
        _ALIAS_INDEX[_alias.lower()] = _pid


# Pre-built region → list[PropertyID] index
REGION_PROPERTIES: dict[Region, list[PropertyID]] = {}
for _pid, _info in PROPERTY_REGISTRY.items():
    REGION_PROPERTIES.setdefault(_info.region, []).append(_pid)


# Region name aliases for entity extraction
REGION_ALIASES: dict[str, Region] = {
    "franschhoek": Region.FRANSCHHOEK,
    "cape town": Region.CAPE_TOWN,
    "addo": Region.ADDO,
    "grahamstown": Region.GRAHAMSTOWN,
    "makhanda": Region.GRAHAMSTOWN,
    "salem": Region.SALEM,
    "kenton": Region.KENTON_ON_SEA,
    "kenton-on-sea": Region.KENTON_ON_SEA,
    "kenton on sea": Region.KENTON_ON_SEA,
}


def resolve_property_id(text: str) -> PropertyID | None:
    """Resolve text to a PropertyID via exact alias match.

    Returns None if no match found (does NOT do substring matching to avoid
    the prototype bug where 'la fontaine' matched before 'avondrood').
    """
    return _ALIAS_INDEX.get(text.lower().strip())


def get_property_info(property_id: PropertyID) -> PropertyInfo | None:
    """Get property metadata by ID."""
    return PROPERTY_REGISTRY.get(property_id)


def get_properties_for_region(region: Region) -> list[PropertyID]:
    """Get all property IDs in a region."""
    return REGION_PROPERTIES.get(region, [])


def list_properties() -> list[dict]:
    """Return summary list of all properties."""
    return [
        {
            "id": info.id,
            "name": info.name,
            "full_name": info.full_name,
            "region": info.region,
            "location": info.location,
        }
        for info in PROPERTY_REGISTRY.values()
        if info.id != PropertyID.SHARED
    ]
