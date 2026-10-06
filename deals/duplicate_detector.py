import re
import difflib
from decimal import Decimal

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
        # e.g., Tuesday inside everyday or weekdays
        ratio = len(overlap) / max(len(days_set1), len(days_set2))
        return max(0.75, ratio), True

    # Completely different days (e.g. monday vs friday)
    return 0.0, False


def compute_price_similarity(price1, price2, disc1: str, disc2: str) -> float:
    """Compares price and discount percentages."""
    p_score = 0.5

    # Check explicit discount percentage string match (e.g. '20%')
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

    # Compare numeric price
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


def detect_deal_duplicates(deal, candidate_qs=None):
    """
    Analyzes an incoming or existing deal against candidates for the same restaurant.
    
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

    best_match = None
    highest_score = 0.0
    best_reasons = []

    deal_title_desc = f"{deal.title} {deal.description or ''}"

    for cand in candidates:
        cand_title_desc = f"{cand.title} {cand.description or ''}"
        reasons = []

        # 1. Text Similarity (Title & Description)
        text_score = compute_text_similarity(deal_title_desc, cand_title_desc)
        title_only_score = compute_text_similarity(deal.title, cand.title)
        effective_text_score = max(text_score, title_only_score)

        # 2. Day of Week Overlap
        day_score, is_day_compatible = compute_day_match(deal.day_of_week, cand.day_of_week)

        # 3. Price / Discount Similarity
        price_score = compute_price_similarity(
            deal.price, cand.price,
            deal.discount_percentage, cand.discount_percentage
        )

        # 4. Food type match
        food_score = 0.5
        f1 = normalize_text(deal.food_type or "")
        f2 = normalize_text(cand.food_type or "")
        if f1 and f2 and (f1 in f2 or f2 in f1):
            food_score = 0.9

        # Time slot compatibility
        time_score = 0.5
        if deal.has_time_slots and cand.has_time_slots:
            if deal.start_time == cand.start_time and deal.end_time == cand.end_time:
                time_score = 1.0
            else:
                time_score = 0.6
        elif not deal.has_time_slots and not cand.has_time_slots:
            time_score = 0.8

        # If days are totally mutually exclusive (e.g. Mon vs Sat), penalize heavily
        if not is_day_compatible:
            composite_score = (
                (effective_text_score * 0.40) +
                (price_score * 0.20) +
                (food_score * 0.10)
            ) * 0.45  # Heavy penalty
        else:
            composite_score = (
                (effective_text_score * 0.45) +
                (day_score * 0.25) +
                (price_score * 0.20) +
                (time_score * 0.10)
            )

        # Build human-readable reasons for admin
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

    # Flag threshold: 65% composite or >= 80% title similarity with day compatibility
    is_duplicate = (highest_score >= 0.65) or (
        highest_score >= 0.55 and any("Identical active day" in r for r in best_reasons)
    )

    return is_duplicate, best_match, score_percentage, best_reasons
