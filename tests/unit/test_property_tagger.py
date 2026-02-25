from __future__ import annotations

from pathlib import Path

from src.domain.properties import PropertyID
from src.ingestion.property_tagger import classify_document_type, tag_property_ids


class TestTagPropertyIds:
    """Test the FIXED property tagger that resolves the prototype bug."""

    KB_ROOT = Path("/kb")

    def test_filename_with_property_name(self):
        """File named 'Avondrood Recommends.pdf' → avondrood only."""
        path = Path("/kb/Franschhoek/Avondrood Recommends.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.AVONDROOD]

    def test_filename_with_la_fontaine(self):
        path = Path("/kb/Franschhoek/La Fontaine Menu.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.LA_FONTAINE]

    def test_filename_with_pink_door(self):
        path = Path("/kb/Franschhoek/Pink Door Info.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.PINK_DOOR]

    def test_filename_with_pod(self):
        path = Path("/kb/Cape Town/POD Camps Bay Rates.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.POD_CAMPS_BAY]

    def test_filename_with_blackheath(self):
        path = Path("/kb/Cape Town/Blackheath Lodge Info.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.BLACKHEATH_LODGE]

    def test_property_subfolder(self):
        """File in a property-specific subfolder."""
        path = Path("/kb/Camp Figtree/rates.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.CAMP_FIGTREE]

    def test_region_folder_no_property_in_filename(self):
        """Generic file in region folder → ALL properties in that region."""
        path = Path("/kb/Franschhoek/General Info.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert PropertyID.LA_FONTAINE in result
        assert PropertyID.AVONDROOD in result
        assert PropertyID.PINK_DOOR in result
        assert len(result) == 3

    def test_cape_town_region_fallback(self):
        path = Path("/kb/Cape Town/General Activities.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert PropertyID.POD_CAMPS_BAY in result
        assert PropertyID.BLACKHEATH_LODGE in result

    def test_unknown_folder_returns_shared(self):
        path = Path("/kb/Unknown Folder/random.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.SHARED]

    def test_root_level_file_returns_shared(self):
        path = Path("/kb/company_overview.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.SHARED]

    def test_underscore_filename(self):
        """Underscores in filename should be normalized to spaces for matching."""
        path = Path("/kb/Franschhoek/La_Fontaine_Wine_List.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.LA_FONTAINE]


class TestClassifyDocumentType:
    def test_rates_document(self):
        assert classify_document_type("BHL RACK rates 2024.pdf") == "rates"

    def test_restaurant_menu(self):
        assert classify_document_type("La Fontaine Menu.pdf") == "restaurant"

    def test_activity_document(self):
        assert classify_document_type("Activities and Tours.pdf") == "activity"

    def test_spa_document(self):
        assert classify_document_type("Spa Treatments.pdf") == "spa"

    def test_directions(self):
        assert classify_document_type("Directions to property.pdf") == "directions"

    def test_general_fallback(self):
        assert classify_document_type("random_file.pdf") == "general"

    def test_festive_document(self):
        assert classify_document_type("Festive Season 2024.pdf") == "festive"
