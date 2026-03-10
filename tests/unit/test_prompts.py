from __future__ import annotations

from src.agent.prompts import (
    SYSTEM_PROMPT,
    build_property_list,
    build_scope_instructions,
    format_context,
    format_history,
)


class TestBuildPropertyList:
    def test_contains_all_regions(self):
        result = build_property_list()
        assert "Franschhoek" in result
        assert "Cape Town" in result
        assert "Addo" in result
        assert "Grahamstown" in result
        assert "Salem" in result
        assert "Kenton On Sea" in result

    def test_contains_key_properties(self):
        result = build_property_list()
        assert "La Fontaine" in result
        assert "Avondrood" in result
        assert "POD Camps Bay" in result
        assert "Blackheath Lodge" in result
        assert "Camp Figtree" in result

    def test_does_not_contain_shared(self):
        result = build_property_list()
        assert "shared" not in result.lower() or "Shared" not in result


class TestBuildScopeInstructions:
    def test_property_scope_includes_contact(self):
        result = build_scope_instructions(
            "property",
            property_name="Avondrood",
            location="Franschhoek",
            email="test@avondrood.co.za",
            phone="+27 21 876 2151",
        )
        assert "Avondrood" in result
        assert "test@avondrood.co.za" in result
        assert "+27 21 876 2151" in result

    def test_property_sparse_scope(self):
        result = build_scope_instructions(
            "property",
            property_name="Pleasance",
            location="Grahamstown",
            is_sparse=True,
        )
        assert "limited documented information" in result
        assert "Pleasance" in result

    def test_property_normal_scope(self):
        result = build_scope_instructions(
            "property",
            property_name="La Fontaine",
            location="Franschhoek",
        )
        assert "limited" not in result
        assert "La Fontaine" in result

    def test_no_context_scope_has_discovery(self):
        result = build_scope_instructions("unknown_scope")
        assert "Franschhoek (Wine Country)" in result
        assert "Cape Town (City & Beach)" in result
        assert "Addo (Safari)" in result

    def test_region_scope(self):
        result = build_scope_instructions("region", region="Cape Town")
        assert "Cape Town" in result

    def test_cross_property_scope(self):
        result = build_scope_instructions("cross_property", property_names="La Fontaine, Avondrood")
        assert "La Fontaine, Avondrood" in result

    def test_group_scope(self):
        result = build_scope_instructions("group")
        assert "Oyster Collection as a whole" in result


class TestFormatContext:
    def test_empty_chunks(self):
        assert format_context([]) == "No relevant documents found."

    def test_basic_chunk(self):
        chunks = [{"source_file": "rates.pdf", "content": "R500 per night"}]
        result = format_context(chunks)
        assert "Source: rates.pdf" in result
        assert "R500 per night" in result

    def test_rich_citation_with_section_and_page(self):
        chunks = [
            {
                "source_file": "menu.pdf",
                "content": "Steak R250",
                "metadata": {
                    "section_title": "Dinner Menu",
                    "page_number": 3,
                },
            }
        ]
        result = format_context(chunks)
        assert "Source: menu.pdf" in result
        assert "Section: Dinner Menu" in result
        assert "Page 3" in result

    def test_section_without_page(self):
        chunks = [
            {
                "source_file": "info.pdf",
                "content": "Check-in at 2pm",
                "metadata": {"section_title": "Policies", "page_number": None},
            }
        ]
        result = format_context(chunks)
        assert "Section: Policies" in result
        assert "Page" not in result

    def test_no_metadata(self):
        chunks = [{"source_file": "file.pdf", "content": "text"}]
        result = format_context(chunks)
        assert "Source: file.pdf" in result
        assert "Section" not in result

    def test_multiple_chunks_separated(self):
        chunks = [
            {"source_file": "a.pdf", "content": "AAA"},
            {"source_file": "b.pdf", "content": "BBB"},
        ]
        result = format_context(chunks)
        assert "---" in result
        assert "Document 1" in result
        assert "Document 2" in result


class TestFormatHistory:
    def test_empty(self):
        assert format_history([]) == "No previous conversation."

    def test_formats_messages(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = format_history(history)
        assert "User: Hello" in result
        assert "Assistant: Hi there!" in result

    def test_returns_10_messages(self):
        """Should include last 10 messages, not 6."""
        history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
        result = format_history(history)
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 10

    def test_short_history_all_included(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = format_history(history)
        assert "hello" in result
        assert "hi there" in result


class TestSystemPrompt:
    """System prompt content tests."""

    def test_conversation_continuity_section(self):
        """Prompt should contain conversation continuity instructions."""
        assert "Conversation Continuity" in SYSTEM_PROMPT

    def test_contact_escalation_rule(self):
        """Prompt should limit 'contact directly' usage."""
        assert "Contact Escalation" in SYSTEM_PROMPT

    def test_context_and_history(self):
        """Prompt should reference both context AND conversation history."""
        assert "context documents AND conversation history" in SYSTEM_PROMPT
