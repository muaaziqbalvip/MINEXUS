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
    Quotex-style layout: top strip has icons/timer, right strip has price
    axis labels, bottom strip may have RSI/indicator panel.
    """
    h, w = img.shape[:2]
    top = int(h * 0.10)      # skip top icon/timer row
    bottom = int(h * 0.85)   # skip bottom indicator panel area
    left = int(w * 0.01)
    right = int(w * 0.88)    # avoid right-side price axis + price badge
    return img[top:bottom, left:right], (left, top)


def _split_merged_blob(mask, x, y, w, h, reference_w):
    """
    A contour wider than expected likely contains multiple touching candles.
    Look at the column-wise pixel count (density profile) within the blob's
    bounding box; local minima (valleys) mark boundaries between candles.
    Falls back to even-width slicing if no clear valleys are found.
    """
    roi = mask[y:y + h, x:x + w]
    col_density = roi.sum(axis=0) / 255  # pixel count per column

    n_slices = max(1, round(w / reference_w))
    if n_slices <= 1 or w < 10:
        return [(x, y, w, h)]

    # Find valley points near expected slice boundaries
    expected_slice_w = w / n_slices
    boundaries = [0]
    search_radius = max(2, int(expected_slice_w * 0.3))

    for i in range(1, n_slices):
        expected_pos = int(i * expected_slice_w)
        lo = max(1, expected_pos - search_radius)
        hi = min(w - 1, expected_pos + search_radius)
        if lo >= hi:
            boundaries.append(expected_pos)
            continue
        window = col_density[lo:hi]
        if len(window) == 0:
            boundaries.append(expected_pos)
            continue
        min_idx = lo + int(window.argmin())
        boundaries.append(min_idx)
    boundaries.append(w)

    boxes = []
    for i in range(len(boundaries) - 1):
        bx0, bx1 = boundaries[i], boundaries[i + 1]
        if bx1 <= bx0:
            continue
        # Recompute tight y-bounds within this slice for a cleaner body/wick fit
        slice_roi = roi[:, bx0:bx1]
        rows_with_pixels = slice_roi.sum(axis=1) > 0
        if rows_with_pixels.any():
            y_indices = rows_with_pixels.nonzero()[0]
            sy = y + int(y_indices.min())
            sh = int(y_indices.max() - y_indices.min()) + 1
        else:
            sy, sh = y, h
        boxes.append((x + bx0, sy, bx1 - bx0, sh))

    return boxes if boxes else [(x, y, w, h)]


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
        raw_rects = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            rect_area = w * h
            if w < 2 or h < 4:
                continue  # noise
            if rect_area == 0:
                continue
            fill_ratio = area / rect_area
            if fill_ratio < 0.55:
                continue
            aspect = w / h
            if 0.75 <= aspect <= 1.35 and w < 40 and h < 40:
                continue
            raw_rects.append((x, y, w, h))

        if not raw_rects:
            continue

        # Estimate a "typical" single-candle body width from narrower rects
        # (wicks are thin; bodies are wider). Use the smallest quartile of
        # widths among wick-like thin shapes as a floor, and median overall.
        widths = sorted(r[2] for r in raw_rects)
        min_w = widths[0]
        median_w = widths[len(widths) // 2]
        reference_w = min_w if min_w >= 6 else median_w

        for (x, y, w, h) in raw_rects:
            if reference_w > 0 and w > reference_w * 1.6:
                sub_boxes = _split_merged_blob(mask, x, y, w, h, reference_w)
                for (sx, sy, sw, sh) in sub_boxes:
                    candles.append({"x": sx, "y": sy, "w": sw, "h": sh, "color": color_name})
            else:
                candles.append({"x": x, "y": y, "w": w, "h": h, "color": color_name})

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

    # Remove outlier columns whose width is wildly different from the
    # median candle width (helps drop stray UI line/marker fragments)
    if len(candle_objs) >= 4:
        widths = sorted(c.width for c in candle_objs)
        median_w = widths[len(widths) // 2]
        candle_objs = [
            c for c in candle_objs
            if median_w * 0.35 <= c.width <= median_w * 3.0
        ]

    return candle_objs, cropped, offset


def _group_by_column(candles, x_tolerance=4):
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

    # Separate body (wider rects) from wick (narrower rects) using a
    # relative-width threshold rather than always trusting "widest = body",
    # which is more robust when a candle has no visible wick at all.
    widths = [c["w"] for c in group]
    max_w = max(widths)
    body_candidates = [c for c in group if c["w"] >= max_w * 0.6]
    wick_candidates = [c for c in group if c["w"] < max_w * 0.6]

    # Body = the union of all "wide" rects (usually just one)
    body_top = min(c["y"] for c in body_candidates)
    body_bottom = max(c["y"] + c["h"] for c in body_candidates)
    body_rect = max(body_candidates, key=lambda c: c["w"])
    color = body_rect["color"]

    # Wick = extends from body edges to the furthest thin-rect extent;
    # if no thin wick rects were found, wick == body (true Marubozu / no wick)
    if wick_candidates:
        wick_top = min(body_top, min(c["y"] for c in wick_candidates))
        wick_bottom = max(body_bottom, max(c["y"] + c["h"] for c in wick_candidates))
    else:
        wick_top = body_top
        wick_bottom = body_bottom

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
