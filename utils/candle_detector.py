"""
MI NEXUS - Candle Detection Engine
Detects candlesticks from a chart screenshot using pure OpenCV (no AI/API).
Works by color-segmenting green/red (bullish/bearish) candle bodies and wicks.
"""

import cv2
import numpy as np


class Candle:
    def __init__(self, x, body_top, body_bottom, wick_top, wick_bottom, color, width):
        self.x = x
        self.body_top = body_top
        self.body_bottom = body_bottom
        self.wick_top = wick_top
        self.wick_bottom = wick_bottom
        self.color = color  # "green" (bullish) or "red" (bearish)
        self.width = width

        self.body_height = abs(body_bottom - body_top)
        self.upper_wick = abs(body_top - wick_top)
        self.lower_wick = abs(wick_bottom - body_bottom)
        self.total_range = abs(wick_bottom - wick_top) if wick_bottom != wick_top else 1

    def body_ratio(self):
        return self.body_height / self.total_range if self.total_range else 0

    def upper_wick_ratio(self):
        return self.upper_wick / self.total_range if self.total_range else 0

    def lower_wick_ratio(self):
        return self.lower_wick / self.total_range if self.total_range else 0

    def is_bullish(self):
        return self.color == "green"

    def is_bearish(self):
        return self.color == "red"


# ----------------------------------------------------------------------
# COLOR RANGES - tuned for common broker platforms (Quotex/IQ-style themes)
# Covers both bright-green/red and teal/crimson variants.
# ----------------------------------------------------------------------
GREEN_RANGES = [
    ((35, 40, 40), (85, 255, 255)),   # standard green
    ((70, 30, 40), (95, 255, 255)),   # teal-green (Quotex default up-candle)
]
RED_RANGES = [
    ((0, 40, 40), (10, 255, 255)),    # red low hue
    ((160, 40, 40), (179, 255, 255)), # red high hue
    ((340 // 2, 40, 40), (360 // 2, 255, 255)),  # crimson
]


def _mask_for_ranges(hsv, ranges):
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return mask


def crop_chart_area(img):
    """
    Attempts to isolate the actual chart/candle area, cropping away
    side panels, top bars, and bottom toolbars common in broker UIs.
    Falls back to full image if detection is inconclusive.
    """
    h, w = img.shape[:2]
    # Heuristic crop: trading platforms usually keep candles in the
    # central 80% width and 75% height band.
    top = int(h * 0.05)
    bottom = int(h * 0.90)
    left = int(w * 0.02)
    right = int(w * 0.92)  # avoid right-side price axis
    return img[top:bottom, left:right], (left, top)


def detect_candles(image_path):
    """
    Main entry point. Returns (candles_list, debug_image, offset)
    candles_list is sorted left-to-right (chronological order).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image file")

    cropped, offset = crop_chart_area(img)
    hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)

    green_mask = _mask_for_ranges(hsv, GREEN_RANGES)
    red_mask = _mask_for_ranges(hsv, RED_RANGES)

    # Clean noise
    kernel = np.ones((3, 3), np.uint8)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    candles = []
    for color_name, mask in (("green", green_mask), ("red", red_mask)):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w < 2 or h < 4:
                continue  # noise
            candles.append({
                "x": x, "y": y, "w": w, "h": h, "color": color_name
            })

    if not candles:
        return [], cropped, offset

    # Group by x-position into candle columns (body + wick share x-center)
    candles.sort(key=lambda c: c["x"])
    grouped = _group_by_column(candles)

    candle_objs = []
    for group in grouped:
        candle = _build_candle_from_group(group)
        if candle:
            candle_objs.append(candle)

    candle_objs.sort(key=lambda c: c.x)
    return candle_objs, cropped, offset


def _group_by_column(candles, x_tolerance=6):
    """Groups wick + body rectangles that belong to the same candle column."""
    groups = []
    used = [False] * len(candles)
    candles_sorted = sorted(range(len(candles)), key=lambda i: candles[i]["x"])

    for i in candles_sorted:
        if used[i]:
            continue
        base = candles[i]
        group = [base]
        used[i] = True
        center_x = base["x"] + base["w"] / 2

        for j in candles_sorted:
            if used[j]:
                continue
            other = candles[j]
            other_center = other["x"] + other["w"] / 2
            if abs(other_center - center_x) <= x_tolerance:
                group.append(other)
                used[j] = True
        groups.append(group)

    return groups


def _build_candle_from_group(group):
    """Combines body+wick rects in a column into one Candle object."""
    if not group:
        return None

    # widest rect = body, narrower = wick
    group_sorted = sorted(group, key=lambda c: c["w"], reverse=True)
    body_rect = group_sorted[0]
    color = body_rect["color"]

    all_tops = [c["y"] for c in group]
    all_bottoms = [c["y"] + c["h"] for c in group]

    wick_top = min(all_tops)
    wick_bottom = max(all_bottoms)
    body_top = body_rect["y"]
    body_bottom = body_rect["y"] + body_rect["h"]

    center_x = body_rect["x"] + body_rect["w"] / 2

    return Candle(
        x=center_x,
        body_top=body_top,
        body_bottom=body_bottom,
        wick_top=wick_top,
        wick_bottom=wick_bottom,
        color=color,
        width=body_rect["w"],
    )
