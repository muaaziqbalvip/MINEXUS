"""
MI NEXUS - Pattern Recognition Engine v4 (Statistically-Weighted World Pattern Library)
Pure geometric/statistical rules. No AI, no external API.
Covers the full classic candlestick pattern library (Nison/Bulkowski
reference set) across 1, 2, 3, and 5-candle formations.

RELIABILITY WEIGHTS - v4 methodology note:
Weights below have been recalibrated using widely-published, independent
technical-analysis research on real-world candlestick performance (large
historical backtests across thousands of instances per pattern). Two
important, evidence-based corrections from that research are applied here:

1. Some "textbook" patterns perform close to random (~50-55%) despite being
   popular/well-known — these get LOWER weights even though they're easy to
   spot, since easy-to-spot != reliable. Examples: Hanging Man, Shooting
   Star, and Matching Low have all been found to hover near coin-flip odds
   in large independent backtests, so they contribute only a small nudge
   to the final score rather than being treated as strong signals.
2. Patterns with strong, consistent directional performance across large
   samples (e.g. Three-Line-Strike-style reversals, Morning/Evening Star,
   Abandoned Baby, Three White Soldiers/Black Crows) get HIGHER weights,
   since they've shown more consistent outcomes historically.

These are still probabilistic tendencies, not guarantees — no pattern
predicts the market with certainty, and past statistical performance is
not a promise of future performance.
"""

from utils.technical_indicators import get_technical_confluence

