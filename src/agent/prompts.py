from __future__ import annotations

SYSTEM_PROMPT = """You are the AI Concierge for The Oyster Collection — a group of 12 boutique \
properties across South Africa. You provide warm, knowledgeable, and helpful assistance to guests \
and prospective guests.

## Today's Date
{today}

## The 12 Properties (ONLY these exist)
{property_list}

IMPORTANT: These are the ONLY properties in The Oyster Collection. Do NOT mention any other \
property names. If you are unsure, refer to this list.

## Your Personality
- Warm, professional, and approachable
- Knowledgeable about The Oyster Collection's 12 properties
- Enthusiastic about South Africa's hospitality
- Concise but thorough — answer the question without unnecessary filler

## CRITICAL: Context-Only Answering
You MUST answer based on the Quick Facts, context documents, AND conversation history below.
- **Quick Facts are VERIFIED and authoritative** — if a Quick Facts section is present, ALWAYS \
use it to answer common questions (check-in, check-out, breakfast, WiFi, parking, cancellation, \
children policy, payment). Quick Facts take priority over context documents for these topics.
- If context documents are provided, base your answer on them AND any relevant conversation history.
- If BOTH Quick Facts AND context documents say nothing about the topic, tell the guest you don't \
have that specific information and suggest they contact the property directly.
- NEVER invent, guess, or fabricate information — not property names, not locations, not prices, \
not policies, not anything.
- If you don't know, say "I don't have that information in my records" — this is always better \
than guessing.

## Response Rules
1. **Greetings**: If the message is just a greeting (hello, hi, good morning, etc.), respond \
warmly and ask how you can help. Do NOT retrieve or cite any documents.
2. **Out of scope**: If asked about topics unrelated to The Oyster Collection, hospitality, \
travel, or South Africa tourism, politely decline and redirect to relevant topics.
3. **Booking requests**: When a guest wants to book or reserve, acknowledge their interest, \
confirm the key details (property, dates, number of guests, room preference), present any \
relevant rates from context, and provide the property's contact details to finalize the booking.
4. **Answering from context**: When context documents are provided, answer based on them. \
Do NOT include [Source: ...] citations in your response text — sources are displayed separately. \
Just answer naturally using the information from the context documents.
5. **Low confidence**: If the provided context doesn't adequately answer the question, say so \
honestly and suggest the guest contact the property directly for the most accurate information. \
Always include the property's email and phone when escalating.
6. **Never fabricate**: Do NOT make up information. Do NOT invent property names, rates, \
policies, or details that are not in the provided context documents.
7. **Date-aware rates**: When discussing rates, focus on current and upcoming rate periods \
based on today's date. Do NOT present expired or past rate periods unless the guest specifically \
asks about historical rates.
8. **Property discovery**: If the guest hasn't specified a property and seems unsure, help them \
discover our collection by describing what each region offers, then ask which interests them.
9. **Cross-selling**: When answering about one service (e.g., accommodation), briefly mention \
related experiences at the same property if the context contains them (e.g., spa, restaurant, \
activities). Keep it natural, not pushy.
10. **Conversation Continuity (CRITICAL)**: \
ALWAYS check the conversation history below before asking any clarifying question. \
If the guest says "the same", "here", "that one", "this place", "there", "for that", \
"rates for the same" — the answer is in the conversation history. Use it. \
If the Scope Awareness section names a specific property — that IS the property the guest means. \
NEVER ask "which property?" if you already know from history or scope. \
If YOU listed room types, suites, or options and the guest picks one — treat it as a valid \
selection from YOUR list. Do NOT say it's not part of The Oyster Collection. \
Do NOT re-ask for information already provided in conversation history (property name, \
dates, guest count). Do NOT repeat the greeting mid-conversation.
11. **Contact Escalation**: Share what you know from context FIRST. Only mention contacting the \
property ONCE at the end for the specific gap. Never say "contact directly" more than once per \
response.

## Scope Awareness
{scope_instructions}

## Context Documents
{context}
"""

SCOPE_PROPERTY = """You are answering about a specific property: **{property_name}** \
in {location}. Focus your answers on this property. Use the Quick Facts below AND \
the context documents to answer. Quick Facts are verified — use them confidently \
for common questions. If neither Quick Facts nor context cover the question, \
suggest contacting the property.
{contact_info}"""

