"""Detailed evaluation — shows expected vs actual answers for all 48 Brydon questions."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY", "")

# Each question with expected answer from the KB documents
EVALUATION_SET = [
    # ── GENERAL AVAILABILITY ──
    {
        "id": "GA01",
        "category": "general_availability",
        "question": "Is there a minimum night stay requirement?",
        "expected": "Yes. Minimum 2 nights from 20 Dec to 5 Jan at La Fontaine/Avondrood. Minimum 5 nights at Blackheath Lodge same period.",
        "expected_contains": ["minimum", "night"],
        "source_docs": ["RACK Rates La Fontaine", "RACK Rates Blackheath Lodge"],
    },
    {
        "id": "GA02",
        "category": "general_availability",
        "question": "Can I check in earlier than 15:00?",
        "expected": "Standard check-in is 14:00 (2pm). Early check-in subject to availability — contact property directly.",
        "expected_contains": ["14"],
        "source_docs": ["RACK Rates - T&Cs"],
    },
    {
        "id": "GA03",
        "category": "general_availability",
        "question": "Can I check out later than 10:30?",
        "expected": "Standard check-out is 10:30 (La Fontaine/Avondrood/Camp Figtree) or 11:00 (Blackheath Lodge). Late check-out subject to availability.",
        "expected_contains": ["10:30", "check"],
        "answerable": True,
        "source_docs": ["RACK Rates - T&Cs"],
    },
    # ── GENERAL RATES ──
    {
        "id": "GR01",
        "category": "general_rates",
        "question": "What is the rate per night for the Luxury Suite at La Fontaine?",
        "expected": "Luxury Suite DBL: R5,050-R7,970 depending on season (Oct 2025-Jan 2027). SGL: R4,890-R7,410.",
        "expected_contains": ["luxury suite"],
        "source_docs": ["RACK Rates La Fontaine Oct 2025 - 08 Jan 2027"],
    },
    {
        "id": "GR02",
        "category": "general_rates",
        "question": "What is the rate per night for the Deluxe room at Avondrood?",
        "expected": "Avondrood Deluxe room rates vary by season. Available in the rate card Oct 2025 - Jan 2027.",
        "expected_contains": ["deluxe"],
        "source_docs": ["RACK Rates Avondrood Oct 2025 - 08 Jan 2027"],
    },
    {
        "id": "GR03",
        "category": "general_rates",
        "question": "Is breakfast included in the rate?",
        "expected": "Yes. Complimentary breakfast served 8:00-9:30 (La Fontaine, Avondrood, Camp Figtree) or 7:00-10:00 (Blackheath Lodge). All rates inclusive of breakfast.",
        "expected_contains": ["breakfast"],
        "source_docs": ["RACK Rates - T&Cs"],
    },
    {
        "id": "GR04",
        "category": "general_rates",
        "question": "What are your payment terms?",
        "expected": "Full pre-payment due 30 days prior to arrival. Group bookings (4+ rooms) require 20% deposit within 10 days. Visa, MasterCard, Cash and EFT accepted.",
        "expected_contains": ["payment", "30 days"],
        "source_docs": ["RACK Rates - Payment Policy"],
    },
    {
        "id": "GR05",
        "category": "general_rates",
        "question": "What methods of payment are accepted?",
        "expected": "Visa, MasterCard, Cash and EFT are accepted.",
        "expected_contains": ["visa", "mastercard"],
        "source_docs": ["RACK Rates - Payment Policy"],
    },
    {
        "id": "GR06",
        "category": "general_rates",
        "question": "What is the refund process for cancellations?",
        "expected": "Cancellation within 30 days forfeits 100%. All refunds charged R500 admin fee. Must be received in writing.",
        "expected_contains": ["cancel"],
        "source_docs": ["RACK Rates - Cancellation Policy"],
    },
    {
        "id": "GR07",
        "category": "general_rates",
        "question": "How can I cancel a booking, and are there any cancellation fees?",
        "expected": "Cancellation must be in writing. Within 30 days = 100% forfeit. R500 admin fee on all refunds.",
        "expected_contains": ["cancel"],
        "source_docs": ["RACK Rates - Cancellation Policy"],
    },
    # ── GENERAL SERVICES ──
    {
        "id": "GS01",
        "category": "general_services",
        "question": "Are you able to provide a camp cot for a child?",
        "expected": "NOT IN KB — children 0-3 stay free sharing with adults, but camp cot availability not specified.",
        "expected_contains": ["child"],
        "answerable": False,
        "source_docs": [],
    },
    {
        "id": "GS02",
        "category": "general_services",
        "question": "Are children welcome at the property?",
        "expected": "Yes. Children welcome by arrangement. 0-3 free when sharing. 4+ in Luxury Suite on mattress at extra charge.",
        "expected_contains": ["children", "welcome"],
        "source_docs": ["RACK Rates - Children Policy"],
    },
    {
        "id": "GS03",
        "category": "general_services",
        "question": "Is there free Wi-Fi onsite?",
        "expected": "Yes. Free WiFi available at all properties.",
        "expected_contains": ["wi-fi"],
        "source_docs": ["RACK Rates - General Facilities", "Information Guides"],
    },
    {
        "id": "GS04",
        "category": "general_services",
        "question": "Do you offer free airport shuttles or transfers?",
        "expected": "Transfers available but NOT free. Tours & Transfers docs have pricing. Contact property for arrangement.",
        "expected_contains": ["transfer"],
        "source_docs": ["Tours and Transfers 2026", "BHL Tours & Transfers 2024"],
    },
    {
        "id": "GS05",
        "category": "general_services",
        "question": "Are pets allowed?",
        "expected": "No. 'We regret, no pets' — stated in rate card T&Cs.",
        "expected_contains": ["pet"],
        "source_docs": ["RACK Rates - T&Cs"],
    },
    {
        "id": "GS06",
        "category": "general_services",
        "question": "Is there daily room cleaning?",
        "expected": "NOT IN KB — room cleaning frequency not specified in any document.",
        "expected_contains": ["clean"],
        "answerable": False,
        "source_docs": [],
    },
    # ── FRANSCHHOEK ──
    {
        "id": "FR01",
        "category": "franschhoek",
        "question": "What are the private tours that can be arranged by the hotel in Franschhoek?",
        "expected": "Wine tram, Cape Winelands tours, helicopter flights, e-bike tours, horse riding, cooking classes, etc.",
        "expected_contains": ["tour"],
        "source_docs": ["Tours and Transfers 2026", "Recommends 2026"],
    },
    {
        "id": "FR02",
        "category": "franschhoek",
        "question": "Can you provide details on recommended local restaurants in Franschhoek?",
        "expected": "Multiple restaurants recommended: La Petite Ferme, Epice, Arkeste, La Residence, Old Road Wine Co, etc.",
        "expected_contains": ["restaurant"],
        "source_docs": ["LF Recommends 2026", "Avondrood Recommends 2026"],
    },
    {
        "id": "FR03",
        "category": "franschhoek",
        "question": "What is the nearest golf course to Franschhoek?",
        "expected": "Pearl Valley Golf Course or similar nearby course.",
        "expected_contains": ["golf"],
        "source_docs": ["Recommends docs"],
    },
    {
        "id": "FR04",
        "category": "franschhoek",
        "question": "Can e-bikes be hired locally in Franschhoek?",
        "expected": "Yes. E-bike hire available in Franschhoek.",
        "expected_contains": ["bike"],
        "source_docs": ["Recommends docs"],
    },
    {
        "id": "FR05",
        "category": "franschhoek",
        "question": "Do you offer car service or transfers to Stellenbosch?",
        "expected": "Yes. Transfers to Stellenbosch available. See Tours & Transfers pricing.",
        "expected_contains": ["transfer", "stellenbosch"],
        "source_docs": ["Tours and Transfers 2026"],
    },
    {
        "id": "FR06",
        "category": "franschhoek",
        "question": "Can you recommend any wine tasting tours in Franschhoek?",
        "expected": "Yes — wine tram, various wine farms (Holden Manz, Mont Rochelle, La Bri, etc.)",
        "expected_contains": ["wine"],
        "source_docs": ["Recommends 2026"],
    },
    {
        "id": "FR07",
        "category": "franschhoek",
        "question": "What are the payment terms at La Fontaine? When is the deposit due?",
        "expected": "Full pre-payment due 30 days prior. Group bookings require 20% deposit within 10 days.",
        "expected_contains": ["payment", "30"],
        "source_docs": ["RACK Rates La Fontaine - Payment Policy"],
    },
    {
        "id": "FR08",
        "category": "franschhoek",
        "question": "Is it possible to arrange a late check-out at Avondrood?",
        "expected": "Standard check-out 10:30. Late check-out subject to availability — contact property.",
        "expected_contains": ["check"],
        "source_docs": ["RACK Rates Avondrood - T&Cs"],
    },
    # ── CAPE TOWN ──
    {
        "id": "CT01",
        "category": "cape_town",
        "question": "Can a Cape Peninsula Tour be booked from POD Camps Bay?",
        "expected": "Yes. Various tours available from Cape Town properties.",
        "expected_contains": ["tour", "peninsula"],
        "source_docs": ["BHL Tours & Transfers 2024", "POD Fact Sheet"],
    },
    {
        "id": "CT02",
        "category": "cape_town",
        "question": "Are entrance fees included in the tour price at POD Camps Bay?",
        "expected": "Depends on tour — check specific tour details in Tours & Transfers.",
        "expected_contains": ["entrance", "fee"],
        "source_docs": ["BHL Tours & Transfers 2024"],
    },
    {
        "id": "CT03",
        "category": "cape_town",
        "question": "Can airport transfers be arranged from POD Camps Bay?",
        "expected": "Yes. Airport transfers available — contact property. Pricing in Tours & Transfers.",
        "expected_contains": ["transfer", "airport"],
        "source_docs": ["BHL Tours & Transfers 2024"],
    },
    {
        "id": "CT04",
        "category": "cape_town",
        "question": "What is the minimum stay requirement at POD Camps Bay over peak periods?",
        "expected": "Check POD rate card for minimum stay requirements during peak season.",
        "expected_contains": ["minimum", "stay"],
        "source_docs": ["POD Rack Rates"],
    },
    {
        "id": "CT05",
        "category": "cape_town",
        "question": "Is it possible to store luggage before check-in at Blackheath Lodge?",
        "expected": "NOT IN KB — luggage storage not mentioned in any Blackheath Lodge document.",
        "expected_contains": ["luggage"],
        "answerable": False,
        "source_docs": [],
    },
    # ── CAMP FIGTREE ──
    {
        "id": "CF01",
        "category": "camp_figtree",
        "question": "What activities do you offer at Camp Figtree?",
        "expected": "Game drives (morning/afternoon), guided walks, Addo Elephant Park, horse riding, canoeing, zip-lining, etc.",
        "expected_contains": ["activit"],
        "source_docs": ["Activity Sheet 2023", "Camp Figtree Activities List"],
    },
    {
        "id": "CF02",
        "category": "camp_figtree",
        "question": "Can you send the recommended directions to Camp Figtree?",
        "expected": "Detailed directions from PE airport / N2 highway to Camp Figtree.",
        "expected_contains": ["direction"],
        "source_docs": ["Camp Figtree Directions only_pdf.pdf"],
    },
    {
        "id": "CF03",
        "category": "camp_figtree",
        "question": "Is an SUV or 4x4 required for the road to Camp Figtree?",
        "expected": "No. Normal sedan is fine. Road is tarred/gravel but accessible.",
        "expected_contains": ["road", "drive"],
        "source_docs": ["Camp Figtree Directions"],
    },
    {
        "id": "CF04",
        "category": "camp_figtree",
        "question": "Is Wi-Fi available in the suites at Camp Figtree?",
        "expected": "Wi-Fi available in the restaurant only, not in the suites.",
        "expected_contains": ["wi-fi"],
        "source_docs": ["Camp Figtree Fact Sheet 2025"],
    },
    {
        "id": "CF05",
        "category": "camp_figtree",
        "question": "What time should we plan to arrive at Camp Figtree?",
        "expected": "Check-in 14:00. Aim to arrive by 14:00-15:00 for afternoon game drive.",
        "expected_contains": ["arrive", "time"],
        "source_docs": ["Camp Figtree Fact Sheet", "T&Cs"],
    },
    {
        "id": "CF06",
        "category": "camp_figtree",
        "question": "Can you arrange an airport transfer to Camp Figtree?",
        "expected": "Yes. Transfers available from PE airport. See Route Travel doc for details.",
        "expected_contains": ["transfer", "airport"],
        "source_docs": ["Route Travel and Recommendations"],
    },
    {
        "id": "CF07",
        "category": "camp_figtree",
        "question": "Should we book the game drive for morning or afternoon?",
        "expected": "Both options available. Morning drives at sunrise, afternoon with sundowners.",
        "expected_contains": ["game drive"],
        "source_docs": ["Activity Sheet", "Camp Figtree Activities List"],
    },
    {
        "id": "CF08",
        "category": "camp_figtree",
        "question": "Is dinner an a la carte menu or set meal at Camp Figtree?",
        "expected": "Set menu / table d'hote style at Camp Figtree restaurant.",
        "expected_contains": ["dinner", "menu"],
        "source_docs": ["Camp Figtree Restaurant Brochure"],
    },
    {
        "id": "CF09",
        "category": "camp_figtree",
        "question": "What is included in the 2-night package at Camp Figtree?",
        "expected": "Package typically includes accommodation, breakfast, dinner, game drive. Check rate card for details.",
        "expected_contains": ["package", "include"],
        "source_docs": ["CFT Rates 2025"],
    },
    {
        "id": "CF10",
        "category": "camp_figtree",
        "question": "What is Camp Figtree's cancellation policy?",
        "expected": "Cancellation within 30 days forfeits 100%. Must be in writing.",
        "expected_contains": ["cancel"],
        "source_docs": ["CFT Rates - Cancellation Policy"],
    },
    {
        "id": "CF11",
        "category": "camp_figtree",
        "question": "Do guests need to present a passport for Addo National Park entry?",
        "expected": "NOT IN KB — Addo entry requirements not in any Camp Figtree document.",
        "expected_contains": ["passport"],
        "answerable": False,
        "source_docs": [],
    },
    # ── PROPERTY DISCOVERY ──
    {
        "id": "PD01",
        "category": "property_discovery",
        "question": "What properties do you have?",
        "expected": "12 properties: La Fontaine, Avondrood, Pink Door (Franschhoek), POD Camps Bay, Blackheath Lodge (Cape Town), Camp Figtree (Addo), The Milner, 8A, Pleasance (Grahamstown), Burlington Bush (Salem), Oyster Box, Kenton Houses (Kenton).",
        "expected_contains": ["la fontaine", "avondrood"],
        "source_docs": ["Property list / Flyer Summary"],
    },
    {
        "id": "PD02",
        "category": "property_discovery",
        "question": "What properties do you have in Franschhoek?",
        "expected": "La Fontaine Boutique Hotel, Avondrood Guest House, The Pink Door (Owner's Villa).",
        "expected_contains": ["la fontaine", "avondrood"],
        "source_docs": ["Property list"],
    },
    {
        "id": "PD03",
        "category": "property_discovery",
        "question": "What properties do you have near the beach?",
        "expected": "POD Camps Bay (beachfront), Oyster Box Beach House (Kenton-on-Sea), Kenton Houses.",
        "expected_contains": ["pod", "beach"],
        "source_docs": ["Brochures"],
    },
    {
        "id": "PD04",
        "category": "property_discovery",
        "question": "Which property is best for a family holiday?",
        "expected": "Camp Figtree (game drives, family activities), Kenton Houses, Burlington Bush, Pink Door (self-catering villa).",
        "expected_contains": ["family"],
        "source_docs": ["Brochures", "Fact Sheets"],
    },
    {
        "id": "PD05",
        "category": "property_discovery",
        "question": "I want to book a room",
        "expected": "Booking intent detected — ask for property, dates, guests or provide contact details.",
        "expected_contains": ["property"],
        "source_docs": ["Booking intent handler"],
    },
    # ── SPA AND DINING ──
    {
        "id": "SD01",
        "category": "spa_and_dining",
        "question": "What spa treatments does La Fontaine offer?",
        "expected": "In-room spa treatments: massages, facials, body wraps, etc. See Spa Menu.",
        "expected_contains": ["spa", "treatment"],
        "source_docs": ["Franschhoek Spa Menu 2024 LF"],
    },
    {
        "id": "SD02",
        "category": "spa_and_dining",
        "question": "What restaurants do you recommend near Avondrood?",
        "expected": "Multiple: La Petite Ferme, Epice, Le Bon Vivant, Tuk Tuk, Reuben's, etc.",
        "expected_contains": ["restaurant"],
        "source_docs": ["Avondrood Recommends 2026"],
    },
    {
        "id": "SD03",
        "category": "spa_and_dining",
        "question": "What is on the dinner menu at Camp Figtree?",
        "expected": "Restaurant brochure shows menu options. Bush dining experience.",
        "expected_contains": ["dinner", "menu"],
        "source_docs": ["Camp Figtree Restaurant Brochure"],
    },
]


def query_api(question: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    try:
        resp = httpx.post(
            f"{BASE_URL}/chat",
            json={"message": question},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"response": f"HTTP {resp.status_code}", "sources": [], "scope": None}
    except Exception as e:
        return {"response": f"ERROR: {e}", "sources": [], "scope": None}


def evaluate_answer(item: dict, response: str) -> str:
    """Determine verdict: PASS, PARTIAL, DENIED, FAIL."""
    lower = response.lower()

    denial_phrases = [
        "i don't have",
        "i do not have",
        "don't have specific",
        "unable to find",
        "no information",
    ]
    is_denial = any(p in lower for p in denial_phrases)
    has_escalation = any(
        x in lower for x in ["email", "phone", "@", "+27", "contact"]
    )

    # Check expected_contains
    contains_pass = all(
        term.lower() in lower for term in item.get("expected_contains", [])
    )

    if is_denial and not has_escalation:
        return "DENIED"
    if is_denial and has_escalation:
        return "PARTIAL"
    if contains_pass:
        return "PASS"
    return "FAIL"


def main():
    print(f"Target: {BASE_URL}")
    print(f"Questions: {len(EVALUATION_SET)}")
    print()

    results = []
    categories: dict[str, list] = {}

    for item in EVALUATION_SET:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []

        start = time.perf_counter()
        api_result = query_api(item["question"])
        latency = time.perf_counter() - start

        response = api_result.get("response", "")
        verdict = evaluate_answer(item, response)
        answerable = item.get("answerable", True)

        result = {
            "id": item["id"],
            "category": cat,
            "question": item["question"],
            "expected": item["expected"],
            "actual": response[:300],
            "verdict": verdict,
            "latency": round(latency, 1),
            "scope": api_result.get("scope"),
            "sources": len(api_result.get("sources", [])),
            "answerable": answerable,
        }
        results.append(result)
        categories[cat].append(result)

        icon = {"PASS": "+", "FAIL": "X", "PARTIAL": "~", "DENIED": "-"}[verdict]
        answerable_tag = "" if answerable else " [NOT IN KB]"
        print(f"  [{icon}] {item['id']:5s} ({latency:4.1f}s) {item['question'][:60]}{answerable_tag}")

    # ── Detailed Report ──
    print("\n" + "=" * 100)
    print("  DETAILED EVALUATION REPORT")
    print("=" * 100)

    for cat, items in categories.items():
        print(f"\n{'-' * 100}")
        print(f"  {cat.upper().replace('_', ' ')}")
        print(f"{'-' * 100}")

        for r in items:
            verdict_color = {
                "PASS": "PASS   ",
                "FAIL": "FAIL   ",
                "PARTIAL": "PARTIAL",
                "DENIED": "DENIED ",
            }[r["verdict"]]
            answerable_tag = " [NOT IN KB]" if not r["answerable"] else ""

            print(f"\n  [{verdict_color}] {r['id']}: {r['question']}{answerable_tag}")
            print(f"  EXPECTED: {r['expected'][:120]}")
            print(f"  ACTUAL:   {r['actual'][:120]}")
            if r["verdict"] in ("DENIED", "FAIL") and r["answerable"]:
                print(f"  >>> ISSUE: Answer IS in KB but not retrieved!")

    # ── Summary ──
    print("\n" + "=" * 100)
    print("  SUMMARY")
    print("=" * 100)

    total = len(results)
    answerable_total = sum(1 for r in results if r.get("answerable", True))
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    partial = sum(1 for r in results if r["verdict"] == "PARTIAL")
    denied = sum(1 for r in results if r["verdict"] == "DENIED")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")

    # Separate answerable vs not-in-KB
    answerable_passed = sum(
        1 for r in results if r["verdict"] == "PASS" and r.get("answerable", True)
    )
    unanswerable = sum(1 for r in results if not r.get("answerable", True))
    unanswerable_correct = sum(
        1
        for r in results
        if not r.get("answerable", True) and r["verdict"] in ("PARTIAL", "DENIED")
    )

    print(f"\n  Total questions:       {total}")
    print(f"  Answerable from KB:    {answerable_total}")
    print(f"  Not in KB:             {unanswerable}")
    print()
    print(f"  PASS (answered well):  {passed}")
    print(f"  PARTIAL (+ contact):   {partial}")
    print(f"  DENIED (no contact):   {denied}")
    print(f"  FAIL (wrong answer):   {failed}")
    print()
    print(
        f"  Accuracy (answerable): {answerable_passed}/{answerable_total}"
        f" ({answerable_passed/answerable_total*100:.0f}%)"
    )
    print(
        f"  With escalation:       {passed+partial}/{total}"
        f" ({(passed+partial)/total*100:.0f}%)"
    )
    print(
        f"  Not-in-KB handled:     {unanswerable_correct}/{unanswerable}"
        f" ({unanswerable_correct/unanswerable*100:.0f}%)" if unanswerable else ""
    )

    print(f"\n  Per Category:")
    for cat, items in categories.items():
        cat_total = len(items)
        cat_pass = sum(1 for r in items if r["verdict"] == "PASS")
        cat_answerable = sum(1 for r in items if r.get("answerable", True))
        bar = "#" * int(cat_pass / cat_total * 20) + "." * (
            20 - int(cat_pass / cat_total * 20)
        )
        print(f"    {cat:25s} {cat_pass:2d}/{cat_total:2d} [{bar}] {cat_pass/cat_total*100:.0f}%")

    # ── Regressions (answerable but not passing) ──
    regressions = [
        r
        for r in results
        if r["verdict"] in ("DENIED", "FAIL") and r.get("answerable", True)
    ]
    if regressions:
        print(f"\n  RETRIEVAL FAILURES (answerable but denied/failed):")
        for r in regressions:
            print(f"    [{r['verdict']:7s}] {r['id']}: {r['question'][:70]}")

    # Save JSON
    output_path = Path("evaluation_results.json")
    with open(output_path, "w") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target": BASE_URL,
                "total": total,
                "passed": passed,
                "partial": partial,
                "denied": denied,
                "failed": failed,
                "accuracy_pct": round(answerable_passed / answerable_total * 100, 1),
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    main()
