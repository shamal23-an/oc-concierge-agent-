"""Streamlit chat UI for the Oyster Collection AI Concierge.

Talks to the FastAPI /chat endpoint. Run with:
    make run-ui
    # or: uv run streamlit run src/channels/streamlit_app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# Load .env from project root (same file FastAPI uses)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

# ── Configuration ─────────────────────────────────────────────────────────── #

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

BRAND_GOLD = "#9E8962"

# ── Page setup ────────────────────────────────────────────────────────────── #

st.set_page_config(
    page_title="Oyster Collection Concierge",
    page_icon="🦪",
    layout="centered",
)

# Custom CSS for polish
st.markdown(
    f"""
    <style>
    /* Brand header bar */
    .brand-header {{
        background-color: {BRAND_GOLD};
        padding: 18px 14px;
        border-radius: 10px;
        margin-bottom: 4px;
        text-align: center;
    }}
    .brand-header img {{
        width: 100%;
        max-width: 280px;
    }}

    /* Metadata pills */
    .meta-pill {{
        display: inline-block;
        background: #F5F2ED;
        color: #6B5B3E;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75em;
        margin-right: 6px;
        margin-top: 4px;
    }}
    .meta-pill.cached {{
        background: #E8F5E9;
        color: #2E7D32;
    }}

    /* Source list */
    .source-item {{
        font-size: 0.8em;
        color: #666;
        padding: 2px 0;
    }}

    /* Welcome banner */
    .welcome-box {{
        background: linear-gradient(135deg, #F5F2ED 0%, #FFFFFF 100%);
        border-left: 4px solid {BRAND_GOLD};
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
    }}
    .welcome-box h3 {{
        color: {BRAND_GOLD};
        margin-top: 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helper functions ──────────────────────────────────────────────────────── #


@st.cache_data(ttl=300)
def fetch_properties() -> list[dict]:
    """Fetch property list from the API (cached 5 min)."""
    try:
        resp = requests.get(f"{API_BASE_URL}/properties", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return []


def check_api_health() -> bool:
    """Quick health check against the API."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=3)
        data = resp.json()
        return data.get("status") == "healthy"
    except requests.RequestException:
        return False


def send_message(
    message: str,
    *,
    property_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Send a chat message to the API and return the response."""
    payload: dict = {"message": message}
    if property_id:
        payload["property_id"] = property_id
    if session_id:
        payload["session_id"] = session_id

    resp = requests.post(
        f"{API_BASE_URL}/chat",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _render_metadata(scope: str | None, property_id: str | None, cached: bool) -> None:
    """Render scope/property/cache as styled pills below a response."""
    pills = []
    if scope:
        pills.append(f'<span class="meta-pill">{scope}</span>')
    if property_id:
        label = property_id.replace("_", " ").title()
        pills.append(f'<span class="meta-pill">{label}</span>')
    if cached:
        pills.append('<span class="meta-pill cached">⚡ Cached</span>')
    if pills:
        st.markdown(" ".join(pills), unsafe_allow_html=True)


def _render_sources(sources: list[str]) -> None:
    """Render source citations in a clean expandable section."""
    if not sources:
        return
    with st.expander(f"📄 {len(sources)} source(s) referenced"):
        for source in sources:
            st.markdown(
                f'<div class="source-item">📎 {source}</div>',
                unsafe_allow_html=True,
            )


# ── Session state initialisation ──────────────────────────────────────────── #

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = None

# ── Sidebar ───────────────────────────────────────────────────────────────── #

with st.sidebar:
    st.markdown(
        """
        <div class="brand-header">
            <img src="https://www.oystercollection.co.za/wp-content/uploads/2023/07/The-Oyster-Collection-1536x609.png"
            />
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("AI Concierge")

    st.divider()

    # API health indicator
    api_healthy = check_api_health()
    if api_healthy:
        st.success("API Connected", icon="✅")
    else:
        st.error("API Unavailable", icon="❌")
        st.caption("Start the API: `uv run uvicorn src.api.app:app --reload --port 8000`")

    st.divider()

    # Property selector
    properties = fetch_properties()
    property_options = {"🏠 All Properties": None}
    for prop in properties:
        label = f"{prop['full_name']} — {prop['location']}"
        property_options[label] = prop["id"]

    selected_label = st.selectbox(
        "Ask about a specific property",
        options=list(property_options.keys()),
        help="Select a property for focused answers, "
        "or leave as 'All Properties' for general questions",
    )
    selected_property_id = property_options[selected_label]

    st.divider()

    # New conversation button
    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    # Session info
    if st.session_state.session_id:
        st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

    st.divider()

    st.markdown(
        "**Try asking about:**\n"
        "- Rates and room types\n"
        "- Restaurant recommendations\n"
        "- Activities and excursions\n"
        "- Spa menus and treatments\n"
        "- Directions and transfers\n"
    )

# ── Main chat area ────────────────────────────────────────────────────────── #

# Welcome message when no conversation yet
if not st.session_state.messages:
    st.markdown(
        """
        <div class="welcome-box">
            <h3>Welcome to The Oyster Collection</h3>
            <p>I'm your AI concierge — I can help you with information about our
            <strong>12 boutique properties</strong> across South Africa.</p>
            <p>Ask me about rates, restaurants, activities, spa treatments, directions,
            or anything else about your stay. Select a property from the sidebar for
            focused answers, or ask about any property by name.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            _render_sources(msg.get("sources", []))
            _render_metadata(msg.get("scope"), msg.get("property_id"), msg.get("cached", False))

# ── Chat input ────────────────────────────────────────────────────────────── #

if prompt := st.chat_input(
    "Ask me anything about The Oyster Collection...",
    disabled=not api_healthy,
):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Send to API and display response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                data = send_message(
                    prompt,
                    property_id=selected_property_id,
                    session_id=st.session_state.session_id,
                )

                response_text = data.get("response", "Sorry, something went wrong.")
                sources = data.get("sources", [])
                scope = data.get("scope")
                property_id = data.get("property_id")
                cached = data.get("cached", False)

                # Update session_id from API response
                if data.get("session_id"):
                    st.session_state.session_id = data["session_id"]

                st.markdown(response_text)
                _render_sources(sources)
                _render_metadata(scope, property_id, cached)

                # Save assistant message to history
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "sources": sources,
                        "scope": scope,
                        "property_id": property_id,
                        "cached": cached,
                    }
                )

            except requests.ConnectionError:
                st.error(
                    "Could not connect to the API. "
                    "Make sure it's running with "
                    "`uv run uvicorn src.api.app:app --reload --port 8000`."
                )
            except requests.Timeout:
                st.error("The request timed out. Please try again.")
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    st.warning(
                        "Your previous message is still being processed. "
                        "Please wait a moment and try again."
                    )
                else:
                    st.error(f"API error: {e}")
            except requests.RequestException as e:
                st.error(f"Request failed: {e}")
