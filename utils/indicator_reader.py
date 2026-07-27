"""
MI NEXUS - Indicator Reader
Detects an on-chart RSI panel (common in Quotex/broker screenshots showing
an RSI sub-indicator strip) using pure computer vision — no AI/API.

How it works: RSI panels are typically a horizontal strip at the bottom of
the chart with a colored line oscillating between labeled levels (e.g. 30
and 70). We locate that strip, trace the line's vertical position, and map
it to an approximate RSI value using the panel's height as the 0-100 scale.
This is a heuristic approximation, not exact indicator math — it's meant to
add supporting context, not replace true RSI calculation from price data.
"""

import cv2
import numpy as np


def _find_rsi_panel(img):
    """
    Heuristic: RSI panels are usually a distinct horizontal band in the
    bottom ~25% of the chart, often with a subtle border separating it
    from the main candle area. We approximate its bounds rather than
    doing OCR-based label detection, which is unreliable at small sizes.
    """
    h, w = img.shape[:2]
    panel_top = int(h * 0.78)
    panel_bottom = int(h * 0.98)
    panel_left = int(w * 0.03)
    panel_right = int(w * 0.85)
    return img[panel_top:panel_bottom, panel_left:panel_right], (panel_top, panel_bottom)


def detect_rsi_signal(image_path):
    """
    Attempts to detect an RSI-like oscillator line in the lower chart region
    and classify it as overbought / oversold / neutral based on its recent
    vertical position within the panel.

    Returns dict: {"detected": bool, "zone": str, "bias": str} or
    {"detected": False} if no clear RSI-like panel/line was found.
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"detected": False}

    panel, (panel_top, panel_bottom) = _find_rsi_panel(img)
    if panel.size == 0:
        return {"detected": False}

    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)

    # RSI lines are commonly rendered in green/teal or a distinct accent color,
    # thin (1-3px), spanning most of the panel width horizontally.
    green_mask = cv2.inRange(hsv, np.array([35, 40, 60]), np.array([95, 255, 255]))

    ph, pw = green_mask.shape
    col_positions = []
    for x in range(0, pw, max(1, pw // 60)):  # sample ~60 columns across the panel
        col = green_mask[:, x]
        ys = np.nonzero(col)[0]
        if len(ys) > 0:
            col_positions.append(int(ys.mean()))

    if len(col_positions) < 8:
        return {"detected": False}  # not enough signal to trust this as an RSI line

    # Use the most recent ~20% of sampled columns (rightmost = most recent time)
    recent_count = max(3, len(col_positions) // 5)
    recent_positions = col_positions[-recent_count:]
    avg_y = sum(recent_positions) / len(recent_positions)

    # Map vertical position to an approximate 0-100 scale (top of panel = 100, bottom = 0)
    relative_pos = 1.0 - (avg_y / ph)  # 0 = bottom, 1 = top
    approx_rsi = round(relative_pos * 100, 1)

    if approx_rsi >= 70:
        zone, bias = "Overbought", "bearish"
    elif approx_rsi <= 30:
        zone, bias = "Oversold", "bullish"
    else:
        zone, bias = "Neutral", "neutral"

    return {
        "detected": True,
        "approx_value": approx_rsi,
        "zone": zone,
        "bias": bias,
    }
