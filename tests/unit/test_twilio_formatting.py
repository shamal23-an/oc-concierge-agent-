from __future__ import annotations

from src.channels.twilio_whatsapp import _format_for_whatsapp, _split_messages


class TestFormatForWhatsapp:
    """WhatsApp formatting conversion tests."""

    def test_markdown_headers_to_bold(self):
        assert _format_for_whatsapp("### Room Types") == "*Room Types*"
        assert _format_for_whatsapp("## Rates") == "*Rates*"

    def test_double_star_to_single(self):
        assert _format_for_whatsapp("**Camp Figtree**") == "*Camp Figtree*"

    def test_horizontal_rule_removed(self):
        result = _format_for_whatsapp("above\n---\nbelow")
        assert "---" not in result
        assert "above" in result
        assert "below" in result

    def test_bullet_dash_to_bullet(self):
        result = _format_for_whatsapp("- First item\n- Second item")
        assert "\u2022 First item" in result
        assert "\u2022 Second item" in result

    def test_citations_removed(self):
        result = _format_for_whatsapp("Great rates! [Source: rates.pdf \u2014 Page 2]")
        assert "[Source:" not in result
        assert "Great rates!" in result

    def test_triple_newlines_collapsed(self):
        result = _format_for_whatsapp("first\n\n\n\nsecond")
        assert "\n\n\n" not in result
        assert "first" in result
        assert "second" in result

    def test_combined_formatting(self):
        text = (
            "### Camp Figtree Rates\n\n**The Outpost Suite**"
            "\n- R2,500 per night\n---\n[Source: rates.pdf]"
        )
        result = _format_for_whatsapp(text)
        assert "###" not in result
        assert "**" not in result
        assert "---" not in result
        assert "[Source:" not in result
        assert "*Camp Figtree Rates*" in result


class TestSplitMessages:
    """Message splitting for WhatsApp length limits."""

    def test_short_not_split(self):
        text = "Hello, welcome to The Oyster Collection!"
        parts = _split_messages(text)
        assert len(parts) == 1
        assert parts[0] == text

    def test_long_message_split(self):
        # Create a message longer than 1500 chars
        text = ("This is a paragraph about rates. " * 20 + "\n\n") * 5
        parts = _split_messages(text.strip())
        assert len(parts) >= 2
        for part in parts:
            assert len(part) <= 1500

    def test_split_preserves_content(self):
        text = "Part one content.\n\nPart two content.\n\nPart three content."
        parts = _split_messages(text, max_len=30)
        combined = " ".join(parts)
        assert "Part one" in combined
        assert "Part two" in combined
        assert "Part three" in combined
