from __future__ import annotations

from src.domain.properties import (
    PROPERTY_REGISTRY,
    REGION_PROPERTIES,
    PropertyID,
    Region,
    get_properties_for_region,
    get_property_info,
    list_properties,
    resolve_property_id,
)


class TestPropertyRegistry:
    def test_registry_has_12_properties(self):
        # SHARED is a special value, not a real property
        real_properties = [p for p in PROPERTY_REGISTRY if p != PropertyID.SHARED]
        assert len(real_properties) == 12

    def test_all_properties_have_aliases(self):
        for pid, info in PROPERTY_REGISTRY.items():
            if pid == PropertyID.SHARED:
                continue
            assert len(info.aliases) > 0, f"{pid} has no aliases"

    def test_all_properties_have_kb_folders(self):
        for pid, info in PROPERTY_REGISTRY.items():
            if pid == PropertyID.SHARED:
                continue
            assert len(info.kb_folders) > 0, f"{pid} has no kb_folders"

    def test_franschhoek_has_3_properties(self):
        props = get_properties_for_region(Region.FRANSCHHOEK)
        assert len(props) == 3
        assert PropertyID.LA_FONTAINE in props
        assert PropertyID.AVONDROOD in props
        assert PropertyID.PINK_DOOR in props

    def test_cape_town_has_2_properties(self):
        props = get_properties_for_region(Region.CAPE_TOWN)
        assert len(props) == 2

    def test_all_6_regions_exist(self):
        assert len(REGION_PROPERTIES) == 6


class TestResolvePropertyId:
    def test_exact_alias_match(self):
        assert resolve_property_id("la fontaine") == PropertyID.LA_FONTAINE
        assert resolve_property_id("avondrood") == PropertyID.AVONDROOD
        assert resolve_property_id("pod camps bay") == PropertyID.POD_CAMPS_BAY

    def test_case_insensitive(self):
        assert resolve_property_id("La Fontaine") == PropertyID.LA_FONTAINE
        assert resolve_property_id("AVONDROOD") == PropertyID.AVONDROOD

    def test_whitespace_stripped(self):
        assert resolve_property_id("  la fontaine  ") == PropertyID.LA_FONTAINE

    def test_no_match_returns_none(self):
        assert resolve_property_id("random hotel") is None
        assert resolve_property_id("") is None

    def test_8a_resolves(self):
        assert resolve_property_id("8a") == PropertyID.EIGHT_A


class TestGetPropertyInfo:
    def test_returns_info(self):
        info = get_property_info(PropertyID.CAMP_FIGTREE)
        assert info is not None
        assert info.name == "Camp Figtree"
        assert info.region == Region.ADDO

    def test_none_for_invalid(self):
        assert get_property_info("nonexistent") is None


class TestListProperties:
    def test_returns_12_properties(self):
        props = list_properties()
        assert len(props) == 12

    def test_each_has_required_fields(self):
        for p in list_properties():
            assert "id" in p
            assert "name" in p
            assert "region" in p
