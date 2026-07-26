"""
MI NEXUS - Pattern Recognition Engine v2
Pure geometric/statistical rules. No AI, no external API.
Expanded pattern library + reliability-weighted scoring.
"""

# Reliability weights are rough, commonly-cited technical-analysis reference
# points (not guarantees) used only to relatively weigh conflicting signals.
PATTERN_RELIABILITY = {
    "Doji": 0.30,
    "Hammer": 0.65,
    "Inverted Hammer": 0.55,
    "Shooting Star": 0.65,
    "Hanging Man": 0.55,
    "Marubozu": 0.75,
    "Spinning Top": 0.25,
    "Bullish Engulfing": 0.80,
    "Bearish Engulfing": 0.80,
    "Piercing Line": 0.60,
    "Dark Cloud Cover": 0.60,
    "Tweezer Top": 0.50,
    "Tweezer Bottom": 0.50,
    "Harami Bullish": 0.55,
    "Harami Bearish": 0.55,
    "Morning Star": 0.85,
    "Evening Star": 0.85,
    "Three White Soldiers": 0.80,
    "Three Black Crows": 0.80,
    "Rising Three Methods": 0.60,
    "Falling Three Methods": 0.60,
    "Plain Candle Momentum": 0.30,
}


def _last(candles, n):
    return candles[-n:] if len(candles) >= n else []


def detect_patterns(candles):
    """
    Takes a chronological list of Candle objects.
    Returns list of dicts: {"name": str, "signal": "bullish"/"bearish"/"neutral", "weight": float}
    """
    found = []
    if len(candles) < 1:
        return found

    c1 = candles[-1]
    c2 = candles[-2] if len(candles) >= 2 else None
    c3 = candles[-3] if len(candles) >= 3 else None
    c4 = candles[-4] if len(candles) >= 4 else None
    c5 = candles[-5] if len(candles) >= 5 else None

    def add(name, signal):
        found.append({"name": name, "signal": signal, "weight": PATTERN_RELIABILITY.get(name, 0.4)})

    # ---------------- Single-candle patterns ----------------
    if c1.body_ratio() < 0.12:
        add("Doji", "neutral")

    if (c1.body_ratio() < 0.35 and c1.lower_wick_ratio() > 0.5 and c1.upper_wick_ratio() < 0.15):
        if c2 and c2.is_bearish():
            add("Hammer", "bullish")
        elif c2 and c2.is_bullish():
            add("Hanging Man", "bearish")
        else:
            add("Hammer", "bullish")

    if (c1.body_ratio() < 0.35 and c1.upper_wick_ratio() > 0.5 and c1.lower_wick_ratio() < 0.15):
        if c2 and c2.is_bearish():
            add("Inverted Hammer", "bullish")
        else:
            add("Shooting Star", "bearish")

    if c1.body_ratio() > 0.9:
        add("Marubozu", "bullish" if c1.is_bullish() else "bearish")

    if (0.15 < c1.body_ratio() < 0.4 and c1.upper_wick_ratio() > 0.25 and c1.lower_wick_ratio() > 0.25):
        add("Spinning Top", "neutral")

    # ---------------- Two-candle patterns ----------------
    if c2:
        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            add("Bullish Engulfing", "bullish")

        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            add("Bearish Engulfing", "bearish")

        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_bottom < c2.body_bottom
                and c1.body_top > (c2.body_top + c2.body_bottom) / 2
                and c1.body_top < c2.body_top):
            add("Piercing Line", "bullish")

        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top > c2.body_top
                and c1.body_bottom < (c2.body_top + c2.body_bottom) / 2
                and c1.body_bottom > c2.body_bottom):
            add("Dark Cloud Cover", "bearish")

        if abs(c1.wick_top - c2.wick_top) < max(1, c1.total_range * 0.05) and c1.is_bearish() and c2.is_bullish():
            add("Tweezer Top", "bearish")
        if abs(c1.wick_bottom - c2.wick_bottom) < max(1, c1.total_range * 0.05) and c1.is_bullish() and c2.is_bearish():
            add("Tweezer Bottom", "bullish")

        if (c1.body_ratio() < 0.4
                and c1.body_top >= c2.body_top and c1.body_bottom <= c2.body_bottom):
            if c2.is_bearish() and c1.is_bullish():
                add("Harami Bullish", "bullish")
            elif c2.is_bullish() and c1.is_bearish():
                add("Harami Bearish", "bearish")

    # ---------------- Three-candle patterns ----------------
    if c3:
        if (c3.is_bearish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bullish() and c1.body_ratio() > 0.5
                and c1.body_top > (c3.body_top + c3.body_bottom) / 2):
            add("Morning Star", "bullish")

        if (c3.is_bullish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bearish() and c1.body_ratio() > 0.5
                and c1.body_bottom < (c3.body_top + c3.body_bottom) / 2):
            add("Evening Star", "bearish")

        if (c3.is_bullish() and c2.is_bullish() and c1.is_bullish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_bottom > c3.body_bottom and c1.body_bottom > c2.body_bottom):
            add("Three White Soldiers", "bullish")

        if (c3.is_bearish() and c2.is_bearish() and c1.is_bearish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_top < c3.body_top and c1.body_top < c2.body_top):
            add("Three Black Crows", "bearish")

    # ---------------- Five-candle patterns ----------------
    if c5:
        middle_three = [c4, c3, c2]
        if (c5.is_bullish() and c5.body_ratio() > 0.55
                and all(m.body_ratio() < 0.4 for m in middle_three)
                and c1.is_bullish() and c1.body_ratio() > 0.5
                and c1.body_bottom > c5.body_top):
            add("Rising Three Methods", "bullish")

        if (c5.is_bearish() and c5.body_ratio() > 0.55
                and all(m.body_ratio() < 0.4 for m in middle_three)
                and c1.is_bearish() and c1.body_ratio() > 0.5
                and c1.body_top < c5.body_bottom):
            add("Falling Three Methods", "bearish")

    if not found:
        sig = "bullish" if c1.is_bullish() else "bearish"
        add("Plain Candle Momentum", sig)

    return found


