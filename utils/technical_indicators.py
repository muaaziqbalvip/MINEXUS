"""
MI NEXUS PRO - Technical Indicators Engine v2

Computes real technical indicators from detected candle data.
All calculations use standard/textbook formulas applied directly
to the Candle objects extracted from screenshots.

v2 Additions:
  - MACD approximation (12/26/9 EMA crossover from candle midpoints)
  - Bollinger Band position (is price near upper/lower band?)
  - ATR (Average True Range) for volatility assessment
  - Volume proxy from candle body sizes (larger body ≈ more volume)
  - Enhanced confluence scorer with 6 signals instead of 4
  - Trend momentum strength (how strong is the current trend impulse?)
"""


def _price_mid(candle):
    """Candle midpoint (close price proxy in image coordinates)."""
    return (candle.body_top + candle.body_bottom) / 2


def _price_high(candle):
    """Candle high (wick top = smallest y = highest price)."""
    return candle.wick_top


def _price_low(candle):
    """Candle low (wick bottom = largest y = lowest price)."""
    return candle.wick_bottom


# ─────────────────────────────────────────────────────────────────────────────
# EXISTING INDICATORS (v1 — preserved)
# ─────────────────────────────────────────────────────────────────────────────

def detect_fractals(candles, window=2):
    """
    Bill Williams-style fractal detection: a candle is a fractal HIGH if
    its high (wick_top, smaller y = higher price) is higher than `window`
    candles on each side; fractal LOW is the mirror case.
    Returns list of {"index": i, "type": "high"/"low"}.
    """
    fractals = []
    n = len(candles)
    for i in range(window, n - window):
        c = candles[i]
        left = candles[i - window:i]
        right = candles[i + 1:i + 1 + window]

        is_high = all(c.wick_top < o.wick_top for o in left + right)
        is_low = all(c.wick_bottom > o.wick_bottom for o in left + right)

        if is_high:
            fractals.append({"index": i, "type": "high"})
        elif is_low:
            fractals.append({"index": i, "type": "low"})

    return fractals


def compute_zigzag(candles, threshold_pct=3.0):
    """
    Threshold-filtered ZigZag: tracks swing high/low structure.
    Returns swing points and market-structure label (HH/HL/LH/LL).
    """
    if len(candles) < 3:
        return [], "insufficient_data"

    swings = []
    trend = None
    last_extreme_idx = 0
    last_extreme_y = _price_mid(candles[0])

    for i in range(1, len(candles)):
        y = _price_mid(candles[i])
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
                last_extreme_idx, last_extreme_y = i, y
            elif change_pct >= threshold_pct:
                swings.append({"index": last_extreme_idx, "type": "high"})
                trend = "down"
                last_extreme_idx, last_extreme_y = i, y
        else:
            if y > last_extreme_y:
                last_extreme_idx, last_extreme_y = i, y
            elif change_pct >= threshold_pct:
                swings.append({"index": last_extreme_idx, "type": "low"})
                trend = "up"
                last_extreme_idx, last_extreme_y = i, y

    swings.append({"index": last_extreme_idx, "type": "high" if trend == "up" else "low"})

    structure = []
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    for group, high_label, low_label in ((highs, "HH", "LH"), (lows, "HL", "LL")):
        for j in range(1, len(group)):
            prev_y = _price_mid(candles[group[j - 1]["index"]])
            curr_y = _price_mid(candles[group[j]["index"]])
            if curr_y < prev_y:
                structure.append(high_label if group is highs else low_label)
            else:
                structure.append("LH" if group is highs else "LL")

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
    """Simple Moving Average of candle midpoints."""
    if len(candles) < period:
        period = len(candles)
    if period == 0:
        return None
    recent = candles[-period:]
    return sum(_price_mid(c) for c in recent) / period


def compute_ema(candles, period=12):
    """
    Exponential Moving Average of candle midpoints.
    Uses standard EMA formula: EMA = price * k + prev_EMA * (1 - k)
    where k = 2 / (period + 1).
    """
    if not candles or period <= 0:
        return None

    prices = [_price_mid(c) for c in candles]
    if len(prices) < period:
        # Not enough data — use SMA as seed
        return sum(prices) / len(prices)

    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period  # seed with SMA of first `period` bars

    for price in prices[period:]:
        ema = price * k + ema * (1 - k)

    return ema