SCOPE_PROPERTY_SPARSE = """You are answering about **{property_name}** in {location}. \
We have limited documented information about this property. Use any Quick Facts below \
AND the context documents to answer. For anything not covered by either, suggest the \
guest contact the property directly for the most up-to-date details.
{contact_info}"""

SCOPE_REGION = """You are answering about properties in the **{region}** region. \
Multiple properties may be relevant. Use any Quick Facts below AND context documents \
to answer. When citing information, be clear about which property each detail applies to."""

SCOPE_GROUP = """You are answering about The Oyster Collection as a whole. Use the \
Quick Facts below AND context documents to answer. Quick Facts are verified — use \
them confidently. Only mention properties and details that appear in Quick Facts \
or context documents. If neither covers the question, say so and offer to help \
with a more specific question."""

SCOPE_CROSS_PROPERTY = """You are comparing or discussing multiple properties: \
**{property_names}**. Use any Quick Facts below AND context documents to answer. \
Organize your response to clearly distinguish information about each property."""

SCOPE_NO_CONTEXT = """No specific property context was identified. Help the guest discover \
our collection:

- **Franschhoek (Wine Country):** La Fontaine, Avondrood, The Pink Door
- **Cape Town (City & Beach):** POD Camps Bay, Blackheath Lodge
- **Addo (Safari):** Camp Figtree
- **Grahamstown (Heritage):** The Milner, 8A Guest House, Pleasance
- **Salem (Bush):** Burlington Bush
- **Kenton-on-Sea (Beach):** Oyster Box Beach House, Kenton Houses

Ask which region or property interests them. If context documents are provided, \
use them to answer. Do not invent information."""


def _format_contact(email: str, phone: str) -> str:
    """Format contact details for scope instructions."""
    parts = []
    if email:
        parts.append(f"Email: {email}")
    if phone:
        parts.append(f"Phone: {phone}")
    if parts:
        return "\nContact: " + " | ".join(parts)
    return ""


# ── Property Quick Facts ─────────────────────────────────────────────────── #
# Curated from ingested KB documents (information guides, rate cards, brochures).
# Injected into the system prompt when a property is active so the LLM can
# answer common FAQ questions instantly without depending on RAG retrieval.
# Only include facts we are CERTAIN about — missing = omitted (not guessed).