def compute_trend_bias(candles, lookback=8):
    """
    Momentum score from body sizes / direction of last N candles,
    plus a simple structure check (recent highs/lows vs earlier highs/lows).
    Returns value between -1 (strong bearish) and +1 (strong bullish).
    """
    recent = _last(candles, lookback)
    if not recent:
        return 0.0

    score = 0.0
    total_weight = 0.0
    for i, c in enumerate(recent):
        w = (i + 1)
        direction = 1 if c.is_bullish() else -1
        score += direction * c.body_ratio() * w
        total_weight += w

    momentum = score / total_weight if total_weight else 0.0

    structure = 0.0
    if len(recent) >= 4:
        mid = len(recent) // 2
        first_half, second_half = recent[:mid], recent[mid:]
        fh_high = max(c.wick_top for c in first_half)
        fh_low = min(c.wick_bottom for c in first_half)
        sh_high = max(c.wick_top for c in second_half)
        sh_low = min(c.wick_bottom for c in second_half)
        # Image y-coords: smaller y = higher price.
        if sh_high < fh_high and sh_low < fh_low:
            structure = 0.3
        elif sh_high > fh_high and sh_low > fh_low:
            structure = -0.3

    combined = momentum * 0.7 + structure * 0.3
    return max(-1.0, min(1.0, combined))


def predict_next_candle(candles):
    """
    Combines pattern signals + trend momentum into a final prediction.
    """
    patterns = detect_patterns(candles)
    trend_bias = compute_trend_bias(candles)

    pattern_score = 0.0
    pattern_weight_sum = 0.0
    breakdown = []
    for p in patterns:
        if p["signal"] == "bullish":
            pattern_score += p["weight"]
        elif p["signal"] == "bearish":
            pattern_score -= p["weight"]
        pattern_weight_sum += p["weight"]
        breakdown.append({
            "name": p["name"],
            "signal": p["signal"],
            "reliability": round(p["weight"] * 100, 0),
        })

    if pattern_weight_sum > 0:
        pattern_score /= pattern_weight_sum

    final_score = (pattern_score * 0.65) + (trend_bias * 0.35)

    direction = "UP" if final_score >= 0 else "DOWN"
    confidence = min(96, max(54, 55 + abs(final_score) * 42))

    if confidence >= 85:
        strength = "VERY STRONG"
    elif confidence >= 72:
        strength = "STRONG"
    elif confidence >= 62:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    return {
        "direction": direction,
        "confidence": round(confidence, 1),
        "strength": strength,
        "patterns": patterns,
        "breakdown": breakdown,
        "trend_bias": round(trend_bias, 3),
        "final_score": round(final_score, 3),
    }
