"""
MI NEXUS - Pattern Recognition Engine
Pure geometric/statistical rules. No AI, no external API.
Detects classic candlestick patterns and produces a weighted
bias score used for the next-candle prediction.
"""

PATTERNS = []


def _last(candles, n):
    return candles[-n:] if len(candles) >= n else []


def detect_patterns(candles):
    """
    Takes a chronological list of Candle objects.
    Returns list of dicts: {"name": str, "signal": "bullish"/"bearish", "weight": float}
    """
    found = []
    if len(candles) < 1:
        return found

    c1 = candles[-1]           # most recent candle
    c2 = candles[-2] if len(candles) >= 2 else None
    c3 = candles[-3] if len(candles) >= 3 else None

    # ---------------- Single-candle patterns ----------------

    # Doji: very small body relative to range
    if c1.body_ratio() < 0.12:
        found.append({"name": "Doji", "signal": "neutral", "weight": 0.3})

    # Hammer: small body near top, long lower wick, small upper wick
    if (c1.body_ratio() < 0.35 and c1.lower_wick_ratio() > 0.5
            and c1.upper_wick_ratio() < 0.15):
        signal = "bullish"
        found.append({"name": "Hammer", "signal": signal, "weight": 0.7})

    # Shooting Star / Inverted Hammer: small body near bottom, long upper wick
    if (c1.body_ratio() < 0.35 and c1.upper_wick_ratio() > 0.5
            and c1.lower_wick_ratio() < 0.15):
        found.append({"name": "Shooting Star", "signal": "bearish", "weight": 0.7})

    # Marubozu: full body, tiny/no wicks (strong momentum candle)
    if c1.body_ratio() > 0.9:
        sig = "bullish" if c1.is_bullish() else "bearish"
        found.append({"name": "Marubozu", "signal": sig, "weight": 0.8})

    # Spinning Top: small body, wicks on both sides roughly equal
    if (0.15 < c1.body_ratio() < 0.4 and c1.upper_wick_ratio() > 0.25
            and c1.lower_wick_ratio() > 0.25):
        found.append({"name": "Spinning Top", "signal": "neutral", "weight": 0.25})

    # ---------------- Two-candle patterns ----------------
    if c2:
        # Bullish Engulfing
        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            found.append({"name": "Bullish Engulfing", "signal": "bullish", "weight": 0.85})

        # Bearish Engulfing
        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top <= c2.body_bottom and c1.body_bottom >= c2.body_top):
            found.append({"name": "Bearish Engulfing", "signal": "bearish", "weight": 0.85})

        # Piercing Line (bullish reversal)
        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_bottom < c2.body_bottom
                and c1.body_top > (c2.body_top + c2.body_bottom) / 2):
            found.append({"name": "Piercing Line", "signal": "bullish", "weight": 0.6})

        # Dark Cloud Cover (bearish reversal)
        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top > c2.body_top
                and c1.body_bottom < (c2.body_top + c2.body_bottom) / 2):
            found.append({"name": "Dark Cloud Cover", "signal": "bearish", "weight": 0.6})

        # Tweezer Top / Bottom
        if abs(c1.wick_top - c2.wick_top) < max(1, c1.total_range * 0.05) and c1.is_bearish() and c2.is_bullish():
            found.append({"name": "Tweezer Top", "signal": "bearish", "weight": 0.5})
        if abs(c1.wick_bottom - c2.wick_bottom) < max(1, c1.total_range * 0.05) and c1.is_bullish() and c2.is_bearish():
            found.append({"name": "Tweezer Bottom", "signal": "bullish", "weight": 0.5})

    # ---------------- Three-candle patterns ----------------
    if c3:
        # Morning Star (bullish reversal)
        if (c3.is_bearish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bullish() and c1.body_ratio() > 0.5
                and c1.body_top > (c3.body_top + c3.body_bottom) / 2):
            found.append({"name": "Morning Star", "signal": "bullish", "weight": 0.9})

        # Evening Star (bearish reversal)
        if (c3.is_bullish() and c3.body_ratio() > 0.5
                and c2.body_ratio() < 0.3
                and c1.is_bearish() and c1.body_ratio() > 0.5
                and c1.body_bottom < (c3.body_top + c3.body_bottom) / 2):
            found.append({"name": "Evening Star", "signal": "bearish", "weight": 0.9})

        # Three White Soldiers
        if (c3.is_bullish() and c2.is_bullish() and c1.is_bullish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_bottom > c3.body_bottom and c1.body_bottom > c2.body_bottom):
            found.append({"name": "Three White Soldiers", "signal": "bullish", "weight": 0.85})

        # Three Black Crows
        if (c3.is_bearish() and c2.is_bearish() and c1.is_bearish()
                and c3.body_ratio() > 0.55 and c2.body_ratio() > 0.55 and c1.body_ratio() > 0.55
                and c2.body_top < c3.body_top and c1.body_top < c2.body_top):
            found.append({"name": "Three Black Crows", "signal": "bearish", "weight": 0.85})

    if not found:
        # Fallback: plain candle color momentum
        sig = "bullish" if c1.is_bullish() else "bearish"
        found.append({"name": "Plain Candle Momentum", "signal": sig, "weight": 0.35})

    return found


def compute_trend_bias(candles, lookback=6):
    """
    Simple momentum score from body sizes / direction of last N candles.
    Returns value between -1 (strong bearish) and +1 (strong bullish).
    """
    recent = _last(candles, lookback)
    if not recent:
        return 0.0

    score = 0.0
    total_weight = 0.0
    for i, c in enumerate(recent):
        w = (i + 1)  # recent candles weigh more
        direction = 1 if c.is_bullish() else -1
        score += direction * c.body_ratio() * w
        total_weight += w

    return score / total_weight if total_weight else 0.0


def predict_next_candle(candles):
    """
    Combines pattern signals + trend momentum into a final prediction.
    Returns dict: {
        "direction": "UP"/"DOWN",
        "confidence": float (0-100),
        "patterns": [...],
        "trend_bias": float
    }
    """
    patterns = detect_patterns(candles)
    trend_bias = compute_trend_bias(candles)

    pattern_score = 0.0
    pattern_weight_sum = 0.0
    for p in patterns:
        if p["signal"] == "bullish":
            pattern_score += p["weight"]
        elif p["signal"] == "bearish":
            pattern_score -= p["weight"]
        pattern_weight_sum += p["weight"]

    if pattern_weight_sum > 0:
        pattern_score /= pattern_weight_sum

    # Combine: pattern signal weighted more (65%), trend momentum (35%)
    final_score = (pattern_score * 0.65) + (trend_bias * 0.35)

    direction = "UP" if final_score >= 0 else "DOWN"
    # Confidence scales with signal strength, floored/capped for realism
    confidence = min(95, max(52, 55 + abs(final_score) * 40))

    return {
        "direction": direction,
        "confidence": round(confidence, 1),
        "patterns": patterns,
        "trend_bias": round(trend_bias, 3),
        "final_score": round(final_score, 3),
    }