def compute_ma_trend(candles, short_period=5, long_period=10):
    """
    Compares short SMA vs long SMA for trend direction.
    Returns "bullish", "bearish", or "flat".
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
    # smaller y = higher price → short MA below long MA in y-terms = bullish
    return "bullish" if short_ma < long_ma else "bearish"


def compute_calculated_rsi(candles, period=14):
    """
    Real RSI from candle-to-candle midpoint changes using Wilder's smoothing.
    Returns value 0-100, or None if insufficient data.
    """
    if len(candles) < period + 1:
        period = len(candles) - 1
    if period < 2:
        return None

    closes = [_price_mid(c) for c in candles[-(period + 1):]]
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i - 1] - closes[i]  # smaller y = higher price
        gains.append(max(0, delta))
        losses.append(max(0, -delta))

    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


# ─────────────────────────────────────────────────────────────────────────────
# NEW v2 INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def compute_macd(candles, fast=12, slow=26, signal=9):
    """
    MACD approximation from candle midpoints.
    Returns dict with:
      - macd_line: fast EMA - slow EMA (in image y-coords, so sign is inverted)
      - signal_line: EMA of macd_line
      - histogram: macd_line - signal_line
      - bias: "bullish" (MACD above signal) / "bearish" (below) / "neutral"

    Note: image y-coords are inverted (smaller y = higher price), so a
    "bullish" MACD means macd_line < signal_line in raw y-values.
    We handle this by inverting the final comparison.
    """
    if len(candles) < slow + signal:
        return {"bias": "neutral", "histogram": 0, "macd_line": None, "signal_line": None}

    fast_ema = compute_ema(candles, fast)
    slow_ema = compute_ema(candles, slow)

    if fast_ema is None or slow_ema is None:
        return {"bias": "neutral", "histogram": 0, "macd_line": None, "signal_line": None}

    # In price terms (not y-coords): macd = fast - slow
    # Since y is inverted, fast_ema < slow_ema means fast > slow in price → bullish
    macd_line_y = fast_ema - slow_ema  # y-coordinate difference

    # Compute signal line: we need a history of MACD values
    # Approximation: use a rolling MACD across the last (signal) windows
    macd_history = []
    step = max(1, len(candles) // (signal + 2))
    for i in range(signal + 1):
        idx = max(1, len(candles) - (signal - i) * step)
        sub = candles[:idx]
        if len(sub) >= slow:
            fe = compute_ema(sub, fast)
            se = compute_ema(sub, slow)
            if fe is not None and se is not None:
                macd_history.append(fe - se)

    if not macd_history:
        signal_line_y = macd_line_y
    else:
        signal_line_y = sum(macd_history) / len(macd_history)

    histogram = macd_line_y - signal_line_y

    # In y-coord space: macd < signal means price-MACD > price-signal = bullish
    if abs(histogram) < 0.001:
        bias = "neutral"
    elif macd_line_y < signal_line_y:
        bias = "bullish"
    else:
        bias = "bearish"

    return {
        "macd_line": round(macd_line_y, 4),
        "signal_line": round(signal_line_y, 4),
        "histogram": round(histogram, 4),
        "bias": bias,
    }


def compute_bollinger_position(candles, period=20, num_std=2.0):
    """
    Bollinger Band position: where is the current price relative to the bands?
    Returns:
      - "near_upper": price near upper band (overbought zone → bearish caution)
      - "near_lower": price near lower band (oversold zone → bullish caution)
      - "middle": price near the mid-band (neutral)
      - "outside_upper": price above upper band (strong breakout bullish)
      - "outside_lower": price below lower band (strong breakout bearish)
      - bias: "bullish" / "bearish" / "neutral"
    """
    n = min(period, len(candles))
    if n < 5:
        return {"position": "unknown", "bias": "neutral", "bandwidth": 0}

    prices = [_price_mid(c) for c in candles[-n:]]
    sma = sum(prices) / len(prices)
    variance = sum((p - sma) ** 2 for p in prices) / len(prices)
    std = variance ** 0.5

    if std < 0.001:
        return {"position": "middle", "bias": "neutral", "bandwidth": 0}

    current = prices[-1]
    upper_band = sma - num_std * std   # y-coord: upper in price = lower y
    lower_band = sma + num_std * std   # y-coord: lower in price = higher y
    bandwidth = abs(upper_band - lower_band) / max(1, sma) * 100

    # Position in normalized terms (0 = at lower price band, 1 = at upper price band)
    band_range = lower_band - upper_band  # positive (lower_band > upper_band in y)
    if band_range <= 0:
        return {"position": "middle", "bias": "neutral", "bandwidth": round(bandwidth, 2)}

    position_ratio = (lower_band - current) / band_range  # 0=bottom, 1=top

    if current < upper_band:
        position = "outside_upper"
        bias = "bullish"  # price above upper band in price space
    elif current > lower_band:
        position = "outside_lower"
        bias = "bearish"
    elif position_ratio > 0.80:
        position = "near_upper"
        bias = "bearish"  # overbought
    elif position_ratio < 0.20:
        position = "near_lower"
        bias = "bullish"  # oversold
    else:
        position = "middle"
        bias = "neutral"

    return {
        "position": position,
        "bias": bias,
        "bandwidth": round(bandwidth, 2),
        "position_ratio": round(position_ratio, 2),
    }


def compute_atr(candles, period=14):
    """
    Average True Range: measures market volatility.
    Higher ATR = more volatile (wider candles, bigger moves).
    Returns ATR as a percentage of the average price range.
    """
    if len(candles) < 2:
        return {"atr": 0, "volatility": "low"}

    n = min(period, len(candles))
    true_ranges = []

    for i in range(1, n):
        c = candles[-(n - i + 1)]
        prev = candles[-(n - i)]

        # True range components (in image y-coords)
        high_low = abs(c.wick_top - c.wick_bottom)   # current range
        high_close = abs(c.wick_top - _price_mid(prev))   # gap from prev close
        low_close = abs(c.wick_bottom - _price_mid(prev))  # gap from prev close

        tr = max(high_low, high_close, low_close)
        true_ranges.append(tr)

    if not true_ranges:
        return {"atr": 0, "volatility": "low"}

    atr = sum(true_ranges) / len(true_ranges)

    # Normalize: ATR as % of typical price level
    avg_price = sum(_price_mid(c) for c in candles[-n:]) / n
    atr_pct = (atr / max(1, avg_price)) * 100

    # Classify volatility
    if atr_pct > 2.0:
        volatility = "high"
    elif atr_pct > 0.8:
        volatility = "medium"
    else:
        volatility = "low"

    return {
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 3),
        "volatility": volatility,
    }


def compute_volume_proxy(candles, period=8):
    """
    Approximates volume from candle body sizes.
    Assumption: larger candle body ≈ more participation/volume.
    Returns:
      - trend: "increasing" / "decreasing" / "stable" (volume trend)
      - bias: "bullish" (bull candles have bigger bodies) / "bearish" / "neutral"
      - recent_surge: True if last candle is notably larger than average
    """
    if len(candles) < 4:
        return {"trend": "stable", "bias": "neutral", "recent_surge": False}

    recent = candles[-period:]
    body_sizes = [c.body_height for c in recent]

    avg_body = sum(body_sizes) / len(body_sizes)
    last_body = body_sizes[-1]

    # Volume trend: compare first half to second half average
    mid = len(body_sizes) // 2
    first_avg = sum(body_sizes[:mid]) / max(1, mid)
    second_avg = sum(body_sizes[mid:]) / max(1, len(body_sizes) - mid)

    if second_avg > first_avg * 1.20:
        vol_trend = "increasing"
    elif second_avg < first_avg * 0.80:
        vol_trend = "decreasing"
    else:
        vol_trend = "stable"

    # Volume bias: do bull or bear candles have bigger bodies?
    bull_bodies = [c.body_height for c in recent if c.is_bullish()]
    bear_bodies = [c.body_height for c in recent if c.is_bearish()]

    if bull_bodies and bear_bodies:
        avg_bull = sum(bull_bodies) / len(bull_bodies)
        avg_bear = sum(bear_bodies) / len(bear_bodies)
        if avg_bull > avg_bear * 1.25:
            vol_bias = "bullish"
        elif avg_bear > avg_bull * 1.25:
            vol_bias = "bearish"
        else:
            vol_bias = "neutral"
    else:
        vol_bias = "neutral"

    recent_surge = last_body > avg_body * 1.5

    return {
        "trend": vol_trend,
        "bias": vol_bias,
        "recent_surge": recent_surge,
        "avg_body": round(avg_body, 1),
    }


def compute_trend_strength(candles, period=8):
    """
    Measures how STRONG the current trend is, not just its direction.
    Based on how consistently candles move in the same direction.
    Returns:
      - strength: 0.0 (no trend) to 1.0 (perfect trend)
      - direction: "bullish" / "bearish" / "neutral"
      - label: "STRONG TREND" / "MODERATE TREND" / "WEAK/SIDEWAYS"
    """
    recent = candles[-period:] if len(candles) >= period else candles
    if len(recent) < 3:
        return {"strength": 0, "direction": "neutral", "label": "INSUFFICIENT DATA"}

    bull = sum(1 for c in recent if c.is_bullish())
    bear = len(recent) - bull

    dominance = max(bull, bear) / len(recent)

    # Weight by body size: larger bodies = stronger conviction
    bull_weight = sum(c.body_height for c in recent if c.is_bullish())
    bear_weight = sum(c.body_height for c in recent if c.is_bearish())
    total_weight = bull_weight + bear_weight

    weight_dominance = max(bull_weight, bear_weight) / max(1, total_weight)

    strength = dominance * 0.5 + weight_dominance * 0.5

    if bull > bear:
        direction = "bullish"
    elif bear > bull:
        direction = "bearish"
    else:
        direction = "neutral"

    if strength > 0.75:
        label = "STRONG TREND"
    elif strength > 0.55:
        label = "MODERATE TREND"
    else:
        label = "WEAK/SIDEWAYS"

    return {
        "strength": round(strength, 2),
        "direction": direction,
        "label": label,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MASTER CONFLUENCE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def get_technical_confluence(candles):
    """
    Master function: runs ALL indicators and returns a comprehensive
    confluence dict for the pattern engine to factor into its final score.

    v2: Adds MACD, Bollinger, ATR, Volume proxy, Trend Strength.
    """
    fractals = detect_fractals(candles)
    zigzag_swings, structure_bias = compute_zigzag(candles)
    ma_trend = compute_ma_trend(candles)
    rsi = compute_calculated_rsi(candles)
    macd = compute_macd(candles)
    bollinger = compute_bollinger_position(candles)
    atr_data = compute_atr(candles)
    volume = compute_volume_proxy(candles)
    trend_strength = compute_trend_strength(candles)

    rsi_bias = "neutral"
    if rsi is not None:
        if rsi >= 70:
            rsi_bias = "bearish"   # overbought
        elif rsi <= 30:
            rsi_bias = "bullish"   # oversold

    recent_fractal_type = fractals[-1]["type"] if fractals else None

    # Enhanced confluence count for display
    signals = [ma_trend, structure_bias, rsi_bias, macd["bias"], bollinger["bias"], volume["bias"]]
    bull_signals = signals.count("bullish")
    bear_signals = signals.count("bearish")

    if bull_signals > bear_signals:
        overall_bias = "bullish"
    elif bear_signals > bull_signals:
        overall_bias = "bearish"
    else:
        overall_bias = "neutral"

    return {
        # Existing v1 keys (preserved for compatibility)
        "fractals_count": len(fractals),
        "recent_fractal": recent_fractal_type,
        "zigzag_structure_bias": structure_bias,
        "ma_trend": ma_trend,
        "calculated_rsi": rsi,
        "rsi_bias": rsi_bias,

        # New v2 keys
        "macd_bias": macd["bias"],
        "macd_histogram": macd.get("histogram"),
        "bollinger_position": bollinger["position"],
        "bollinger_bias": bollinger["bias"],
        "bollinger_bandwidth": bollinger.get("bandwidth"),
        "atr_volatility": atr_data["volatility"],
        "atr_pct": atr_data.get("atr_pct"),
        "volume_trend": volume["trend"],
        "volume_bias": volume["bias"],
        "volume_surge": volume["recent_surge"],
        "trend_strength": trend_strength["strength"],
        "trend_strength_label": trend_strength["label"],
        "trend_direction": trend_strength["direction"],

        # Summary
        "bull_signal_count": bull_signals,
        "bear_signal_count": bear_signals,
        "overall_bias": overall_bias,
    }
