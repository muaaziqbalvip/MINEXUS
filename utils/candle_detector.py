"""
MI NEXUS - Candle Detection Engine (v2 - column-projection based)
Detects candlesticks from a chart screenshot using pure OpenCV (no AI/API).

This version scans the chart column-by-column (like reading a barcode)
instead of relying on contour-blob shape heuristics. This is far more
robust against:
  - candles whose wicks touch/merge with adjacent candles
  - diagonal UI lines (trade-line overlays) that share the candle color
  - small square candle bodies being mistaken for circular UI icons

For each vertical column, we measure the height of green/red pixel runs.
Real candle columns show a tall, mostly-solid colored run. A thin diagonal
line only lights up 1-3px per column, which naturally falls below the
minimum-height threshold and gets ignored - no fragile shape heuristics
needed.
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
# ----------------------------------------------------------------------
GREEN_RANGES = [
    ((35, 40, 40), (85, 255, 255)),
    ((70, 30, 40), (95, 255, 255)),
]
RED_RANGES = [
    ((0, 40, 40), (10, 255, 255)),
    ((160, 40, 40), (179, 255, 255)),
]


def _mask_for_ranges(hsv, ranges):
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return mask


def crop_chart_area(img):
    """
    Isolates the actual chart/candle area, cropping away side panels, top
    bars, and bottom toolbars common in broker UIs.

    Bug fix: the right-edge cut used to be a hardcoded 88% of image width,
    which assumes every screenshot has a wide price-axis sidebar (true for
    Quotex-style UIs). Charts without one (plain TradingView-style widgets,
    verified on a real screenshot) have real, recent candles sitting past
    that 88% line - those were being silently sliced off, so predictions
    were being made on stale data missing the newest 3-4 candles, which is
    exactly the data next-candle prediction needs most. Now we scan the
    actual candle-colored pixels near the right edge and only fall back to
    the 88% cut if there's no real candle content beyond it - so a genuine
    price-axis sidebar still gets excluded, but real candles never do.
    """
    h, w = img.shape[:2]
    top = int(h * 0.10)
    bottom = int(h * 0.80)   # exclude bottom RSI/indicator strip
    left = int(w * 0.01)
    right = int(w * 0.88)    # default: exclude right-side price axis/badge

    right = max(right, _detect_real_right_edge(img, right, w, top, bottom))

    return img[top:bottom, left:right], (left, top)


def _detect_real_right_edge(img, default_right, w, top, bottom):
    """Scans for candle-colored tall column runs beyond the default crop
    line; if found (a real cluster, not a single stray colored pixel),
    extends the right boundary just past them instead of cutting them off.
    Restricted to the same top:bottom candle band as the final crop - the
    first version of this scanned the full image height and picked up
    colored UI elements above the chart (e.g. red SELL/BUY price boxes) as
    false "candles", which would have wrongly widened the crop on charts
    that never actually needed it."""
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = _mask_for_ranges(hsv, GREEN_RANGES) | _mask_for_ranges(hsv, RED_RANGES)
        mask = mask[top:bottom, :]
        min_height = max(8, int((bottom - top) * 0.035))
        tall_cols = []
        for x in range(default_right, w):
            col = mask[:, x]
            on = np.nonzero(col)[0]
            if len(on) == 0:
                continue
            gaps = np.where(np.diff(on) > 3)[0]
            segs = np.split(on, gaps + 1) if len(gaps) else [on]
            if max(len(s) for s in segs) >= min_height:
                tall_cols.append(x)
        if len(tall_cols) < 3:
            return default_right  # no real cluster past the default line
        return min(w, max(tall_cols) + 15)
    except Exception:
        return default_right


def _column_runs(mask):
    """
    For each column, finds the longest contiguous vertical run of "on"
    pixels and its (top, bottom) bounds. Returns a list of dicts per
    column: {"height": int, "top": int, "bottom": int} or None if empty.
    """
    h, w = mask.shape
    results = [None] * w
    for x in range(w):
        col = mask[:, x]
        on = np.nonzero(col)[0]
        if len(on) == 0:
            continue
        # find the longest contiguous run (handles small gaps/antialiasing)
        gaps = np.where(np.diff(on) > 3)[0]
        segments = np.split(on, gaps + 1) if len(gaps) else [on]
        best = max(segments, key=len)
        results[x] = {"height": int(best[-1] - best[0] + 1), "top": int(best[0]), "bottom": int(best[-1])}
    return results


def _find_candle_columns(mask, min_height=10, max_center_drift=4):
    """
    Scans column runs and groups consecutive columns with a tall-enough,
    POSITION-STABLE run into candle "slots". A real candle body/wick stays
    at roughly the same vertical position across its width; a diagonal
    trade-line overlay (same color family) instead drifts steadily up or
    down column-by-column, so we reject columns whose run center has
    drifted too far from the previous accepted column - this is what
    correctly tells candles apart from diagonal line overlays without
    needing fragile shape/fill-ratio heuristics.
    """
    runs = _column_runs(mask)
    w = len(runs)

    slots = []
    current = None
    prev_center = None

    for x in range(w):
        r = runs[x]
        is_tall_enough = r is not None and r["height"] >= min_height
        center = (r["top"] + r["bottom"]) / 2 if r else None

        drifted_too_much = (
            is_tall_enough and prev_center is not None
            and abs(center - prev_center) > max_center_drift
        )

        if is_tall_enough and not drifted_too_much:
            if current is None:
                current = {"x_start": x, "x_end": x, "top": r["top"], "bottom": r["bottom"]}
            else:
                current["x_end"] = x
                current["top"] = min(current["top"], r["top"])
                current["bottom"] = max(current["bottom"], r["bottom"])
            prev_center = center
        else:
            if current is not None:
                slots.append(current)
                current = None
            prev_center = center if is_tall_enough else None
    if current is not None:
        slots.append(current)

    return slots


def _split_wide_slot(mask, slot, reference_width):
    """
    If a detected slot is much wider than a typical single candle, it's
    likely 2+ candles whose wicks touch with no gap. Split it evenly into
    the estimated number of candles and recompute each sub-slot's actual
    top/bottom from the mask.
    """
    width = slot["x_end"] - slot["x_start"] + 1
    n = max(1, round(width / reference_width))
    if n <= 1:
        return [slot]

    slice_w = width / n
    sub_slots = []
    for i in range(n):
        sx0 = slot["x_start"] + int(i * slice_w)
        sx1 = slot["x_start"] + int((i + 1) * slice_w) - 1
        sx1 = max(sx1, sx0)
        region = mask[:, sx0:sx1 + 1]
        rows = np.nonzero(region.sum(axis=1) > 0)[0]
        if len(rows) == 0:
            continue
        sub_slots.append({
            "x_start": sx0, "x_end": sx1,
            "top": int(rows.min()), "bottom": int(rows.max()),
        })
    return sub_slots if sub_slots else [slot]


def detect_candles(image_path):
    """
    Main entry point. Returns (candles_list, debug_image, offset).
    candles_list is sorted left-to-right (chronological order).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image file")

    cropped, offset = crop_chart_area(img)
    hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)

    green_mask = _mask_for_ranges(hsv, GREEN_RANGES)
    red_mask = _mask_for_ranges(hsv, RED_RANGES)

    # Light cleanup only - column-run approach handles most noise natively
    kernel = np.ones((2, 2), np.uint8)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    # A real candle's wick is a meaningful fraction of the visible chart
    # height; using an absolute floor tuned to typical screenshot sizes
    # filters out thin diagonal trade-lines (which only touch 1-3px/column)
    # without needing fragile per-shape heuristics.
    chart_h = cropped.shape[0]
    min_height = max(8, int(chart_h * 0.035))
    max_drift = max(6, int(chart_h * 0.025))

    all_slots = []
    for color_name, mask in (("green", green_mask), ("red", red_mask)):
        slots = _find_candle_columns(mask, min_height=min_height, max_center_drift=max_drift)
        for s in slots:
            s["color"] = color_name
        all_slots.extend(slots)

    if not all_slots:
        return [], cropped, offset

    # Fix: on thin/high-DPI screenshots (candle body only 2-3px wide), a
    # single real candle's column-run sometimes gets cut into two adjacent
    # slots by one column of anti-aliasing/gridline noise that drops just
    # below min_height. Left unfixed, this duplicates the candle and
    # corrupts the last-few-candles window every pattern/signal reads from
    # (verified against a real chart screenshot — same-color slots 2-3px
    # apart with near-identical top/bottom were being counted as two
    # separate candles). Reunite same-color slots that are only a couple
    # columns apart AND whose vertical spans overlap heavily — a genuinely
    # separate adjacent candle almost never has the same body/wick range.
    all_slots.sort(key=lambda s: s["x_start"])
    merged_slots = []
    for s in all_slots:
        if merged_slots:
            last = merged_slots[-1]
            gap = s["x_start"] - last["x_end"] - 1
            span = max(last["bottom"], s["bottom"]) - min(last["top"], s["top"])
            overlap = min(last["bottom"], s["bottom"]) - max(last["top"], s["top"])
            overlap_ratio = (overlap / span) if span > 0 else 1.0
            if s["color"] == last["color"] and 0 <= gap <= 3 and overlap_ratio > 0.6:
                last["x_end"] = s["x_end"]
                last["top"] = min(last["top"], s["top"])
                last["bottom"] = max(last["bottom"], s["bottom"])
                continue
        merged_slots.append(dict(s))
    all_slots = merged_slots

    # Estimate a reference single-candle BODY width from the slots (used to
    # decide which slots are actually 2+ candles merged together).
    # Bug fix: this used to take the flat median of ALL slot widths, but
    # doji/small-range candles render with a much narrower footprint than
    # full-bodied candles on some chart themes (verified on a real
    # screenshot where ~half the slots were thin dojis) — that dragged the
    # median down and made ordinary full-width candles look "too wide",
    # triggering the merged-slot splitter on completely normal single
    # candles and duplicating them in the output. Using the 65th percentile
    # instead reliably lands on the full-body-candle width even when dojis
    # make up close to half the chart, while still catching genuinely
    # merged/wide slots (which are ~2x that width or more).
    widths = sorted(s["x_end"] - s["x_start"] + 1 for s in all_slots)
    ref_idx = min(len(widths) - 1, int(len(widths) * 0.65))
    median_w = widths[ref_idx]

    final_slots = []
    for s in all_slots:
        width = s["x_end"] - s["x_start"] + 1
        if median_w > 0 and width > median_w * 1.8:
            mask = green_mask if s["color"] == "green" else red_mask
            for sub in _split_wide_slot(mask, s, median_w):
                sub["color"] = s["color"]
                final_slots.append(sub)
        else:
            final_slots.append(s)

    # Build Candle objects. For the wick vs body distinction we look at
    # the actual pixel width used by the slot's peak run (a wick is
    # narrower than the body at the same x-range), approximated here by
    # using the full column-run bounds as both body and wick extent, then
    # refining the body using the widest sub-run within the slot.
    candle_objs = []
    for s in final_slots:
        x_start, x_end = s["x_start"], s["x_end"]
        color = s["color"]
        mask = green_mask if color == "green" else red_mask
        width = x_end - x_start + 1
        center_x = (x_start + x_end) / 2

        # Body = rows where MOST columns in this slot are lit (wide part);
        # Wick = rows where only a thin sliver of columns are lit (narrow part)
        region = mask[:, x_start:x_end + 1]
        row_counts = (region > 0).sum(axis=1)  # how many columns lit per row
        if row_counts.max() == 0:
            continue
        body_threshold = max(1, row_counts.max() * 0.6)
        body_rows = np.nonzero(row_counts >= body_threshold)[0]
        any_rows = np.nonzero(row_counts > 0)[0]

        wick_top, wick_bottom = int(any_rows.min()), int(any_rows.max())
        if len(body_rows) > 0:
            body_top, body_bottom = int(body_rows.min()), int(body_rows.max())
        else:
            body_top, body_bottom = wick_top, wick_bottom

        candle_objs.append(Candle(
            x=center_x,
            body_top=body_top,
            body_bottom=body_bottom,
            wick_top=wick_top,
            wick_bottom=wick_bottom,
            color=color,
            width=width,
        ))

    candle_objs.sort(key=lambda c: c.x)

    # Drop extreme width outliers (stray fragments that survived splitting)
    if len(candle_objs) >= 4:
        widths = sorted(c.width for c in candle_objs)
        med = widths[len(widths) // 2]
        candle_objs = [c for c in candle_objs if med * 0.3 <= c.width <= med * 3.5]

    return candle_objs, cropped, offset