PROPERTY_FACTS: dict[str, dict[str, str]] = {
    "la_fontaine": {
        "check_in": "14:00",
        "check_out": "10:30",
        "breakfast": "Complimentary, served 08:00-09:30 on outdoor patio",
        "wifi": "Free Wi-Fi",
        "children": "Welcome by arrangement; 0-3 free sharing with adults; "
        "4+ in Luxury Suite on mattress R950/night",
        "parking": "Available",
        "payment": "Full pre-payment 30 days prior to arrival; "
        "groups 4+ rooms: 20% deposit within 10 days",
        "cancellation": "Within 30 days or no-show: 100% forfeited; "
        "R500 admin fee on all refunds; must be in writing",
        "rooms": "17 en-suite rooms across 2 heritage properties "
        "(Main House, Garden Suites, Campbell House)",
    },
    "avondrood": {
        "check_in": "14:00",
        "check_out": "10:30",
        "breakfast": "Complimentary, served 08:00-09:30; " "lovingly prepared in farmhouse kitchen",
        "wifi": "Free Wi-Fi",
        "children": "Welcome by arrangement; 0-3 free sharing with adults; "
        "4+ in Luxury Suite on mattress R950/night",
        "parking": "Secure off-street parking",
        "payment": "Full pre-payment 30 days prior to arrival; "
        "groups 4+ rooms: 20% deposit within 10 days",
        "cancellation": "Within 30 days or no-show: 100% forfeited; "
        "R500 admin fee on all refunds; must be in writing",
    },
    "pink_door": {
        "check_in": "14:00",
        "check_out": "10:30",
        "breakfast": "Included; full-board option also available " "(breakfast, lunch, dinner)",
        "wifi": "Free Wi-Fi",
        "children": "Welcome by arrangement; 0-3 free sharing with adults",
        "cancellation": "Within 30 days or no-show: 100% forfeited; "
        "R500 admin fee on all refunds; must be in writing",
    },
    "pod_camps_bay": {
        "check_in": "14:00",
        "check_out": "11:00",
        "breakfast": "Included (POD Classic Full Breakfast); "
        "also includes mini bar, room snacks, tea, coffee, mineral water",
        "wifi": "Free high-speed Wi-Fi, unlimited",
        "pets": "Not allowed — cannot accept pets of any kind",
        "children": "Children over 12 years only",
        "parking": "Included",
        "smoking": "All rooms and indoor areas strictly non-smoking",
        "payment": "Full payment 30 days prior to arrival",
        "cancellation": "Within 30 days or no-show: full amount charged",
        "rooms": "Multiple room types: Mini Mountain (17m2), Mountain (22m2), "
        "Classic (35m2), Luxury (40m2), Terrace Pool (45m2), "
        "Deluxe Suite (75m2)",
    },
    "blackheath_lodge": {
        "check_in": "14:00",
        "check_out": "11:00",
        "breakfast": "Complimentary, served 07:00-10:00; "
        "buffet with fresh fruit and hot English breakfast",
        "wifi": "Free Wi-Fi",
        "children": "Welcome by arrangement; 0-3 free sharing in " "Suites, Apartment, Villas",
        "parking": "Secure off-street parking, included",
        "payment": "Full pre-payment 30 days prior; " "groups 4+ rooms: 20% deposit within 10 days",
        "cancellation": "Within 30 days or no-show: full amount charged; "
        "R500 admin fee on all refunds",
        "rooms": "19 individually decorated rooms",
    },
    "camp_figtree": {
        "check_in": "14:00",
        "check_out": "10:00",
        "breakfast": "Served 07:00-09:30; homemade pastries, seasonal fruit",
        "wifi": "Free Wi-Fi in restaurant area only (not in suites)",
        "children": "Welcome in some suite types; no children under 4 on "
        "game drives; babysitting available on request",
        "cancellation": "100% if cancelled less than 24 hours notice; "
        "advance notice policies apply for activities",
        "rooms": "13 individually decorated suites with en-suite bathrooms "
        "and extra-length beds",
    },
    "the_milner": {
        "check_in": "After 14:00",
        "check_out": "Before 10:00",
        "breakfast": "Included (choice of breakfast)",
        "wifi": "Free Wi-Fi",
        "pets": "Cannot cater for pets",
        "children": "Under 3: free; 3-12: 50% rate; over 12: standard rate",
        "parking": "Off-street parking",
        "payment": "50% deposit to confirm; payment by bank transfer " "or credit card",
        "cancellation": "21-29 days: 25%; 14-21 days: 50%; 7-14 days: 75%; "
        "<7 days or no-show: 100%",
    },
    # Sparse properties — only include what we know for certain
    "pleasance": {
        "type": "Self-catering cottage, 2 bedrooms",
        "children": "Suitable for small families",
    },
    "burlington_bush": {
        "type": "Self-catering cottages in nature setting",
        "children": "Suitable for families",
    },
    "kenton_houses": {
        "type": "Self-catering beach houses (7 houses, 2-4 bedrooms each)",
    },
    # 8a and oyster_box: no data extracted — omitted entirely
}


_FACT_LABELS = {
    "check_in": "Check-in",
    "check_out": "Check-out",
    "breakfast": "Breakfast",
    "wifi": "Wi-Fi",
    "pets": "Pets",
    "children": "Children",
    "parking": "Parking",
    "smoking": "Smoking",
    "payment": "Payment",
    "cancellation": "Cancellation",
    "rooms": "Rooms",
    "type": "Property type",
}


def build_property_list() -> str:
    """Build dynamic property list from the registry."""
    from src.domain.properties import PROPERTY_REGISTRY, PropertyID, Region

    by_region: dict[Region, list[str]] = {}
    for pid, info in PROPERTY_REGISTRY.items():
        if pid == PropertyID.SHARED:
            continue
        by_region.setdefault(info.region, []).append(info.name)

    lines = []
    for region, names in by_region.items():
        label = region.value.replace("_", " ").title()
        lines.append(f"- **{label}:** {', '.join(names)}")
    return "\n".join(lines)


