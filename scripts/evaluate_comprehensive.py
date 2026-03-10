"""Comprehensive evaluation -- 100+ questions across all dimensions.

Categories:
- General (availability, rates, payments, services, policies)
- Franschhoek (La Fontaine, Avondrood, Pink Door)
- Cape Town (POD Camps Bay, Blackheath Lodge)
- Camp Figtree / Addo
- Property Discovery / Group queries
- Cross-property comparisons
- Sparse properties (Milner, 8A, Pleasance, Burlington, Oyster Box, Kenton)
- Out-of-scope / irrelevant
- Typos / fuzzy matching
- Booking intent
- Follow-up / context-dependent (session continuity)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY", "")

EVALUATION_SET = [
    # ========================================================================
    # GENERAL -- AVAILABILITY & BOOKING
    # ========================================================================
    {
        "id": "GA01",
        "category": "general_availability",
        "question": "Is there a minimum night stay requirement?",
        "expected": "Yes. Minimum 2 nights from 20 Dec to 5 Jan at some properties.",
        "expected_contains": ["minimum", "night"],
        "answerable": True,
    },
    {
        "id": "GA02",
        "category": "general_availability",
        "question": "Can I check in earlier than 15:00?",
        "expected": "Standard check-in is 14:00. Early check-in subject to availability.",
        "expected_contains": ["14"],
        "answerable": True,
    },
    {
        "id": "GA03",
        "category": "general_availability",
        "question": "Can I check out later than 10:30?",
        "expected": "Standard check-out is 10:30. Late check-out subject to availability.",
        "expected_contains": ["10:30"],
        "answerable": True,
    },
    {
        "id": "GA04",
        "category": "general_availability",
        "question": "Can I be waitlisted for specific dates if nothing is available?",
        "expected": "Not documented in KB. Suggest contacting property directly.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GA05",
        "category": "general_availability",
        "question": "Can you hold a reservation for me, and until what date?",
        "expected": "Not documented in KB. Suggest contacting property directly.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # GENERAL -- RATES, DISCOUNTS, PAYMENT
    # ========================================================================
    {
        "id": "GR01",
        "category": "general_rates",
        "question": "What is the rate per night for the Luxury Suite at La Fontaine?",
        "expected": "Luxury Suite rates vary by season from rate card Oct 2025-Jan 2027.",
        "expected_contains": ["luxury suite"],
        "answerable": True,
    },
    {
        "id": "GR02",
        "category": "general_rates",
        "question": "What is the rate per night for the Deluxe room at Avondrood?",
        "expected": "Avondrood Deluxe room rates from rate card Oct 2025-Jan 2027.",
        "expected_contains": ["deluxe"],
        "answerable": True,
    },
    {
        "id": "GR03",
        "category": "general_rates",
        "question": "Is breakfast included in the rate?",
        "expected": "Yes at some properties. Complimentary breakfast included.",
        "expected_contains": ["breakfast"],
        "answerable": True,
    },
    {
        "id": "GR04",
        "category": "general_rates",
        "question": "What are your payment terms?",
        "expected": "Full pre-payment due 30 days prior to arrival.",
        "expected_contains": ["payment", "30 days"],
        "answerable": True,
    },
    {
        "id": "GR05",
        "category": "general_rates",
        "question": "What methods of payment are accepted?",
        "expected": "Visa, MasterCard, Cash and EFT accepted.",
        "expected_contains": ["visa"],
        "answerable": True,
    },
    {
        "id": "GR06",
        "category": "general_rates",
        "question": "What is the refund process for cancellations?",
        "expected": "Cancellation within 30 days forfeits 100%. R500 admin fee.",
        "expected_contains": ["cancellation"],
        "answerable": True,
    },
    {
        "id": "GR07",
        "category": "general_rates",
        "question": "How can I cancel a booking, and are there any cancellation fees?",
        "expected": "Must be in writing. Within 30 days = 100% forfeit. R500 admin fee.",
        "expected_contains": ["cancel", "writing"],
        "answerable": True,
    },
    {
        "id": "GR08",
        "category": "general_rates",
        "question": "Do you need a deposit for the booking?",
        "expected": "Full pre-payment 30 days prior. Group bookings 20% deposit within 10 days.",
        "expected_contains": ["deposit"],
        "answerable": True,
    },
    {
        "id": "GR09",
        "category": "general_rates",
        "question": "Are you able to apply a returning customer discount?",
        "expected": "Not documented in KB. Contact property for special rates.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GR10",
        "category": "general_rates",
        "question": "Can you send an invoice or quote that covers the whole trip?",
        "expected": "Not documented. Contact property for invoicing.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GR11",
        "category": "general_rates",
        "question": "Can I make a prepayment, and what is the payment link?",
        "expected": "Pre-payment required. Contact property for payment link.",
        "expected_contains": ["payment"],
        "answerable": True,
    },
    # ========================================================================
    # GENERAL -- GUEST & FAMILY SERVICES
    # ========================================================================
    {
        "id": "GS01",
        "category": "general_services",
        "question": "Are children welcome at the property, and are there any age restrictions?",
        "expected": "Yes, children welcome by arrangement. 0-3 free when sharing.",
        "expected_contains": ["children"],
        "answerable": True,
    },
    {
        "id": "GS02",
        "category": "general_services",
        "question": "Are you able to provide a camp cot for a child?",
        "expected": "Not documented in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GS03",
        "category": "general_services",
        "question": "Do you also have a high chair available?",
        "expected": "Not documented in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GS04",
        "category": "general_services",
        "question": "Is there a safety net or cover for the pool?",
        "expected": "Not documented in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GS05",
        "category": "general_services",
        "question": "Is there free Wi-Fi onsite?",
        "expected": "Yes, free Wi-Fi available.",
        "expected_contains": ["wi-fi"],
        "answerable": True,
    },
    {
        "id": "GS06",
        "category": "general_services",
        "question": "Do you offer free airport shuttles or transfers?",
        "expected": "Not free. Transfers available for a fee.",
        "expected_contains": ["transfer"],
        "answerable": True,
    },
    {
        "id": "GS07",
        "category": "general_services",
        "question": "Are pets allowed?",
        "expected": "No, we regret no pets.",
        "expected_contains": ["pet"],
        "answerable": True,
    },
    {
        "id": "GS08",
        "category": "general_services",
        "question": "Is there daily room cleaning?",
        "expected": "Not documented in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GS09",
        "category": "general_services",
        "question": "Is there heating in the room?",
        "expected": "Not documented in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "GS10",
        "category": "general_services",
        "question": ("Is a fold-out mattress available for children, and what is the charge?"),
        "expected": "Children 4+ in Luxury Suite on mattress at extra charge.",
        "expected_contains": ["children"],
        "answerable": True,
    },
    {
        "id": "GS11",
        "category": "general_services",
        "question": "Are there on-site spaces for large groups to gather?",
        "expected": "Not documented. Contact property for group facilities.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # GENERAL -- ACTIVITIES
    # ========================================================================
    {
        "id": "ACT01",
        "category": "general_activities",
        "question": "Are game drives included in the room price?",
        "expected": "Depends on package. Some Camp Figtree packages include game drives.",
        "expected_contains": ["game drive"],
        "answerable": True,
    },
    {
        "id": "ACT02",
        "category": "general_activities",
        "question": "Can a game drive be organised privately?",
        "expected": "Private game drives available at Camp Figtree.",
        "expected_contains": ["game drive"],
        "answerable": True,
    },
    {
        "id": "ACT03",
        "category": "general_activities",
        "question": "Is it possible to do a self-drive around Addo park?",
        "expected": "Self-drive available at Addo Elephant National Park.",
        "expected_contains": ["addo"],
        "answerable": True,
    },
    {
        "id": "ACT04",
        "category": "general_activities",
        "question": "How far in advance do we need to book a game drive?",
        "expected": "Advance booking recommended. Contact Camp Figtree.",
        "expected_contains": ["book"],
        "answerable": True,
    },
    # ========================================================================
    # FRANSCHHOEK -- ROOMS & CONFIG
    # ========================================================================
    {
        "id": "FR01",
        "category": "franschhoek_rooms",
        "question": "Can you reconfirm the bed configuration in the room at La Fontaine?",
        "expected": "Room configurations in La Fontaine info guide.",
        "expected_contains": ["bed"],
        "answerable": True,
    },
    {
        "id": "FR02",
        "category": "franschhoek_rooms",
        "question": "Does our room at La Fontaine include a bath?",
        "expected": "Check room amenities in information guide.",
        "expected_contains": ["bath"],
        "answerable": True,
    },
    {
        "id": "FR03",
        "category": "franschhoek_rooms",
        "question": "What is the size of the travel cot you provide at La Fontaine?",
        "expected": "Not documented in KB. Contact La Fontaine directly.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "FR04",
        "category": "franschhoek_rooms",
        "question": (
            "Can a Luxury Suite with a private garden and sun loungers "
            "be allocated at the time of booking?"
        ),
        "expected": "Room allocation details from La Fontaine info guide.",
        "expected_contains": ["suite"],
        "answerable": True,
    },
    {
        "id": "FR05",
        "category": "franschhoek_rooms",
        "question": "Is it possible to secure an early check-in at La Fontaine?",
        "expected": "Check-in at 14:00. Early check-in subject to availability.",
        "expected_contains": ["check-in"],
        "answerable": True,
    },
    {
        "id": "FR06",
        "category": "franschhoek_rooms",
        "question": (
            "Do you have accommodation for an additional family at La Fontaine? "
            "What is the best room configuration for children of various ages?"
        ),
        "expected": "Room options from La Fontaine info guide. Interleading/adjacent rooms.",
        "expected_contains": ["room"],
        "answerable": True,
    },
    {
        "id": "FR07",
        "category": "franschhoek_rooms",
        "question": "Is the room reservation for single or double occupancy at La Fontaine?",
        "expected": "Rates show SGL and DBL occupancy options.",
        "expected_contains": ["occupancy"],
        "answerable": True,
    },
    # ========================================================================
    # FRANSCHHOEK -- ACTIVITIES & TOURS
    # ========================================================================
    {
        "id": "FT01",
        "category": "franschhoek_tours",
        "question": "What are the private tours that can be arranged by the hotel in Franschhoek?",
        "expected": "Wine tram, Cape Winelands tours, helicopter, e-bikes, horse riding, etc.",
        "expected_contains": ["tour"],
        "answerable": True,
    },
    {
        "id": "FT02",
        "category": "franschhoek_tours",
        "question": "Can you provide details on recommended local restaurants in Franschhoek?",
        "expected": "La Petite Ferme, Epice, Arkeste, Le Bon Vivant, etc.",
        "expected_contains": ["restaurant"],
        "answerable": True,
    },
    {
        "id": "FT03",
        "category": "franschhoek_tours",
        "question": (
            "Can the hotel book tours and restaurants in advance "
            "or during the stay in Franschhoek?"
        ),
        "expected": "Yes, concierge can arrange bookings. Tours & Transfers doc.",
        "expected_contains": ["book"],
        "answerable": True,
    },
    {
        "id": "FT04",
        "category": "franschhoek_tours",
        "question": (
            "What is the nearest golf course to Franschhoek, " "and will they allow visitors?"
        ),
        "expected": "Pearl Valley / Boschenmeer Golf Estate.",
        "expected_contains": ["golf"],
        "answerable": True,
    },
    {
        "id": "FT05",
        "category": "franschhoek_tours",
        "question": "Can e-bikes be hired locally in Franschhoek?",
        "expected": "Yes, e-bike tours with VineBikes available.",
        "expected_contains": ["e-bike"],
        "answerable": True,
    },
    {
        "id": "FT06",
        "category": "franschhoek_tours",
        "question": "Do you offer car service or transfers to Stellenbosch from Franschhoek?",
        "expected": "Yes. Transfer pricing in Tours & Transfers doc.",
        "expected_contains": ["stellenbosch"],
        "answerable": True,
    },
    {
        "id": "FT07",
        "category": "franschhoek_tours",
        "question": "Are the transfer rates per person or per car in Franschhoek?",
        "expected": "Rates typically per vehicle/transfer. Check Tours & Transfers doc.",
        "expected_contains": ["rate"],
        "answerable": True,
    },
    {
        "id": "FT08",
        "category": "franschhoek_tours",
        "question": "Can you recommend wine tasting tours with transport in Franschhoek?",
        "expected": "Wine tram, various wine farms with transport included.",
        "expected_contains": ["wine"],
        "answerable": True,
    },
    {
        "id": "FT09",
        "category": "franschhoek_tours",
        "question": (
            "Can you provide a quote for a driver to take us "
            "on a wine tasting and lunch tour in Franschhoek?"
        ),
        "expected": "Private driver/tour pricing in Tours & Transfers doc.",
        "expected_contains": ["tour"],
        "answerable": True,
    },
    # ========================================================================
    # FRANSCHHOEK -- BOOKING & PAYMENT
    # ========================================================================
    {
        "id": "FB01",
        "category": "franschhoek_booking",
        "question": "What are the payment terms at La Fontaine? When is the deposit due?",
        "expected": "Full pre-payment 30 days prior. Group bookings 20% deposit.",
        "expected_contains": ["payment", "30"],
        "answerable": True,
    },
    {
        "id": "FB02",
        "category": "franschhoek_booking",
        "question": "Can you re-send or amend my invoice at La Fontaine?",
        "expected": "Not documented. Contact La Fontaine for invoice queries.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "FB03",
        "category": "franschhoek_booking",
        "question": "Is it possible to arrange a late check-out at Avondrood?",
        "expected": "Standard check-out 10:30. Late check-out subject to availability.",
        "expected_contains": ["check"],
        "answerable": True,
    },
    {
        "id": "FB04",
        "category": "franschhoek_booking",
        "question": ("Can we leave our car parked at La Fontaine and check-in later in the day?"),
        "expected": "Not documented. Contact La Fontaine for parking queries.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # FRANSCHHOEK -- SPA & DINING
    # ========================================================================
    {
        "id": "FS01",
        "category": "franschhoek_spa_dining",
        "question": "What spa treatments does La Fontaine offer?",
        "expected": "In-room spa: massages, facials, body wraps. Spa menu available.",
        "expected_contains": ["spa"],
        "answerable": True,
    },
    {
        "id": "FS02",
        "category": "franschhoek_spa_dining",
        "question": "What restaurants do you recommend near Avondrood?",
        "expected": "La Petite Ferme, Epice, Le Bon Vivant, Tuk Tuk, Reuben's, etc.",
        "expected_contains": ["restaurant"],
        "answerable": True,
    },
    # ========================================================================
    # CAPE TOWN -- TOURS & ACTIVITIES
    # ========================================================================
    {
        "id": "CT01",
        "category": "cape_town_tours",
        "question": "Can a Cape Peninsula Tour be booked from POD Camps Bay?",
        "expected": "Yes. Various tours available from Cape Town properties.",
        "expected_contains": ["peninsula"],
        "answerable": True,
    },
    {
        "id": "CT02",
        "category": "cape_town_tours",
        "question": "Are entrance fees included in the tour price at POD Camps Bay?",
        "expected": "Entrance fees typically not included. Check specific tour details.",
        "expected_contains": ["fee"],
        "answerable": True,
    },
    {
        "id": "CT03",
        "category": "cape_town_tours",
        "question": "Is the tour price per person or for the whole group?",
        "expected": "Check Tours & Transfers doc for per-person vs per-vehicle pricing.",
        "expected_contains": ["price"],
        "answerable": True,
    },
    {
        "id": "CT04",
        "category": "cape_town_tours",
        "question": ("Does the Cape Peninsula tour include Chapman's Peak Drive?"),
        "expected": "Tour itinerary details from BHL Tours & Transfers doc.",
        "expected_contains": ["tour"],
        "answerable": True,
    },
    {
        "id": "CT05",
        "category": "cape_town_tours",
        "question": "Will the tour guide pick us up at POD Camps Bay?",
        "expected": "Pick-up arrangements from Tours & Transfers doc.",
        "expected_contains": ["tour"],
        "answerable": True,
    },
    {
        "id": "CT06",
        "category": "cape_town_tours",
        "question": "Can a tour date be changed due to weather or other bookings?",
        "expected": "Not documented. Contact property for rescheduling.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # CAPE TOWN -- RESERVATIONS & LOGISTICS
    # ========================================================================
    {
        "id": "CR01",
        "category": "cape_town_reservations",
        "question": "What is the minimum stay requirement at POD Camps Bay over peak periods?",
        "expected": "Check POD rate card for minimum stay during peak season.",
        "expected_contains": ["stay"],
        "answerable": True,
    },
    {
        "id": "CR02",
        "category": "cape_town_reservations",
        "question": "Can airport transfers be arranged from POD Camps Bay?",
        "expected": "Yes. Airport transfers available. Contact property for details.",
        "expected_contains": ["transfer"],
        "answerable": True,
    },
    {
        "id": "CR03",
        "category": "cape_town_reservations",
        "question": "Is it possible to store luggage before check-in at Blackheath Lodge?",
        "expected": "Not documented in KB. Contact Blackheath Lodge.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "CR04",
        "category": "cape_town_reservations",
        "question": (
            "Is it possible to be allocated a specific room preference, "
            "such as a lighter room at Blackheath?"
        ),
        "expected": "Room preference info from Blackheath info guide.",
        "expected_contains": ["room"],
        "answerable": True,
    },
    # ========================================================================
    # CAMP FIGTREE -- RATES & BOOKING
    # ========================================================================
    {
        "id": "CF01",
        "category": "camp_figtree_rates",
        "question": "Is there any flexibility or wiggle room on the quoted prices at Camp Figtree?",
        "expected": "Not documented. Contact Camp Figtree for rate flexibility.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "CF02",
        "category": "camp_figtree_rates",
        "question": "Does a child count toward the higher rate category at Camp Figtree?",
        "expected": "Children rate policy from Camp Figtree rate card.",
        "expected_contains": ["child"],
        "answerable": True,
    },
    {
        "id": "CF03",
        "category": "camp_figtree_rates",
        "question": "When is the full payment due for Camp Figtree?",
        "expected": "Full pre-payment 30 days prior to arrival.",
        "expected_contains": ["payment"],
        "answerable": True,
    },
    {
        "id": "CF04",
        "category": "camp_figtree_rates",
        "question": "What is Camp Figtree's cancellation policy?",
        "expected": "Cancellation within 30 days forfeits 100%. Must be in writing.",
        "expected_contains": ["cancellation"],
        "answerable": True,
    },
    # ========================================================================
    # CAMP FIGTREE -- ROOMS
    # ========================================================================
    {
        "id": "CFR01",
        "category": "camp_figtree_rooms",
        "question": "Does the room at Camp Figtree have a king or twin beds?",
        "expected": "Room configurations from Camp Figtree fact sheet/brochure.",
        "expected_contains": ["bed"],
        "answerable": True,
    },
    {
        "id": "CFR02",
        "category": "camp_figtree_rooms",
        "question": "Do you have interleading rooms at Camp Figtree for families?",
        "expected": "Room layout from brochure. Contact for interleading availability.",
        "expected_contains": ["room"],
        "answerable": True,
    },
    {
        "id": "CFR03",
        "category": "camp_figtree_rooms",
        "question": "What exactly is included in the 2-night package at Camp Figtree?",
        "expected": "Package details from rate card. Accommodation, meals, game drives.",
        "expected_contains": ["package"],
        "answerable": True,
    },
    # ========================================================================
    # CAMP FIGTREE -- ACTIVITIES & DINING
    # ========================================================================
    {
        "id": "CFA01",
        "category": "camp_figtree_activities",
        "question": "Can you send a list of activities you offer at Camp Figtree?",
        "expected": "Game drives, guided walks, Addo park, horse riding, canoeing, zip-line.",
        "expected_contains": ["game drive"],
        "answerable": True,
    },
    {
        "id": "CFA02",
        "category": "camp_figtree_activities",
        "question": "Should we book the game drive for morning or afternoon at Camp Figtree?",
        "expected": "Both options. Morning at sunrise, afternoon with sundowners.",
        "expected_contains": ["morning"],
        "answerable": True,
    },
    {
        "id": "CFA03",
        "category": "camp_figtree_activities",
        "question": "Is dinner an a la carte menu or a set 3-course meal at Camp Figtree?",
        "expected": "Set menu / table d'hote style at Camp Figtree restaurant.",
        "expected_contains": ["dinner"],
        "answerable": True,
    },
    {
        "id": "CFA04",
        "category": "camp_figtree_activities",
        "question": ("How do I submit dietary notes or special requirements at Camp Figtree?"),
        "expected": "Not documented in KB. Contact Camp Figtree for dietary needs.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "CFA05",
        "category": "camp_figtree_activities",
        "question": (
            "Can you book the Giraffe walk for a specific date and time " "at Camp Figtree?"
        ),
        "expected": "Activities available. Contact Camp Figtree for specific bookings.",
        "expected_contains": ["giraffe"],
        "answerable": True,
    },
    # ========================================================================
    # CAMP FIGTREE -- LOGISTICS
    # ========================================================================
    {
        "id": "CFL01",
        "category": "camp_figtree_logistics",
        "question": (
            "Can you send the recommended directions to Camp Figtree? "
            "Is it true Google Maps takes you via Motherwell?"
        ),
        "expected": "Detailed directions from PE airport. Avoid Motherwell route.",
        "expected_contains": ["direction"],
        "answerable": True,
    },
    {
        "id": "CFL02",
        "category": "camp_figtree_logistics",
        "question": "Is an SUV or 4x4 required for the road to Camp Figtree?",
        "expected": "No. Normal sedan is fine. Road is accessible.",
        "expected_contains": ["vehicle"],
        "answerable": True,
    },
    {
        "id": "CFL03",
        "category": "camp_figtree_logistics",
        "question": "What time should we plan to arrive at Camp Figtree?",
        "expected": "Check-in 14:00. Arrive during daylight.",
        "expected_contains": ["arrive"],
        "answerable": True,
    },
    {
        "id": "CFL04",
        "category": "camp_figtree_logistics",
        "question": "Is Wi-Fi available in the suites at Camp Figtree or just public areas?",
        "expected": "Wi-Fi in restaurant area only, not in suites.",
        "expected_contains": ["wi-fi"],
        "answerable": True,
    },
    {
        "id": "CFL05",
        "category": "camp_figtree_logistics",
        "question": (
            "Do guests including children need to present a passport "
            "for Addo National Park entry?"
        ),
        "expected": "Not documented in KB. Contact Addo National Park directly.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "CFL06",
        "category": "camp_figtree_logistics",
        "question": "Can you arrange an airport transfer to Camp Figtree, and what are the rates?",
        "expected": "Yes, transfers available from PE airport. Route Travel doc.",
        "expected_contains": ["transfer"],
        "answerable": True,
    },
    {
        "id": "CFL07",
        "category": "camp_figtree_logistics",
        "question": "Do you have a parking space available at Camp Figtree?",
        "expected": "Not documented in KB. Contact Camp Figtree.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # PROPERTY DISCOVERY -- GROUP QUERIES
    # ========================================================================
    {
        "id": "PD01",
        "category": "property_discovery",
        "question": "What properties do you have?",
        "expected": "12 properties across 6 regions in South Africa.",
        "expected_contains": ["la fontaine", "avondrood"],
        "answerable": True,
    },
    {
        "id": "PD02",
        "category": "property_discovery",
        "question": "What properties do you have in Franschhoek?",
        "expected": "La Fontaine, Avondrood, The Pink Door.",
        "expected_contains": ["la fontaine", "avondrood"],
        "answerable": True,
    },
    {
        "id": "PD03",
        "category": "property_discovery",
        "question": "What properties do you have near the beach?",
        "expected": "POD Camps Bay, Oyster Box Beach House, Kenton Houses.",
        "expected_contains": ["pod", "beach"],
        "answerable": True,
    },
    {
        "id": "PD04",
        "category": "property_discovery",
        "question": "Which property is best for a family holiday?",
        "expected": "Camp Figtree, Kenton Houses, Burlington Bush.",
        "expected_contains": ["family"],
        "answerable": True,
    },
    {
        "id": "PD05",
        "category": "property_discovery",
        "question": "Which of your properties are best for a safari experience?",
        "expected": "Camp Figtree in the Addo region. Game drives, Addo Elephant Park.",
        "expected_contains": ["camp figtree"],
        "answerable": True,
    },
    {
        "id": "PD06",
        "category": "property_discovery",
        "question": "Do you have properties in the Eastern Cape?",
        "expected": "Yes. Camp Figtree (Addo), The Milner/8A/Pleasance (Grahamstown), Burlington Bush (Salem), Oyster Box/Kenton (Kenton-on-Sea).",
        "expected_contains": ["eastern cape"],
        "answerable": True,
    },
    {
        "id": "PD07",
        "category": "property_discovery",
        "question": "Which property has the best wine tasting experiences nearby?",
        "expected": "Franschhoek properties: La Fontaine, Avondrood, Pink Door.",
        "expected_contains": ["wine"],
        "answerable": True,
    },
    # ========================================================================
    # CROSS-PROPERTY COMPARISONS
    # ========================================================================
    {
        "id": "CP01",
        "category": "cross_comparison",
        "question": "What is the difference between La Fontaine and Avondrood?",
        "expected": "Both in Franschhoek. Compare room types, amenities from info guides.",
        "expected_contains": ["la fontaine", "avondrood"],
        "answerable": True,
    },
    {
        "id": "CP02",
        "category": "cross_comparison",
        "question": "Which is better for couples, POD Camps Bay or Blackheath Lodge?",
        "expected": "Compare both Cape Town properties from their info/brochures.",
        "expected_contains": ["pod"],
        "answerable": True,
    },
    {
        "id": "CP03",
        "category": "cross_comparison",
        "question": "Compare Camp Figtree and Burlington Bush for a nature getaway.",
        "expected": "Camp Figtree has game drives, activities. Burlington Bush more remote.",
        "expected_contains": ["camp figtree"],
        "answerable": True,
    },
    # ========================================================================
    # SPARSE PROPERTIES (limited/no KB)
    # ========================================================================
    {
        "id": "SP01",
        "category": "sparse_properties",
        "question": "What rooms are available at The Milner Hotel?",
        "expected": "Limited info from Milner info guide. Contact for details.",
        "expected_contains": ["milner"],
        "answerable": True,
    },
    {
        "id": "SP02",
        "category": "sparse_properties",
        "question": "What are the rates at 8A Guest House?",
        "expected": "No rate card in KB. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    {
        "id": "SP03",
        "category": "sparse_properties",
        "question": "What activities are available near Burlington Bush?",
        "expected": "Limited info from brochure only. Contact property.",
        "expected_contains": ["burlington"],
        "answerable": True,
    },
    {
        "id": "SP04",
        "category": "sparse_properties",
        "question": "What is the rate per night at Oyster Box Beach House?",
        "expected": "Oyster Box rate card available. Rates from 2025-2026.",
        "expected_contains": ["rate"],
        "answerable": True,
    },
    {
        "id": "SP05",
        "category": "sparse_properties",
        "question": "Tell me about Kenton Houses. What makes them special?",
        "expected": "Brochure info + house comparison doc available.",
        "expected_contains": ["kenton"],
        "answerable": True,
    },
    {
        "id": "SP06",
        "category": "sparse_properties",
        "question": "What is there to do in Grahamstown near The Milner?",
        "expected": "Limited info from Milner info guide. Contact for details.",
        "expected_contains": ["milner"],
        "answerable": True,
    },
    # ========================================================================
    # BOOKING INTENT
    # ========================================================================
    {
        "id": "BK01",
        "category": "booking_intent",
        "question": "I want to book a room",
        "expected": "Ask for property, dates, guests, room preference.",
        "expected_contains": ["property"],
        "answerable": True,
    },
    {
        "id": "BK02",
        "category": "booking_intent",
        "question": "I'd like to make a reservation at Camp Figtree for 2 nights",
        "expected": "Acknowledge Camp Figtree, ask for dates and guests.",
        "expected_contains": ["camp figtree"],
        "answerable": True,
    },
    {
        "id": "BK03",
        "category": "booking_intent",
        "question": (
            "Can you check availability at La Fontaine for 15-18 March " "for 2 adults and 1 child?"
        ),
        "expected": "Acknowledge details, provide rate info, offer contact.",
        "expected_contains": ["la fontaine"],
        "answerable": True,
    },
    {
        "id": "BK04",
        "category": "booking_intent",
        "question": "Can you confirm if the reservation has been made?",
        "expected": "Cannot confirm reservations directly. Contact property.",
        "expected_contains": ["contact"],
        "answerable": False,
    },
    # ========================================================================
    # TYPOS & FUZZY MATCHING
    # ========================================================================
    {
        "id": "TY01",
        "category": "typos_fuzzy",
        "question": "What are the rates at camp figtre?",
        "expected": "Resolves to Camp Figtree. Show rates from rate card.",
        "expected_contains": ["camp figtree"],
        "answerable": True,
    },
    {
        "id": "TY02",
        "category": "typos_fuzzy",
        "question": "Tell me about blackhealth lodge",
        "expected": "Resolves to Blackheath Lodge. Info from Blackheath docs.",
        "expected_contains": ["blackheath"],
        "answerable": True,
    },
    {
        "id": "TY03",
        "category": "typos_fuzzy",
        "question": "Whats available at avondrod?",
        "expected": "Resolves to Avondrood. Info from Avondrood docs.",
        "expected_contains": ["avondrood"],
        "answerable": True,
    },
    {
        "id": "TY04",
        "category": "typos_fuzzy",
        "question": "I want to stay at pod camp bay",
        "expected": "Resolves to POD Camps Bay. Info from POD docs.",
        "expected_contains": ["pod"],
        "answerable": True,
    },
    {
        "id": "TY05",
        "category": "typos_fuzzy",
        "question": "dinner options at la fontane?",
        "expected": "Resolves to La Fontaine. Restaurant info.",
        "expected_contains": ["la fontaine"],
        "answerable": True,
    },
    # ========================================================================
    # OUT-OF-SCOPE / IRRELEVANT
    # ========================================================================
    {
        "id": "OOS01",
        "category": "out_of_scope",
        "question": "What is the capital of South Africa?",
        "expected": "Politely decline. Redirect to Oyster Collection topics.",
        "expected_contains": ["oyster collection"],
        "answerable": True,
    },
    {
        "id": "OOS02",
        "category": "out_of_scope",
        "question": "Can you write me a Python script?",
        "expected": "Politely decline. Redirect to hospitality topics.",
        "expected_contains": ["help"],
        "answerable": True,
    },
    {
        "id": "OOS03",
        "category": "out_of_scope",
        "question": "What is the weather in Cape Town next week?",
        "expected": "Cannot provide weather forecasts. Suggest checking weather services.",
        "expected_contains": ["weather"],
        "answerable": True,
    },
    {
        "id": "OOS04",
        "category": "out_of_scope",
        "question": "Can you recommend hotels in Durban?",
        "expected": "Only assist with Oyster Collection properties. Redirect.",
        "expected_contains": ["oyster"],
        "answerable": True,
    },
    # ========================================================================
    # GREETINGS & BASIC INTERACTION
    # ========================================================================
    {
        "id": "GRT01",
        "category": "greetings",
        "question": "Hello!",
        "expected": "Warm greeting. Ask how they can help.",
        "expected_contains": ["help"],
        "answerable": True,
    },
    {
        "id": "GRT02",
        "category": "greetings",
        "question": "Good morning, I need some help planning my trip",
        "expected": "Warm greeting. Ask about property/region interest.",
        "expected_contains": ["help"],
        "answerable": True,
    },
    {
        "id": "GRT03",
        "category": "greetings",
        "question": "Thank you for your help!",
        "expected": "Warm acknowledgement. Offer further assistance.",
        "expected_contains": ["help"],
        "answerable": True,
    },
]


def query_api(question: str, session_id: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    body: dict = {"message": question}
    if session_id:
        body["session_id"] = session_id

    try:
        resp = httpx.post(
            f"{BASE_URL}/chat",
            json=body,
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
    has_escalation = any(x in lower for x in ["email", "phone", "@", "+27", "contact"])

    # Check expected_contains
    contains_pass = all(term.lower() in lower for term in item.get("expected_contains", []))

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
            "property_id": api_result.get("property_id"),
            "sources": len(api_result.get("sources", [])),
            "answerable": answerable,
        }
        results.append(result)
        categories[cat].append(result)

        icon = {"PASS": "+", "FAIL": "X", "PARTIAL": "~", "DENIED": "-"}[verdict]
        answerable_tag = "" if answerable else " [NOT IN KB]"
        print(
            f"  [{icon}] {item['id']:6s} ({latency:4.1f}s) "
            f"{item['question'][:60]}{answerable_tag}"
        )

    # -- Detailed Report --
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

            print(f"\n  [{verdict_color}] {r['id']}: {r['question'][:80]}{answerable_tag}")
            print(f"  EXPECTED: {r['expected'][:120]}")
            print(f"  ACTUAL:   {r['actual'][:120]}")
            if r["verdict"] in ("DENIED", "FAIL") and r["answerable"]:
                print("  >>> ISSUE: Answer IS in KB but not retrieved/answered!")

    # -- Summary --
    print("\n" + "=" * 100)
    print("  SUMMARY")
    print("=" * 100)

    total = len(results)
    answerable_total = sum(1 for r in results if r.get("answerable", True))
    unanswerable = total - answerable_total
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    partial = sum(1 for r in results if r["verdict"] == "PARTIAL")
    denied = sum(1 for r in results if r["verdict"] == "DENIED")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")

    answerable_passed = sum(
        1 for r in results if r["verdict"] == "PASS" and r.get("answerable", True)
    )
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
    if answerable_total:
        print(
            f"  Accuracy (answerable): {answerable_passed}/{answerable_total}"
            f" ({answerable_passed / answerable_total * 100:.0f}%)"
        )
    print(
        f"  With escalation:       {passed + partial}/{total}"
        f" ({(passed + partial) / total * 100:.0f}%)"
    )
    if unanswerable:
        print(
            f"  Not-in-KB handled:     {unanswerable_correct}/{unanswerable}"
            f" ({unanswerable_correct / unanswerable * 100:.0f}%)"
        )

    print("\n  Per Category:")
    for cat, items in categories.items():
        cat_total = len(items)
        cat_pass = sum(1 for r in items if r["verdict"] == "PASS")
        bar = "#" * int(cat_pass / cat_total * 20) + "." * (20 - int(cat_pass / cat_total * 20))
        print(
            f"    {cat:30s} {cat_pass:2d}/{cat_total:2d} "
            f"[{bar}] {cat_pass / cat_total * 100:.0f}%"
        )

    # -- Regressions --
    regressions = [
        r for r in results if r["verdict"] in ("DENIED", "FAIL") and r.get("answerable", True)
    ]
    if regressions:
        print("\n  RETRIEVAL FAILURES (answerable but denied/failed):")
        for r in regressions:
            print(f"    [{r['verdict']:7s}] {r['id']}: {r['question'][:70]}")

    # Save JSON
    output_path = Path("evaluation_comprehensive_results.json")
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
                "accuracy_pct": round(answerable_passed / answerable_total * 100, 1)
                if answerable_total
                else 0,
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    main()
