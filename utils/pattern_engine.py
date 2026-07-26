"""
MI NEXUS - Pattern Recognition Engine v3 (World Pattern Library)
Pure geometric/statistical rules. No AI, no external API.
Covers the full classic candlestick pattern library (Nison/Bulkowski
reference set) across 1, 2, 3, and 5-candle formations.
"""

# Reliability weights are rough, commonly-cited technical-analysis reference
# points (not guarantees) used only to relatively weigh conflicting signals.
PATTERN_RELIABILITY = {
    # --- Single candle ---
    "Doji": 0.30,
    "Long-Legged Doji": 0.30,
    "Dragonfly Doji": 0.62,
    "Gravestone Doji": 0.62,
    "Four-Price Doji": 0.20,
    "Hammer": 0.65,
    "Inverted Hammer": 0.55,
    "Shooting Star": 0.65,
    "Hanging Man": 0.55,
    "Marubozu": 0.75,
    "Spinning Top": 0.25,
    "High Wave Candle": 0.30,
    "Belt Hold Bullish": 0.55,
    "Belt Hold Bearish": 0.55,

    # --- Two candle ---
    "Bullish Engulfing": 0.80,
    "Bearish Engulfing": 0.80,
    "Piercing Line": 0.60,
    "Dark Cloud Cover": 0.60,
    "Tweezer Top": 0.50,
    "Tweezer Bottom": 0.50,
    "Harami Bullish": 0.55,
    "Harami Bearish": 0.55,
    "Harami Cross Bullish": 0.58,
    "Harami Cross Bearish": 0.58,
    "On-Neck Line": 0.40,
    "In-Neck Line": 0.40,
    "Thrusting Line": 0.45,
    "Kicker Bullish": 0.78,
    "Kicker Bearish": 0.78,
    "Meeting Lines Bullish": 0.45,
    "Meeting Lines Bearish": 0.45,

    # --- Three candle ---
    "Morning Star": 0.85,
    "Evening Star": 0.85,
    "Morning Doji Star": 0.87,
    "Evening Doji Star": 0.87,
    "Three White Soldiers": 0.80,
    "Three Black Crows": 0.80,
    "Three Inside Up": 0.65,
    "Three Inside Down": 0.65,
    "Three Outside Up": 0.68,
    "Three Outside Down": 0.68,
    "Abandoned Baby Bullish": 0.88,
    "Abandoned Baby Bearish": 0.88,
    "Stick Sandwich Bullish": 0.55,
    "Stick Sandwich Bearish": 0.55,
    "Tri-Star Bullish": 0.60,
    "Tri-Star Bearish": 0.60,
    "Upside Gap Two Crows": 0.50,
    "Advance Block": 0.45,
    "Deliberation Block": 0.45,

    # --- Five candle / continuation ---
    "Rising Three Methods": 0.60,
    "Falling Three Methods": 0.60,
    "Mat Hold Bullish": 0.62,
    "Mat Hold Bearish": 0.62,

    # --- Fallback ---
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

    def prior_trend_up(idx_from_end, lookback=3):
        """Rough check: were candles before position idx_from_end trending up?"""
        window = candles[max(0, len(candles) - idx_from_end - lookback):len(candles) - idx_from_end]
        if len(window) < 2:
            return None
        ups = sum(1 for c in window if c.is_bullish())
        return ups >= len(window) / 2

    # ================= SINGLE-CANDLE PATTERNS =================
    if c1.total_range > 0 and c1.body_height / c1.total_range < 0.06:
        # True doji variants
        if c1.upper_wick_ratio() > 0.6 and c1.lower_wick_ratio() < 0.15:
            add("Gravestone Doji", "bearish")
        elif c1.lower_wick_ratio() > 0.6 and c1.upper_wick_ratio() < 0.15:
            add("Dragonfly Doji", "bullish")
        elif c1.upper_wick_ratio() > 0.35 and c1.lower_wick_ratio() > 0.35:
            add("Long-Legged Doji", "neutral")
        elif c1.upper_wick_ratio() < 0.1 and c1.lower_wick_ratio() < 0.1:
            add("Four-Price Doji", "neutral")
        else:
            add("Doji", "neutral")
    elif c1.body_ratio() < 0.12:
        add("Doji", "neutral")

    if (c1.body_ratio() < 0.35 and c1.lower_wick_ratio() > 0.5 and c1.upper_wick_ratio() < 0.15):
        was_down = prior_trend_up(1) is False
        if was_down or c2 is None:
            add("Hammer", "bullish")
        else:
            add("Hanging Man", "bearish")

    if (c1.body_ratio() < 0.35 and c1.upper_wick_ratio() > 0.5 and c1.lower_wick_ratio() < 0.15):
        was_down = prior_trend_up(1) is False
        if was_down or c2 is None:
            add("Inverted Hammer", "bullish")
        else:
            add("Shooting Star", "bearish")

    if c1.body_ratio() > 0.9:
        add("Marubozu", "bullish" if c1.is_bullish() else "bearish")

    if (0.15 < c1.body_ratio() < 0.4 and c1.upper_wick_ratio() > 0.25 and c1.lower_wick_ratio() > 0.25):
        add("Spinning Top", "neutral")

    if (c1.body_ratio() < 0.3 and c1.upper_wick_ratio() > 0.3 and c1.lower_wick_ratio() > 0.3
            and c1.total_range > 0):
        add("High Wave Candle", "neutral")

    # Belt Hold: opens at/near the extreme with almost no wick on that side, long body
    if c1.is_bullish() and c1.lower_wick_ratio() < 0.05 and c1.body_ratio() > 0.7:
        add("Belt Hold Bullish", "bullish")
    if c1.is_bearish() and c1.upper_wick_ratio() < 0.05 and c1.body_ratio() > 0.7:
        add("Belt Hold Bearish", "bearish")

    # ================= TWO-CANDLE PATTERNS =================
    if c2:
        # Engulfing
        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            add("Bullish Engulfing", "bullish")
        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            add("Bearish Engulfing", "bearish")

        # Piercing / Dark Cloud
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

        # Tweezer
        if abs(c1.wick_top - c2.wick_top) < max(1, c1.total_range * 0.05) and c1.is_bearish() and c2.is_bullish():
            add("Tweezer Top", "bearish")
        if abs(c1.wick_bottom - c2.wick_bottom) < max(1, c1.total_range * 0.05) and c1.is_bullish() and c2.is_bearish():
            add("Tweezer Bottom", "bullish")

        # Harami / Harami Cross
        if c1.body_top >= c2.body_top and c1.body_bottom <= c2.body_bottom:
            is_cross = c1.body_ratio() < 0.08
            if c2.is_bearish() and (c1.is_bullish() or is_cross):
                add("Harami Cross Bullish" if is_cross else "Harami Bullish", "bullish")
            elif c2.is_bullish() and (c1.is_bearish() or is_cross):
                add("Harami Cross Bearish" if is_cross else "Harami Bearish", "bearish")

        # On-Neck / In-Neck / Thrusting (bearish continuation after down candle, small bullish close near prior low)
        if c2.is_bearish() and c1.is_bullish() and c1.body_ratio() < 0.4:
            if abs(c1.body_top - c2.body_bottom) < c2.total_range * 0.08:
                add("On-Neck Line", "bearish")
            elif c2.body_bottom < c1.body_top < c2.body_bottom + c2.body_height * 0.3:
                add("In-Neck Line", "bearish")
            elif c2.body_bottom + c2.body_height * 0.3 <= c1.body_top < (c2.body_top + c2.body_bottom) / 2:
                add("Thrusting Line", "bearish")

        # Kicker
        if c2.is_bearish() and c1.is_bullish() and c1.body_bottom >= c2.body_top and c1.body_ratio() > 0.7:
            add("Kicker Bullish", "bullish")
        if c2.is_bullish() and c1.is_bearish() and c1.body_top <= c2.body_bottom and c1.body_ratio() > 0.7:
            add("Kicker Bearish", "bearish")

        # Meeting Lines (opposite colors, closes meet at same level)
        if abs(c1.body_bottom - c2.body_top) < c1.total_range * 0.05 and c2.is_bearish() and c1.is_bullish():
            add("Meeting Lines Bullish", "bullish")
        if abs(c1.body_top - c2.body_bottom) < c1.total_range * 0.05 and c2.is_bullish() and c1.is_bearish():
            add("Meeting Lines Bearish", "bearish")

    # ================= THREE-CANDLE PATTERNS =================
    if c3:
        mid_is_doji = c2.body_ratio() < 0.12
        gap_down = c2.body_top < min(c3.body_top, c3.body_bottom)
        gap_up = c2.body_bottom > max(c3.body_top, c3.body_bottom)

        # Morning/Evening Star (+ Doji variants)
        if (c3.is_bearish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bullish() and c1.body_ratio() > 0.5
                and c1.body_top > (c3.body_top + c3.body_bottom) / 2):
            add("Morning Doji Star" if mid_is_doji else "Morning Star", "bullish")

        if (c3.is_bullish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bearish() and c1.body_ratio() > 0.5
                and c1.body_bottom < (c3.body_top + c3.body_bottom) / 2):
            add("Evening Doji Star" if mid_is_doji else "Evening Star", "bearish")

        # Abandoned Baby (star pattern + true price gap both sides)
        if (c3.is_bearish() and mid_is_doji and c1.is_bullish()
                and gap_down and c1.body_bottom > c2.body_top):
            add("Abandoned Baby Bullish", "bullish")
        if (c3.is_bullish() and mid_is_doji and c1.is_bearish()
                and gap_up and c1.body_top < c2.body_bottom):
            add("Abandoned Baby Bearish", "bearish")

        # Three White Soldiers / Three Black Crows
        if (c3.is_bullish() and c2.is_bullish() and c1.is_bullish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_bottom > c3.body_bottom and c1.body_bottom > c2.body_bottom):
            add("Three White Soldiers", "bullish")
        if (c3.is_bearish() and c2.is_bearish() and c1.is_bearish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_top < c3.body_top and c1.body_top < c2.body_top):
            add("Three Black Crows", "bearish")

        # Three Inside Up/Down (Harami followed by confirmation candle)
        if (c3.is_bearish() and c2.is_bullish()
                and c2.body_top <= c3.body_top and c2.body_bottom >= c3.body_bottom
                and c1.is_bullish() and c1.body_top > c3.body_top):
            add("Three Inside Up", "bullish")
        if (c3.is_bullish() and c2.is_bearish()
                and c2.body_top <= c3.body_top and c2.body_bottom >= c3.body_bottom
                and c1.is_bearish() and c1.body_bottom < c3.body_bottom):
            add("Three Inside Down", "bearish")

        # Three Outside Up/Down (Engulfing followed by confirmation candle)
        if (c3.is_bearish() and c2.is_bullish()
                and c2.body_top >= c3.body_top and c2.body_bottom <= c3.body_bottom
                and c1.is_bullish() and c1.body_top > c2.body_top):
            add("Three Outside Up", "bullish")
        if (c3.is_bullish() and c2.is_bearish()
                and c2.body_top >= c3.body_top and c2.body_bottom <= c3.body_bottom
                and c1.is_bearish() and c1.body_bottom < c2.body_bottom):
            add("Three Outside Down", "bearish")

        # Stick Sandwich (down, up, down with matching closes on outer candles)
        if (c3.is_bearish() and c2.is_bullish() and c1.is_bearish()
                and abs(c3.body_bottom - c1.body_bottom) < c3.total_range * 0.06):
            add("Stick Sandwich Bullish", "bullish")
        if (c3.is_bullish() and c2.is_bearish() and c1.is_bullish()
                and abs(c3.body_top - c1.body_top) < c3.total_range * 0.06):
            add("Stick Sandwich Bearish", "bearish")

        # Tri-Star (three consecutive dojis at a turning point)
        if (c3.body_ratio() < 0.12 and c2.body_ratio() < 0.12 and c1.body_ratio() < 0.12):
            if c2.body_top < c3.body_bottom and c2.body_top < c1.body_bottom:
                add("Tri-Star Bullish", "bullish")
            elif c2.body_bottom > c3.body_top and c2.body_bottom > c1.body_top:
                add("Tri-Star Bearish", "bearish")

        # Advance Block / Deliberation (weakening three white soldiers)
        if (c3.is_bullish() and c2.is_bullish() and c1.is_bullish()
                and c3.body_ratio() > c2.body_ratio() > c1.body_ratio()
                and c1.body_ratio() < 0.4):
            add("Advance Block", "bearish")
        elif (c3.is_bullish() and c2.is_bullish() and c1.is_bullish()
                and c3.body_ratio() > 0.5 and c2.body_ratio() > 0.4
                and c1.body_ratio() < 0.25):
            add("Deliberation Block", "bearish")

        # Upside Gap Two Crows
        if (c3.is_bullish() and c2.is_bearish() and c1.is_bearish()
                and c2.body_bottom > c3.body_top
                and c1.body_top > c2.body_top and c1.body_bottom < c2.body_bottom):
            add("Upside Gap Two Crows", "bearish")

    # ================= FIVE-CANDLE PATTERNS =================
    if c5:
        middle_three = [c4, c3, c2]
        if (c5.is_bullish() and c5.body_ratio() > 0.55
                and all(m.body_ratio() < 0.4 for m in middle_three)
                and all(m.body_bottom >= c5.body_bottom for m in middle_three)
                and c1.is_bullish() and c1.body_ratio() > 0.5
                and c1.body_bottom > c5.body_top):
            add("Rising Three Methods", "bullish")

        if (c5.is_bearish() and c5.body_ratio() > 0.55
                and all(m.body_ratio() < 0.4 for m in middle_three)
                and all(m.body_top <= c5.body_top for m in middle_three)
                and c1.is_bearish() and c1.body_ratio() > 0.5
                and c1.body_top < c5.body_bottom):
            add("Falling Three Methods", "bearish")

        # Mat Hold (similar to rising/falling three but with a small gap after the first candle)
        if (c5.is_bullish() and c5.body_ratio() > 0.5
                and c4.is_bullish() and c4.body_ratio() > 0.3
                and c3.body_ratio() < 0.4 and c2.body_ratio() < 0.4
                and c1.is_bullish() and c1.body_top > c5.body_top):
            add("Mat Hold Bullish", "bullish")
        if (c5.is_bearish() and c5.body_ratio() > 0.5
                and c4.is_bearish() and c4.body_ratio() > 0.3
                and c3.body_ratio() < 0.4 and c2.body_ratio() < 0.4
                and c1.is_bearish() and c1.body_bottom < c5.body_bottom):
            add("Mat Hold Bearish", "bearish")

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