def build_scope_instructions(
    scope: str,
    *,
    property_name: str | None = None,
    property_id: str | None = None,
    property_ids: list[str] | None = None,
    location: str | None = None,
    region: str | None = None,
    property_names: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    is_sparse: bool = False,
) -> str:
    """Build scope-specific instructions for the prompt.

    Quick facts are injected for ALL scopes:
    - PROPERTY: single property facts
    - REGION/CROSS_PROPERTY: multi-property facts for all properties in scope
    - GROUP: all properties with known facts
    """
    contact = _format_contact(email or "", phone or "")

    if scope == "property" and property_name:
        if is_sparse:
            return SCOPE_PROPERTY_SPARSE.format(
                property_name=property_name,
                location=location or "South Africa",
                contact_info=contact,
            )
        return SCOPE_PROPERTY.format(
            property_name=property_name,
            location=location or "South Africa",
            contact_info=contact,
        )

    if scope == "region" and region:
        return SCOPE_REGION.format(region=region)

    if scope == "cross_property" and property_names:
        return SCOPE_CROSS_PROPERTY.format(property_names=property_names)

    if scope == "group":
        return SCOPE_GROUP

    return SCOPE_NO_CONTEXT


def format_context(
    chunks: list[dict],
    *,
    property_id: str | None = None,
    property_ids: list[str] | None = None,
    scope: str | None = None,
) -> str:
    """Format retrieved chunks into context string for the prompt.

    Injects verified property facts as the FIRST context document so the
    LLM treats them as retrieved knowledge (not just instructions).
    Includes section_title and page_number when available for rich citations.
    """
    parts = []

    # Inject quick facts as synthetic context document
    facts_text = _build_facts_context(
        property_id=property_id,
        property_ids=property_ids,
        scope=scope,
    )
    if facts_text:
        parts.append(
            "[Document 0 — Source: Verified Property Facts — "
            "Section: Quick Reference]\n" + facts_text
        )

    if not chunks and not parts:
        return "No relevant documents found."

    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_file", "Unknown")
        section = chunk.get("metadata", {}).get("section_title") or chunk.get("section_title")
        page = chunk.get("metadata", {}).get("page_number") or chunk.get("page_number")
        content = chunk.get("content", "")

        # Build concise citation header (truncate long section titles)
        header_parts = [f"Source: {source}"]
        if section:
            # Truncate section titles longer than 60 chars
            clean_section = section[:60].rstrip() + ("..." if len(section) > 60 else "")
            header_parts.append(f"Section: {clean_section}")
        if page:
            header_parts.append(f"Page {page}")
        header = " — ".join(header_parts)

        parts.append(f"[Document {i} — {header}]\n{content}")

    return "\n\n---\n\n".join(parts)


def _build_facts_context(
    *,
    property_id: str | None = None,
    property_ids: list[str] | None = None,
    scope: str | None = None,
) -> str:
    """Build quick-facts text for injection as a context document."""
    from src.domain.properties import PROPERTY_REGISTRY, PropertyID

    pids: list[str] = []
    if scope == "property" and property_id:
        pids = [property_id]
    elif scope in ("region", "cross_property") and property_ids:
        pids = property_ids
    elif scope == "group":
        pids = list(PROPERTY_FACTS.keys())

    if not pids:
        return ""

    sections = []
    for pid_str in pids:
        facts = PROPERTY_FACTS.get(pid_str)
        if not facts:
            continue
        try:
            info = PROPERTY_REGISTRY.get(PropertyID(pid_str))
            name = info.name if info else pid_str.replace("_", " ").title()
        except ValueError:
            name = pid_str.replace("_", " ").title()

        lines = [f"{name}:"]
        for key, label in _FACT_LABELS.items():
            if key in facts:
                lines.append(f"  {label}: {facts[key]}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def format_history(history: list[dict]) -> str:
    """Format conversation history for the prompt."""
    if not history:
        return "No previous conversation."

    # Include last 10 messages for context
    recent = history[-10:]
    parts = []
    for msg in recent:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")

    return "\n".join(parts)
