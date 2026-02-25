from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.properties import PropertyID
from src.domain.schemas import ChatRequest, ChatResponse, QueryScope


class TestChatRequest:
    def test_minimal_request(self):
        req = ChatRequest(message="Hello")
        assert req.message == "Hello"
        assert req.property_id is None
        assert req.session_id is None

    def test_full_request(self):
        req = ChatRequest(
            message="What restaurants?",
            property_id=PropertyID.LA_FONTAINE,
            session_id="abc-123",
        )
        assert req.property_id == PropertyID.LA_FONTAINE

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_property_id_optional(self):
        req = ChatRequest(message="Tell me about the collection")
        assert req.property_id is None


class TestChatResponse:
    def test_basic_response(self):
        resp = ChatResponse(
            response="Welcome!",
            session_id="abc",
        )
        assert resp.sources == []
        assert resp.cached is False

    def test_full_response(self):
        resp = ChatResponse(
            response="Here are restaurants...",
            session_id="abc",
            property_id=PropertyID.AVONDROOD,
            scope=QueryScope.PROPERTY,
            sources=["Avondrood Recommends.pdf"],
            cached=True,
        )
        assert resp.scope == QueryScope.PROPERTY
        assert len(resp.sources) == 1


class TestQueryScope:
    def test_all_scopes_exist(self):
        assert QueryScope.PROPERTY == "property"
        assert QueryScope.REGION == "region"
        assert QueryScope.GROUP == "group"
        assert QueryScope.CROSS_PROPERTY == "cross_property"
        assert QueryScope.CLARIFY == "clarify"
