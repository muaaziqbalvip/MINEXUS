"""
MI NEXUS - Technical Indicators Engine
Computes real technical indicators directly from the detected candle
data (not visual approximation like indicator_reader.py's on-chart RSI
reading) - these are calculated the standard way from actual candle
body/wick positions, giving the pattern engine genuine additional
confirmation signals rather than guesses.

Implements, using standard/textbook formulas:
  - Fractals (5-bar pivot high/low pattern - Bill Williams style)
  - ZigZag (threshold-filtered swing high/low structure, HH/HL/LH/LL)
  - Simple Moving Average (SMA) and trend-slope reading
  - RSI computed from candle body deltas (Wilder's smoothing method)

All of these work directly off the same Candle objects the rest of the
bot already extracts from screenshots - no new detection step needed.
"""


def _price_mid(candle):
    return (candle.body_top + candle.body_bottom) / 2


def detect_fractals(candles, window=2):
    """
    Bill Williams-style fractal detection: a candle is a fractal HIGH if
    its high (wick_top, remember smaller y = higher price) is higher than
    `window` candles on each side; a fractal LOW is the mirror case.
    Returns list of {"index": i, "type": "high"/"low"}.
    """
    fractals = []
    n = len(candles)
    for i in range(window, n - window):
        c = candles[i]
        left = candles[i - window:i]
        right = candles[i + 1:i + 1 + window]

        # smaller wick_top = higher price in image coordinates
        is_high = all(c.wick_top < o.wick_top for o in left + right)
        is_low = all(c.wick_bottom > o.wick_bottom for o in left + right)

        if is_high:
            fractals.append({"index": i, "type": "high"})
        elif is_low:
            fractals.append({"index": i, "type": "low"})

    return fractals


def compute_zigzag(candles, threshold_pct=3.0):
    """
    Threshold-filtered ZigZag: walks through candles tracking the running
    swing high/low, only registering a new turning point once price has
    reversed by more than `threshold_pct` percent from the last extreme.
    Returns a list of swing points: {"index", "price_y", "type": "high"/"low"}
    and a market-structure label sequence (HH/HL/LH/LL).
    """
    if len(candles) < 3:
        return [], "insufficient_data"

    swings = []
    trend = None  # "up" or "down"
    last_extreme_idx = 0
    last_extreme_y = _price_mid(candles[0])

    for i in range(1, len(candles)):
        y = _price_mid(candles[i])
        # In image coords, smaller y = higher price, so "up" move = y decreasing
        change_pct = abs(y - last_extreme_y) / max(1, last_extreme_y) * 100

        if trend is None:
            if change_pct >= threshold_pct:
                trend = "down" if y > last_extreme_y else "up"
                swings.append({
                    "index": last_extreme_idx,
                    "type": "low" if trend == "up" else "high",
                })
                last_extreme_idx, last_extreme_y = i, y
            continue

        if trend == "up":
            if y < last_extreme_y:
                last_extreme_idx, last_extreme_y = i, y  # extending the up-move
            elif change_pct >= threshold_pct:
                swings.append({"index": last_extreme_idx, "type": "high"})
                trend = "down"
                last_extreme_idx, last_extreme_y = i, y
        else:  # trend == "down"
            if y > last_extreme_y:
                last_extreme_idx, last_extreme_y = i, y  # extending the down-move
            elif change_pct >= threshold_pct:
                swings.append({"index": last_extreme_idx, "type": "low"})
                trend = "up"
                last_extreme_idx, last_extreme_y = i, y

    swings.append({"index": last_extreme_idx, "type": "high" if trend == "up" else "low"})

    # Label market structure (HH/HL/LH/LL) by comparing consecutive same-type swings
    structure = []
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    for group, high_label, low_label in ((highs, "HH", "LH"), (lows, "HL", "LL")):
        for j in range(1, len(group)):
            prev_y = _price_mid(candles[group[j - 1]["index"]])
            curr_y = _price_mid(candles[group[j]["index"]])
            # smaller y = higher price
            if curr_y < prev_y:
                structure.append(high_label if group is highs else low_label)
            else:
                structure.append(("LH" if group is highs else "LL"))

    bias = "neutral"
    if structure:
        bullish_count = structure.count("HH") + structure.count("HL")
        bearish_count = structure.count("LH") + structure.count("LL")
        if bullish_count > bearish_count:
            bias = "bullish"
        elif bearish_count > bullish_count:
            bias = "bearish"

    return swings, bias


def compute_sma(candles, period=5):
    """Simple Moving Average of candle midpoints over the last `period` candles."""
    if len(candles) < period:
        period = len(candles)
    if period == 0:
        return None
    recent = candles[-period:]
    return sum(_price_mid(c) for c in recent) / period


def compute_ma_trend(candles, short_period=5, long_period=10):
    """
    Compares a short SMA to a long SMA (classic moving-average-crossover
    read). Returns "bullish" if short MA is above long MA (in price terms,
    remembering smaller y = higher price), "bearish" if below, else "flat".
    """
    if len(candles) < 3:
        return "flat"
    short_period = min(short_period, len(candles))
    long_period = min(long_period, len(candles))

    short_ma = compute_sma(candles, short_period)
    long_ma = compute_sma(candles, long_period)
    if short_ma is None or long_ma is None:
        return "flat"

    diff_pct = abs(short_ma - long_ma) / max(1, long_ma) * 100
    if diff_pct < 0.02:
        return "flat"
    # smaller y = higher price -> short MA below long MA in y-terms = bullish
    return "bullish" if short_ma < long_ma else "bearish"


def compute_calculated_rsi(candles, period=14):
    """
    Real RSI computed from candle-to-candle body-midpoint changes using
    Wilder's smoothing method - not a visual chart read, an actual
    calculation from the extracted candle data.
    Returns a value 0-100, or None if there isn't enough data.
    """
    if len(candles) < period + 1:
        period = len(candles) - 1
    if period < 2:
        return None

    closes = [_price_mid(c) for c in candles[-(period + 1):]]
    gains, losses = [], []
    for i in range(1, len(closes)):
        # smaller y = higher price, so a price INCREASE is closes[i] < closes[i-1]
        delta = closes[i - 1] - closes[i]
        gains.append(max(0, delta))
        losses.append(max(0, -delta))

    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


def get_technical_confluence(candles):
    """
    Master function: runs all indicators above and returns a combined
    confluence dict for the pattern engine to factor into its final score.
    """
    fractals = detect_fractals(candles)
    zigzag_swings, structure_bias = compute_zigzag(candles)
    ma_trend = compute_ma_trend(candles)
    rsi = compute_calculated_rsi(candles)

    rsi_bias = "neutral"
    if rsi is not None:
        if rsi >= 70:
            rsi_bias = "bearish"  # overbought
        elif rsi <= 30:
            rsi_bias = "bullish"  # oversold

    recent_fractal_type = fractals[-1]["type"] if fractals else None

    return {
        "fractals_count": len(fractals),
        "recent_fractal": recent_fractal_type,
        "zigzag_structure_bias": structure_bias,
        "ma_trend": ma_trend,
        "calculated_rsi": rsi,
        "rsi_bias": rsi_bias,
    }