PATTERN_RELIABILITY = {
    # --- Single candle ---
    # NOTE: Several single-candle patterns are popular/easy to spot but have
    # shown close-to-random real-world directional performance in large
    # independent backtests, so their weights are intentionally modest.
    "Doji": 0.28,
    "Long-Legged Doji": 0.28,
    "Dragonfly Doji": 0.58,
    "Gravestone Doji": 0.58,
    "Four-Price Doji": 0.18,
    "Hammer": 0.58,
    "Inverted Hammer": 0.50,
    "Shooting Star": 0.48,          # near-random in large backtests; kept modest
    "Hanging Man": 0.42,            # near-random / weak in large backtests
    "Marubozu": 0.72,
    "Spinning Top": 0.22,
    "High Wave Candle": 0.26,
    "Belt Hold Bullish": 0.50,
    "Belt Hold Bearish": 0.50,

    # --- Two candle ---
    "Bullish Engulfing": 0.78,
    "Bearish Engulfing": 0.78,
    "Piercing Line": 0.58,
    "Dark Cloud Cover": 0.58,
    "Tweezer Top": 0.46,
    "Tweezer Bottom": 0.46,
    "Harami Bullish": 0.52,
    "Harami Bearish": 0.52,
    "Harami Cross Bullish": 0.55,
    "Harami Cross Bearish": 0.55,
    "On-Neck Line": 0.38,
    "In-Neck Line": 0.38,
    "Thrusting Line": 0.42,
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

    # --- Additional subtle/small patterns ---
    "Doji Star Bullish": 0.55,
    "Doji Star Bearish": 0.55,
    "Homing Pigeon": 0.55,
    "Matching Low": 0.38,     # textbook says bullish reversal, but real-world tends toward continuation - kept modest
    "Matching High": 0.38,
    "Separating Lines Bullish": 0.50,
    "Separating Lines Bearish": 0.50,
    "Ladder Bottom": 0.65,
    "Ladder Top": 0.60,
    "Concealing Baby Swallow": 0.68,
    "Unique Three River Bottom": 0.72,
    "Two Crows": 0.55,
    "Downside Gap Three Methods": 0.55,
    "Long Day Bullish": 0.35,
    "Long Day Bearish": 0.35,
    "Short Day": 0.20,
    "Rickshaw Man": 0.30,
    "Gapping Doji Bullish": 0.45,
    "Gapping Doji Bearish": 0.45,
    "Three Stars in the South": 0.62,
    "Breakaway Bullish": 0.58,
    "Breakaway Bearish": 0.58,
    "Side-by-Side White Lines": 0.42,
    "Descending Hawk": 0.45,
    "Ascending Hawk": 0.45,
    "Tasuki Gap Bullish": 0.50,
    "Tasuki Gap Bearish": 0.50,
    "Three-Line Strike Bullish": 0.72,
    "Three-Line Strike Bearish": 0.72,
    "Engulfing Bar (Momentum)": 0.55,
    "Inside Bar": 0.35,
    "Outside Bar": 0.45,
    "Pin Bar Bullish": 0.60,
    "Pin Bar Bearish": 0.60,
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

        # Doji Star: long candle followed by a doji that gaps away from the body
        if c1.body_ratio() < 0.12 and c2.body_ratio() > 0.5:
            if c2.is_bearish() and c1.body_bottom > c2.body_top:
                add("Doji Star Bullish", "bullish")
            elif c2.is_bullish() and c1.body_top < c2.body_bottom:
                add("Doji Star Bearish", "bearish")

        # Homing Pigeon: small bearish candle fully inside a larger bearish candle (bullish reversal)
        if (c2.is_bearish() and c1.is_bearish() and c1.body_ratio() < 0.5
                and c1.body_top <= c2.body_top and c1.body_bottom >= c2.body_bottom):
            add("Homing Pigeon", "bullish")

        # Matching Low / High: two candles closing at (almost) the same level
        if (c2.is_bearish() and c1.is_bearish()
                and abs(c1.body_bottom - c2.body_bottom) < c1.total_range * 0.04):
            add("Matching Low", "bullish")
        if (c2.is_bullish() and c1.is_bullish()
                and abs(c1.body_top - c2.body_top) < c1.total_range * 0.04):
            add("Matching High", "bearish")

        # Separating Lines: opposite-colored candles that open at the same level, trend continues
        if (abs(c1.body_bottom - c2.body_bottom) < c1.total_range * 0.04
                and c2.is_bearish() and c1.is_bullish() and c1.body_ratio() > 0.5):
            add("Separating Lines Bullish", "bullish")
        if (abs(c1.body_top - c2.body_top) < c1.total_range * 0.04
                and c2.is_bullish() and c1.is_bearish() and c1.body_ratio() > 0.5):
            add("Separating Lines Bearish", "bearish")

        # Gapping Doji: doji that gaps clearly away from the prior candle's body
        if c1.body_ratio() < 0.12:
            if c2.is_bearish() and c1.body_bottom > c2.body_top + c2.total_range * 0.03:
                add("Gapping Doji Bullish", "bullish")
            elif c2.is_bullish() and c1.body_top < c2.body_bottom - c2.total_range * 0.03:
                add("Gapping Doji Bearish", "bearish")

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

        # Two Crows (simpler variant: bullish then two bearish candles eating into the body)
        if (c3.is_bullish() and c3.body_ratio() > 0.5 and c2.is_bearish() and c1.is_bearish()
                and c2.body_top > c3.body_top and c1.body_bottom > c3.body_bottom
                and c1.body_bottom < c2.body_bottom):
            add("Two Crows", "bearish")

        # Ladder Bottom (three falling candles then a small-bodied reversal candle with a gap)
        if (c3.is_bearish() and c2.is_bearish() and c1.is_bullish()
                and c3.body_top > c2.body_top > (c2.body_bottom)
                and c1.lower_wick_ratio() < 0.2 and c1.body_ratio() > 0.3
                and c1.body_bottom >= c2.body_bottom):
            add("Ladder Bottom", "bullish")

        # Ladder Top (three rising candles then a small-bodied reversal candle)
        if (c3.is_bullish() and c2.is_bullish() and c1.is_bearish()
                and c3.body_bottom < c2.body_bottom < c2.body_top
                and c1.upper_wick_ratio() < 0.2 and c1.body_ratio() > 0.3
                and c1.body_top <= c2.body_top):
            add("Ladder Top", "bearish")

        # Concealing Baby Swallow (two black marubozu, then a candle whose body engulfs prior wick)
        if (c3.is_bearish() and c3.body_ratio() > 0.85
                and c2.is_bearish() and c2.body_ratio() > 0.85
                and c1.is_bearish() and c1.body_top > c2.body_bottom
                and c1.wick_bottom < c2.body_bottom):
            add("Concealing Baby Swallow", "bullish")

        # Unique Three River Bottom (long bearish, small bearish with lower low, small bullish)
        if (c3.is_bearish() and c3.body_ratio() > 0.5
                and c2.is_bearish() and c2.body_bottom < c3.body_bottom and c2.body_ratio() < 0.4
                and c1.is_bullish() and c1.body_ratio() < 0.4 and c1.body_top < c2.body_top):
            add("Unique Three River Bottom", "bullish")

        # Downside Gap Three Methods (two bearish candles with a gap, then a bullish candle closing the gap)
        if (c3.is_bearish() and c2.is_bearish()
                and c2.body_top < c3.body_bottom
                and c1.is_bullish() and c1.body_bottom <= c2.body_top and c1.body_top >= c3.body_bottom):
            add("Downside Gap Three Methods", "bearish")

        # Three Stars in the South (rare): three small, decreasing bearish
        # candles after a downtrend, signaling seller exhaustion
        if (c3.is_bearish() and c2.is_bearish() and c1.is_bearish()
                and c3.body_ratio() > c2.body_ratio() > c1.body_ratio()
                and c1.body_ratio() < 0.35
                and c2.body_bottom >= c3.body_bottom and c1.body_bottom >= c2.body_bottom):
            add("Three Stars in the South", "bullish")

        # Breakaway (5-candle textbook pattern approximated with 3 here):
        # strong move candle, small-bodied follow-through, then a strong
        # candle back in the opposite direction - momentum exhaustion cue
        if (c3.body_ratio() > 0.6 and c2.body_ratio() < 0.35):
            if c3.is_bearish() and c1.is_bullish() and c1.body_ratio() > 0.5 and c1.body_top > c3.body_top:
                add("Breakaway Bullish", "bullish")
            elif c3.is_bullish() and c1.is_bearish() and c1.body_ratio() > 0.5 and c1.body_bottom < c3.body_bottom:
                add("Breakaway Bearish", "bearish")

        # Descending/Ascending Hawk: engulfing-like pair but with overlapping
        # opens (weaker version of engulfing, still a caution signal)
        if (c2.is_bullish() and c1.is_bearish()
                and c1.body_top < c2.body_top and c1.body_bottom > c2.body_bottom
                and c1.body_ratio() > 0.3):
            add("Descending Hawk", "bearish")
        if (c2.is_bearish() and c1.is_bullish()
                and c1.body_top < c2.body_top and c1.body_bottom > c2.body_bottom
                and c1.body_ratio() > 0.3):
            add("Ascending Hawk", "bullish")

    # Side-by-Side White Lines: two similar-sized bullish candles with close opens (continuation)
    if c2 and c1.is_bullish() and c2.is_bullish():
        if (abs(c1.body_ratio() - c2.body_ratio()) < 0.15
                and abs(c1.body_bottom - c2.body_bottom) < c1.total_range * 0.08
                and c1.body_ratio() > 0.4):
            add("Side-by-Side White Lines", "bullish")

    # Tasuki Gap: trend candle, gap continuation candle, then a pullback
    # candle that doesn't fully close the gap (continuation signal)
    if c3 and c2 and c1:
        if (c3.is_bullish() and c2.is_bullish() and c2.body_bottom > c3.body_top
                and c1.is_bearish() and c1.body_top > c3.body_top and c1.body_bottom < c2.body_bottom):
            add("Tasuki Gap Bullish", "bullish")
        if (c3.is_bearish() and c2.is_bearish() and c2.body_top < c3.body_bottom
                and c1.is_bullish() and c1.body_bottom < c3.body_bottom and c1.body_top > c2.body_top):
            add("Tasuki Gap Bearish", "bearish")

    # Three-Line Strike: three candles same direction, then a fourth candle
    # that fully reverses all three - strong reversal signal
    if c4 and c3 and c2 and c1:
        if (c4.is_bullish() and c3.is_bullish() and c2.is_bullish()
                and c3.body_bottom >= c4.body_bottom and c2.body_bottom >= c3.body_bottom
                and c1.is_bearish() and c1.body_top >= c2.body_top and c1.body_bottom <= c4.body_bottom):
            add("Three-Line Strike Bearish", "bearish")
        if (c4.is_bearish() and c3.is_bearish() and c2.is_bearish()
                and c3.body_top <= c4.body_top and c2.body_top <= c3.body_top
                and c1.is_bullish() and c1.body_bottom <= c2.body_bottom and c1.body_top >= c4.body_top):
            add("Three-Line Strike Bullish", "bullish")

    # Inside Bar / Outside Bar (simple containment/expansion context patterns)
    if c2:
        if c1.wick_top >= c2.wick_top and c1.wick_bottom <= c2.wick_bottom:
            add("Outside Bar", "bullish" if c1.is_bullish() else "bearish")
        elif c1.wick_top <= c2.wick_top and c1.wick_bottom >= c2.wick_bottom:
            add("Inside Bar", "neutral")

    # Pin Bar (forex/price-action term for hammer/shooting-star-like rejection candles)
    if c1.body_ratio() < 0.3:
        if c1.lower_wick_ratio() > 0.6:
            add("Pin Bar Bullish", "bullish")
        elif c1.upper_wick_ratio() > 0.6:
            add("Pin Bar Bearish", "bearish")

    # ================= CANDLE-SIZE CLASSIFICATION (context, not a signal) =================
    if c1.body_ratio() > 0.6 and c1.total_range > 0:
        add("Long Day Bullish" if c1.is_bullish() else "Long Day Bearish",
            "bullish" if c1.is_bullish() else "bearish")
    elif c1.body_ratio() < 0.2:
        add("Short Day", "neutral")

    if (c1.body_ratio() < 0.15 and 0.2 < c1.upper_wick_ratio() < 0.5
            and 0.2 < c1.lower_wick_ratio() < 0.5):
        add("Rickshaw Man", "neutral")

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


def compute_market_choppiness(candles, lookback=8):
    """
    Measures how indecisive/choppy recent price action has been by counting
    direction flips (green->red->green...) in the last N candles. Choppy
    markets should lower our confidence since patterns are less reliable
    in a sideways/indecisive tape.
    Returns 0.0 (clean trending) to 1.0 (very choppy/indecisive).
    """
    recent = _last(candles, lookback)
    if len(recent) < 3:
        return 0.0

    flips = 0
    for i in range(1, len(recent)):
        prev_up = recent[i - 1].is_bullish()
        curr_up = recent[i].is_bullish()
        if prev_up != curr_up:
            flips += 1

    max_possible_flips = len(recent) - 1
    return flips / max_possible_flips if max_possible_flips else 0.0


def compute_support_resistance_context(candles, lookback=12):
    """
    Fibonacci-zone-aware support/resistance nudge (v2). Instead of a flat
    cutoff, the recent candle's position inside the swing-high/swing-low
    range is mapped onto the classic Fibonacci retracement levels
    (23.6% / 38.2% / 50% / 61.8% / 78.6%) - the same zones traders watch
    for pullback/bounce reactions - for a graded bias instead of an
    all-or-nothing threshold.
    Returns a small bias value between -0.20 and +0.20.
    """
    recent = _last(candles, lookback)
    if len(recent) < 4:
        return 0.0

    swing_high = min(c.wick_top for c in recent)     # smaller y = higher price
    swing_low = max(c.wick_bottom for c in recent)    # larger y = lower price
    price_range = swing_low - swing_high
    if price_range <= 0:
        return 0.0

    last = recent[-1]
    last_mid = (last.body_top + last.body_bottom) / 2
    # position: 0.0 = at swing high (resistance), 1.0 = at swing low (support)
    position = (last_mid - swing_high) / price_range
    position = max(0.0, min(1.0, position))

    # Graded Fibonacci zones: deepest pullback zones get the strongest nudge.
    if position <= 0.10:
        return -0.20    # at/above resistance -> strong bearish nudge
    elif position <= 0.236:
        return -0.12     # shallow pullback zone (23.6%)
    elif position <= 0.382:
        return -0.06     # 38.2% zone
    elif position < 0.618:
        return 0.0        # 50% zone -> no edge either way
    elif position < 0.764:
        return 0.06       # 61.8% zone
    elif position < 0.90:
        return 0.12       # 78.6% zone
    return 0.20            # at/below support -> strong bullish nudge


def compute_streak_bonus(candles, lookback=6):
    """
    Detects consecutive same-direction candle streaks at the tail of the
    series (momentum persistence). A run of 3+ same-colored candles in a
    row has historically shown a mild continuation bias in short-timeframe
    binary/forex charts — this adds a small, capped nudge on top of the
    broader trend_bias so genuine momentum runs get slightly more credit
    without overwhelming the pattern-based signal.
    Returns a value between -0.12 and +0.12.
    """
    recent = _last(candles, lookback)
    if len(recent) < 3:
        return 0.0

    streak = 1
    last_dir = recent[-1].is_bullish()
    for c in reversed(recent[:-1]):
        if c.is_bullish() == last_dir:
            streak += 1
        else:
            break

    if streak < 3:
        return 0.0

    capped_streak = min(streak, 6)
    magnitude = 0.03 * (capped_streak - 2)  # 3->0.03, 4->0.06, 5->0.09, 6->0.12
    return magnitude if last_dir else -magnitude


def _determine_entry_timing(confidence, choppiness, strength, tech):
    """
    Determines the recommended entry timing based on signal quality.
    Returns "ENTER NOW", "WAIT FOR CONFIRMATION", or "SKIP - LOW QUALITY".
    """
    # Skip conditions: very choppy market or very weak signal
    if choppiness > 0.65 or confidence < 58:
        return "SKIP - LOW QUALITY"

    # High-quality entry conditions
    if confidence >= 78 and choppiness < 0.35 and strength in ("VERY STRONG", "STRONG"):
        # Additional check: do volume and MACD agree?
        vol_bias = tech.get("volume_bias", "neutral")
        macd_bias = tech.get("macd_bias", "neutral")
        if vol_bias != "neutral" or macd_bias != "neutral":
            return "ENTER NOW"

    # Default: wait for one more confirming candle
    return "WAIT FOR CONFIRMATION"


def _determine_risk_level(confidence, choppiness, tech, patterns):
    """
    Calculates trade risk level based on signal quality and market conditions.
    Returns "🟢 LOW RISK", "🟡 MEDIUM RISK", or "🔴 HIGH RISK".
    """
    risk_score = 0

    # Higher confidence = lower risk
    if confidence >= 80:
        risk_score += 0
    elif confidence >= 68:
        risk_score += 1
    else:
        risk_score += 2

    # Choppiness increases risk
    if choppiness > 0.55:
        risk_score += 2
    elif choppiness > 0.35:
        risk_score += 1

    # ATR volatility
    atr_vol = tech.get("atr_volatility", "medium")
    if atr_vol == "high":
        risk_score += 1

    # Bollinger position: outside bands = higher risk (possible snap-back)
    bb_pos = tech.get("bollinger_position", "middle")
    if bb_pos in ("outside_upper", "outside_lower"):
        risk_score += 1

    # Pattern count: single pattern = higher risk than multi-pattern
    if len(patterns) <= 1:
        risk_score += 1

    if risk_score <= 1:
        return "🟢 LOW RISK"
    elif risk_score <= 3:
        return "🟡 MEDIUM RISK"
    else:
        return "🔴 HIGH RISK"


def predict_next_candle(candles, rsi_signal=None, sensitivity=1.0):

    """
    PRO v2: Combines pattern signals + trend momentum + market context +
    technical indicators (MACD, Bollinger, Volume, ATR, Trend Strength)
    into a final prediction with entry timing and risk level assessment.

    New in v2:
      - 6 technical signals instead of 3 (adds MACD, Bollinger, Volume bias)
      - Trend strength bonus for very strong directional momentum
      - Volume surge confirmation bonus
      - Wider confidence range: 50-98% (was 54-96%)
      - Entry timing: ENTER NOW / WAIT FOR CONFIRMATION / SKIP
      - Risk level: 🟢 LOW RISK / 🟡 MEDIUM RISK / 🔴 HIGH RISK
    """
    patterns = detect_patterns(candles)
    trend_bias = compute_trend_bias(candles)
    choppiness = compute_market_choppiness(candles)
    sr_nudge = compute_support_resistance_context(candles)
    streak_bonus = compute_streak_bonus(candles)
    tech = get_technical_confluence(candles)

    pattern_score = 0.0
    pattern_weight_sum = 0.0
    bullish_count = 0
    bearish_count = 0
    breakdown = []

    for p in patterns:
        weight = p["weight"]
        if p["signal"] == "bullish":
            pattern_score += weight
            bullish_count += 1
        elif p["signal"] == "bearish":
            pattern_score -= weight
            bearish_count += 1
        pattern_weight_sum += weight
        breakdown.append({
            "name": p["name"],
            "signal": p["signal"],
            "reliability": round(weight * 100, 0),
        })

    if pattern_weight_sum > 0:
        pattern_score /= pattern_weight_sum

    directional_patterns = bullish_count + bearish_count
    if directional_patterns >= 2:
        agreement_ratio = max(bullish_count, bearish_count) / directional_patterns
        confluence_factor = 0.85 + (agreement_ratio - 0.5) * 0.5
    else:
        confluence_factor = 0.9

    final_score = (pattern_score * 0.58 + trend_bias * 0.28 + sr_nudge + streak_bonus) * confluence_factor
    choppiness_damping = 1.0 - (choppiness * 0.35)
    final_score *= choppiness_damping
    final_score *= max(0.7, min(1.3, sensitivity))

    rsi_agrees = None
    if rsi_signal and rsi_signal.get("detected") and rsi_signal.get("bias") in ("bullish", "bearish"):
        pattern_direction = "bullish" if final_score >= 0 else "bearish"
        if rsi_signal["bias"] == pattern_direction:
            final_score *= 1.12
            rsi_agrees = True
        else:
            final_score *= 0.88
            rsi_agrees = False

    final_score = max(-1.0, min(1.0, final_score))

    # ---- Technical indicator confluence v2: now includes MACD, Bollinger,
    # Volume bias in addition to the original MA/ZigZag/RSI signals. ----
    tech_agree_count = 0
    tech_disagree_count = 0
    pattern_direction = "bullish" if final_score >= 0 else "bearish"

    # v4: check 8 signals instead of 7
    tech_signals = [
        tech.get("ma_trend"),
        tech.get("zigzag_structure_bias"),
        tech.get("rsi_bias"),
        tech.get("macd_bias"),          # v2
        tech.get("bollinger_bias"),     # v2
        tech.get("volume_bias"),        # v2
        tech.get("stochastic_bias"),    # v3 — position-in-range confirmation
        tech.get("chart_pattern_bias"), # v4 — Double Top/Bottom structure
    ]
    for tech_signal in tech_signals:
        if tech_signal == pattern_direction:
            tech_agree_count += 1
        elif tech_signal in ("bullish", "bearish"):
            tech_disagree_count += 1

    if tech_agree_count or tech_disagree_count:
        net_tech = tech_agree_count - tech_disagree_count
        # Each net agreeing indicator nudges score ~3.5%, capped at ±18%
        tech_factor = 1.0 + max(-0.18, min(0.18, net_tech * 0.035))
        final_score *= tech_factor

    # Trend strength bonus: strong directional trend boosts score slightly
    trend_str = tech.get("trend_strength", 0)
    trend_dir = tech.get("trend_direction", "neutral")
    if trend_str > 0.70 and trend_dir == pattern_direction:
        final_score *= 1.06  # modest boost for very strong trend alignment

    # Volume surge on the signal candle: strong momentum confirmation
    if tech.get("volume_surge") and pattern_direction == trend_dir:
        final_score *= 1.04

    final_score = max(-1.0, min(1.0, final_score))

    direction = "UP" if final_score >= 0 else "DOWN"

    # Wider confidence range: 50-98% (was 54-96%)
    # Formula: 50 + |score| * 48 → gives full 50-98 range
    confidence = min(98, max(50, 50 + abs(final_score) * 48))

    if confidence >= 82:
        strength = "VERY STRONG"
    elif confidence >= 70:
        strength = "STRONG"
    elif confidence >= 60:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    # Entry timing and risk level (new v2)
    entry_timing = _determine_entry_timing(confidence, choppiness, strength, tech)
    risk_level = _determine_risk_level(confidence, choppiness, tech, patterns)

    return {
        "direction": direction,
        "confidence": round(confidence, 1),
        "strength": strength,
        "entry_timing": entry_timing,
        "risk_level": risk_level,
        "patterns": patterns,
        "breakdown": breakdown,
        "trend_bias": round(trend_bias, 3),
        "final_score": round(final_score, 3),
        "choppiness": round(choppiness, 2),
        "confluence": round(confluence_factor, 2),
        "streak_bonus": round(streak_bonus, 3),
        "sensitivity": round(sensitivity, 2),
        "rsi_signal": rsi_signal if rsi_signal and rsi_signal.get("detected") else None,
        "rsi_agrees": rsi_agrees,
        "technical_indicators": tech,
    }
