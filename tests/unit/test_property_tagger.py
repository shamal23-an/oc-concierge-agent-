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


class TestTradePortalTagging:
    """Test Trade-Portal folder structure handling."""

    KB_ROOT = Path("/kb")

    def test_numbered_folder_la_fontaine(self):
        """Trade-Portal numbered folder: '1. La Fontaine - Franschhoek'."""
        path = Path("/kb/Properties/1. La Fontaine - Franschhoek/LF Brochure.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.LA_FONTAINE]

    def test_numbered_folder_avondrood(self):
        path = Path("/kb/Properties/2. Avondrood - Franschhoek/Avondrood Brochure.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.AVONDROOD]

    def test_numbered_folder_pink_door(self):
        path = Path("/kb/Properties/3. Pink Door Franschhoek Owner's Villa/Brochure/intro.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.PINK_DOOR]

    def test_numbered_folder_pod(self):
        path = Path("/kb/Properties/4. POD Camps Bay - Cape Town/POD Fact Sheet 2025.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.POD_CAMPS_BAY]

    def test_numbered_folder_blackheath(self):
        path = Path(
            "/kb/Properties/5. Blackheath Lodge - Cape Town, Sea Point/"
            "Blackheath Lodge Information Guide.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.BLACKHEATH_LODGE]

    def test_numbered_folder_camp_figtree(self):
        path = Path("/kb/Properties/6. Camp Figtree - Addo/Camp Figtree Brochure.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.CAMP_FIGTREE]

    def test_numbered_folder_milner(self):
        path = Path("/kb/Properties/7. The Milner - Grahamstown/The Milner Information Guide.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.THE_MILNER]

    def test_numbered_folder_8a(self):
        path = Path("/kb/Properties/8. 8A - Grahamstown/8A Information Guide.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.EIGHT_A]

    def test_numbered_folder_burlington(self):
        path = Path(
            "/kb/Properties/10. Burlington Bush Cottages - Salem/"
            "Burlington Bush Cottages Brochure.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.BURLINGTON_BUSH]

    def test_rates_subfolder_la_fontaine(self):
        """Rate subfolder: 'Rates - La Fontaine'."""
        path = Path(
            "/kb/Rates/Rates - La Fontaine/" "RACK Rates La Fontaine Oct 2025 - 08 Jan 2027.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.LA_FONTAINE]

    def test_rates_subfolder_pod(self):
        path = Path("/kb/Rates/Rates - POD Camps Bay/" "POD Rack Rates (2025 - 2026).pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.POD_CAMPS_BAY]

    def test_rates_subfolder_blackheath(self):
        path = Path(
            "/kb/Rates/Rates - Blackheath Lodge/"
            "RACK Rates Blackheath Lodge Oct 2025 -08 January 2027.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.BLACKHEATH_LODGE]

    def test_rates_subfolder_avondrood_no_space(self):
        """'Rates- Avondrood' (no space before dash)."""
        path = Path("/kb/Rates/Rates- Avondrood/" "RACK Rates Avondrood Oct 2025 - 08 Jan 2027.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.AVONDROOD]

    def test_rates_subfolder_camp_figtree(self):
        """Rate subfolder with correct spelling should match."""
        path = Path("/kb/Rates/Rates - Camp Figtree/" "CFT Rates 2025 -Jan 2027.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.CAMP_FIGTREE]

    def test_rates_subfolder_camp_figtree_typo(self):
        """Real-world typo 'Figtee' — now matches via 'camp figtee' alias."""
        path = Path("/kb/Rates/Rates - Camp Figtee/" "CFT Rates 2025 -Jan 2027.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        # "Camp Figtee" alias was added to handle this Trade-Portal typo
        assert result == [PropertyID.CAMP_FIGTREE]

    def test_kenton_houses_brochure(self):
        """File in Kenton folder with unique filename."""
        path = Path("/kb/Properties/12. Kenton on Sea Houses/" "Kenton House Comparison.pdf")
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.KENTON_HOUSES]

    def test_kenton_oyster_box_shared_file(self):
        """File mentioning both Oyster Box and Kenton — filename match wins (longest)."""
        path = Path(
            "/kb/Properties/12. Kenton on Sea Houses/"
            "Brochure- Kenton on Sea Homes & Oyster Box Beach House.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        # "oyster box beach house" alias is longest match in filename
        assert result == [PropertyID.OYSTER_BOX]

    def test_oyster_box(self):
        path = Path(
            "/kb/Properties/11. Oyster Box Beach House Owner's Villa/"
            "Oyster Box Beach House Brochure.pdf"
        )
        result = tag_property_ids(path, self.KB_ROOT)
        assert result == [PropertyID.OYSTER_BOX]


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

    def test_brochure(self):
        assert classify_document_type("LF Brochure.pdf") == "brochure"

    def test_fact_sheet(self):
        assert classify_document_type("POD Fact Sheet 2025.pdf") == "fact_sheet"
