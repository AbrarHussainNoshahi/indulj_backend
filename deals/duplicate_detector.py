import os
import re
import json
import logging
import difflib
import requests
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

# Common filler words to ignore when comparing titles & descriptions
STOP_WORDS = {
    "a", "an", "the", "and", "or", "at", "by", "for", "from", "in", "into",
    "of", "on", "onto", "to", "with", "is", "are", "get", "deal", "deals",
    "offer", "offers", "special", "specials", "save", "now", "our", "all"
}

DAY_MAPPINGS = {
    "weekdays": {"monday", "tuesday", "wednesday", "thursday", "friday"},
    "weekends": {"saturday", "sunday"},
    "everyday": {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"},
}


def normalize_text(text: str) -> str:
    """Cleans and lowercases text, stripping punctuation."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s%]", " ", text.lower())
    return " ".join(cleaned.split())


def extract_tokens(text: str) -> set:
    """Extracts meaningful non-stopword tokens and discount keywords."""
    norm = normalize_text(text)
    words = norm.split()
    tokens = {w for w in words if len(w) > 1 and w not in STOP_WORDS}
    return tokens


def extract_discount_tokens(text: str) -> set:
    """Finds discount tokens like '20%', '50%', 'bogo', 'free'."""
    norm = normalize_text(text)
    discounts = set(re.findall(r"\b\d+%", norm))
    if "bogo" in norm or "buy one get one" in norm:
        discounts.add("bogo")
    if "half price" in norm or "half off" in norm:
        discounts.add("50%")
    if "free" in norm:
        discounts.add("free")
    return discounts


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Computes a combined similarity score (0.0 to 1.0) using:
    - Jaccard token overlap
    - SequenceMatcher ratio
    - Discount keyword overlap
    """
    norm1, norm2 = normalize_text(text1), normalize_text(text2)
    if not norm1 or not norm2:
        return 0.0

    if norm1 == norm2:
        return 1.0

    # Sequence matcher ratio
    seq_ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()

    # Token overlap (Jaccard similarity)
    tokens1, tokens2 = extract_tokens(text1), extract_tokens(text2)
    if tokens1 and tokens2:
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        jaccard = len(intersection) / len(union) if union else 0.0
    else:
        jaccard = 0.0

    # Boost if discount tokens match (e.g. both contain '20%')
    disc1, disc2 = extract_discount_tokens(text1), extract_discount_tokens(text2)
    disc_bonus = 0.0
    if disc1 and disc2 and disc1.intersection(disc2):
        disc_bonus = 0.15

    # Blended score
    score = (seq_ratio * 0.45) + (jaccard * 0.55) + disc_bonus
    return min(1.0, score)


def compute_day_match(day1: str, day2: str) -> tuple[float, bool]:
    """
    Compares two days of the week.
    Returns (score, is_compatible).
    """
    d1 = (day1 or "everyday").lower()
    d2 = (day2 or "everyday").lower()

    if d1 == d2:
        return 1.0, True

    days_set1 = DAY_MAPPINGS.get(d1, {d1})
    days_set2 = DAY_MAPPINGS.get(d2, {d2})

    overlap = days_set1.intersection(days_set2)
    if overlap:
        ratio = len(overlap) / max(len(days_set1), len(days_set2))
        return max(0.75, ratio), True

    return 0.0, False


def compute_price_similarity(price1, price2, disc1: str = "", disc2: str = "") -> float:
    """Compares price and discount percentages."""
    p_score = 0.5

    d1_clean = re.sub(r"[^\d]", "", str(disc1 or ""))
    d2_clean = re.sub(r"[^\d]", "", str(disc2 or ""))
    if d1_clean and d2_clean:
        if d1_clean == d2_clean:
            return 1.0
        try:
            diff = abs(int(d1_clean) - int(d2_clean))
            if diff <= 5:
                return 0.8
        except ValueError:
            pass

    try:
        val1 = float(price1 or 0)
        val2 = float(price2 or 0)
        if val1 > 0 and val2 > 0:
            if val1 == val2:
                p_score = 0.95
            else:
                ratio = min(val1, val2) / max(val1, val2)
                p_score = ratio if ratio > 0.7 else 0.3
    except (ValueError, TypeError):
        pass

    return p_score


# ─────────────────────────────────────────────────────────────
# GEMINI AI DUPLICATE CHECKER (AI TIER)
# ─────────────────────────────────────────────────────────────
def check_with_gemini_ai(item_type: str, new_item_data: dict, candidate_list: list[dict]):
    """
    Calls Google Gemini 1.5 Flash via REST API to semantically evaluate
    whether a promotion is a duplicate of existing promotions.
    Returns parsed JSON dict or None on failure.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    api_key = str(api_key).strip()
    if not api_key:
        return None

    prompt = (
        f"You are an AI restaurant promotion auditor. Analyze if the NEW {item_type} is a duplicate "
        f"or conflicting re-submission of any of the EXISTING active/pending {item_type}s for the SAME restaurant.\n\n"
        f"NEW {item_type.upper()}:\n{json.dumps(new_item_data, indent=2)}\n\n"
        f"EXISTING {item_type.upper()}S FOR THIS RESTAURANT:\n{json.dumps(candidate_list, indent=2)}\n\n"
        "Return ONLY a JSON object (no markdown, no backticks, no code fence):\n"
        "{\n"
        '  "is_duplicate": true or false,\n'
        '  "matched_id": <integer id of closest matching promotion, or null>,\n'
        '  "similarity_score": <number between 0 and 100>,\n'
        '  "reasons": ["short bullet explanation 1", "short bullet explanation 2"]\n'
        "}"
    )

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }

    models_to_try = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]

    for model in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = requests.post(url, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                parsed = json.loads(raw_text)
                logger.info(f"Gemini AI duplicate check succeeded using model {model}")
                return parsed
            else:
                logger.debug(f"Gemini AI model {model} returned status {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.info(f"Gemini AI model {model} error: {e}")

    return None


# ─────────────────────────────────────────────────────────────
# DEAL DUPLICATE DETECTOR
# ─────────────────────────────────────────────────────────────
def detect_deal_duplicates(deal, candidate_qs=None):
    """
    Analyzes an incoming or existing deal against candidates for the same restaurant.
    Uses Gemini AI if configured, with an algorithmic local fallback.
    Returns:
        (is_duplicate: bool, best_match_deal, score: float, reasons: list[str])
    """
    from .models import Deal

    if not deal.restaurant:
        return False, None, 0.0, []

    if candidate_qs is None:
        candidate_qs = Deal.objects.filter(
            restaurant=deal.restaurant,
            status__in=["active", "pending"],
        )

    if deal.id:
        candidate_qs = candidate_qs.exclude(pk=deal.id)

    candidates = list(candidate_qs.select_related("restaurant", "submitted_by"))
    if not candidates:
        return False, None, 0.0, []

    new_deal_data = {
        "id": deal.id,
        "title": deal.title,
        "description": deal.description,
        "price": str(deal.price),
        "discount_percentage": deal.discount_percentage,
        "day_of_week": deal.day_of_week,
        "has_time_slots": deal.has_time_slots,
        "start_time": str(deal.start_time) if deal.start_time else None,
        "end_time": str(deal.end_time) if deal.end_time else None,
        "food_type": deal.food_type,
    }

    candidate_list = [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "price": str(c.price),
            "discount_percentage": c.discount_percentage,
            "day_of_week": c.day_of_week,
            "has_time_slots": c.has_time_slots,
            "start_time": str(c.start_time) if c.start_time else None,
            "end_time": str(c.end_time) if c.end_time else None,
            "food_type": c.food_type,
            "status": c.status,
        }
        for c in candidates
    ]

    # 1. Try Gemini AI
    gemini_result = check_with_gemini_ai("deal", new_deal_data, candidate_list)
    if gemini_result and isinstance(gemini_result, dict):
        matched_id = gemini_result.get("matched_id")
        matched_deal = next((c for c in candidates if c.id == matched_id), None)
        score = float(gemini_result.get("similarity_score", 0.0))
        is_dup = bool(gemini_result.get("is_duplicate", False)) or score >= 65.0
        reasons = gemini_result.get("reasons", [])
        if not reasons:
            reasons = [f"AI match confidence: {score}%"]
        if matched_deal and not any(str(matched_deal.id) in r for r in reasons):
            reasons.append(f"Matches Deal #{matched_deal.id}: '{matched_deal.title}' ({matched_deal.status.capitalize()})")

        return is_dup, matched_deal, round(score, 1), reasons

    # 2. Local Fallback Heuristic
    best_match = None
    highest_score = 0.0
    best_reasons = []

    deal_title_desc = f"{deal.title} {deal.description or ''}"

    for cand in candidates:
        cand_title_desc = f"{cand.title} {cand.description or ''}"
        reasons = []

        text_score = compute_text_similarity(deal_title_desc, cand_title_desc)
        title_only_score = compute_text_similarity(deal.title, cand.title)
        effective_text_score = max(text_score, title_only_score)

        day_score, is_day_compatible = compute_day_match(deal.day_of_week, cand.day_of_week)

        price_score = compute_price_similarity(
            deal.price, cand.price,
            deal.discount_percentage, cand.discount_percentage
        )

        food_score = 0.5
        f1 = normalize_text(deal.food_type or "")
        f2 = normalize_text(cand.food_type or "")
        if f1 and f2 and (f1 in f2 or f2 in f1):
            food_score = 0.9

        time_score = 0.5
        if deal.has_time_slots and cand.has_time_slots:
            if deal.start_time == cand.start_time and deal.end_time == cand.end_time:
                time_score = 1.0
            else:
                time_score = 0.6
        elif not deal.has_time_slots and not cand.has_time_slots:
            time_score = 0.8

        if not is_day_compatible:
            composite_score = (
                (effective_text_score * 0.40) +
                (price_score * 0.20) +
                (food_score * 0.10)
            ) * 0.45
        else:
            composite_score = (
                (effective_text_score * 0.45) +
                (day_score * 0.25) +
                (price_score * 0.20) +
                (time_score * 0.10)
            )

        reasons.append(f"Same Restaurant: {deal.restaurant.name}")

        if effective_text_score >= 0.70:
            reasons.append(f"High text similarity ({int(effective_text_score * 100)}% wording overlap)")
        elif effective_text_score >= 0.50:
            reasons.append(f"Moderate text similarity ({int(effective_text_score * 100)}% wording overlap)")

        if day_score >= 0.90:
            reasons.append(f"Identical active day: {deal.day_of_week.capitalize()}")
        elif day_score >= 0.70:
            reasons.append(f"Overlapping schedule: {deal.day_of_week.capitalize()} vs {cand.day_of_week.capitalize()}")

        if price_score >= 0.90:
            if deal.discount_percentage and cand.discount_percentage:
                reasons.append(f"Matching discount: {deal.discount_percentage}")
            else:
                reasons.append(f"Identical price: ${deal.price}")

        if time_score >= 0.90 and deal.has_time_slots:
            reasons.append(f"Same time slot ({deal.start_time} - {deal.end_time})")

        reasons.append(f"Matches Deal #{cand.id}: '{cand.title}' ({cand.status.capitalize()})")

        if composite_score > highest_score:
            highest_score = composite_score
            best_match = cand
            best_reasons = reasons

    score_percentage = round(highest_score * 100, 1)
    is_duplicate = (highest_score >= 0.65) or (
        highest_score >= 0.55 and any("Identical active day" in r for r in best_reasons)
    )

    return is_duplicate, best_match, score_percentage, best_reasons


# ─────────────────────────────────────────────────────────────
# HAPPY HOUR DUPLICATE DETECTOR
# ─────────────────────────────────────────────────────────────
def detect_happy_hour_duplicates(happy_hour, candidate_qs=None):
    """
    Analyzes an incoming or existing happy hour against candidates for the same restaurant.
    Uses Gemini AI if configured, with an algorithmic local fallback.
    Returns:
        (is_duplicate: bool, best_match_hh, score: float, reasons: list[str])
    """
    from happy_hours.models import HappyHour

    if not happy_hour.restaurant:
        return False, None, 0.0, []

    if candidate_qs is None:
        candidate_qs = HappyHour.objects.filter(
            restaurant=happy_hour.restaurant,
            status__in=["active", "upcoming", "pending"],
        )

    if happy_hour.id:
        candidate_qs = candidate_qs.exclude(pk=happy_hour.id)

    candidates = list(candidate_qs.select_related("restaurant", "submitted_by"))
    if not candidates:
        return False, None, 0.0, []

    new_hh_data = {
        "id": happy_hour.id,
        "title": happy_hour.title,
        "description": happy_hour.description,
        "date": str(happy_hour.date) if happy_hour.date else None,
        "start_time": str(happy_hour.start_time) if happy_hour.start_time else None,
        "end_time": str(happy_hour.end_time) if happy_hour.end_time else None,
        "discount_offer": happy_hour.discount_offer,
        "event_type": happy_hour.event_type,
        "vibe": happy_hour.vibe,
    }

    candidate_list = [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "date": str(c.date) if c.date else None,
            "start_time": str(c.start_time) if c.start_time else None,
            "end_time": str(c.end_time) if c.end_time else None,
            "discount_offer": c.discount_offer,
            "event_type": c.event_type,
            "vibe": c.vibe,
            "status": c.status,
        }
        for c in candidates
    ]

    # 1. Try Gemini AI
    gemini_result = check_with_gemini_ai("happy hour", new_hh_data, candidate_list)
    if gemini_result and isinstance(gemini_result, dict):
        matched_id = gemini_result.get("matched_id")
        matched_hh = next((c for c in candidates if c.id == matched_id), None)
        score = float(gemini_result.get("similarity_score", 0.0))
        is_dup = bool(gemini_result.get("is_duplicate", False)) or score >= 65.0
        reasons = gemini_result.get("reasons", [])
        if not reasons:
            reasons = [f"AI match confidence: {score}%"]
        if matched_hh and not any(str(matched_hh.id) in r for r in reasons):
            reasons.append(f"Matches Happy Hour #{matched_hh.id}: '{matched_hh.title}' ({matched_hh.status.capitalize()})")

        return is_dup, matched_hh, round(score, 1), reasons

    # 2. Local Fallback Heuristic
    best_match = None
    highest_score = 0.0
    best_reasons = []

    hh_title_desc = f"{happy_hour.title} {happy_hour.description or ''}"

    for cand in candidates:
        cand_title_desc = f"{cand.title} {cand.description or ''}"
        reasons = []

        text_score = compute_text_similarity(hh_title_desc, cand_title_desc)
        title_only_score = compute_text_similarity(happy_hour.title, cand.title)
        effective_text_score = max(text_score, title_only_score)

        # Date match
        date_score = 0.5
        same_date = False
        if happy_hour.date and cand.date:
            if happy_hour.date == cand.date:
                date_score = 1.0
                same_date = True
            else:
                date_score = 0.2
        elif not happy_hour.date and not cand.date:
            date_score = 0.8

        # Time match
        time_score = 0.5
        if happy_hour.start_time and cand.start_time:
            if happy_hour.start_time == cand.start_time and happy_hour.end_time == cand.end_time:
                time_score = 1.0
            else:
                time_score = 0.6

        # Discount match
        disc_score = compute_price_similarity(0, 0, happy_hour.discount_offer, cand.discount_offer)

        composite_score = (
            (effective_text_score * 0.45) +
            (date_score * 0.25) +
            (time_score * 0.15) +
            (disc_score * 0.15)
        )

        reasons.append(f"Same Restaurant: {happy_hour.restaurant.name}")

        if effective_text_score >= 0.70:
            reasons.append(f"High text similarity ({int(effective_text_score * 100)}% wording overlap)")
        elif effective_text_score >= 0.50:
            reasons.append(f"Moderate text similarity ({int(effective_text_score * 100)}% wording overlap)")

        if same_date:
            reasons.append(f"Identical Date: {happy_hour.date}")

        if time_score >= 0.90 and happy_hour.start_time:
            reasons.append(f"Same Time Slot ({happy_hour.start_time} - {happy_hour.end_time})")

        if happy_hour.discount_offer and cand.discount_offer and disc_score >= 0.8:
            reasons.append(f"Matching Discount Offer: {happy_hour.discount_offer}")

        reasons.append(f"Matches Happy Hour #{cand.id}: '{cand.title}' ({cand.status.capitalize()})")

        if composite_score > highest_score:
            highest_score = composite_score
            best_match = cand
            best_reasons = reasons

    score_percentage = round(highest_score * 100, 1)
    is_duplicate = (highest_score >= 0.65) or (
        highest_score >= 0.55 and any("Identical Date" in r for r in best_reasons)
    )

    return is_duplicate, best_match, score_percentage, best_reasons
