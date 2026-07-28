"""
MI NEXUS - Result Card Renderer
Builds a beautiful 9:16 dark/green glassmorphism result image:
  - Original chart pasted on a clean styled background
  - Next candle prediction (UP/DOWN) marker drawn on chart
  - Pattern + confidence + timeframe details
  - MI NEXUS branding footer
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime, timezone, timedelta

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REG = os.path.join(FONT_DIR, "DejaVuSans.ttf")

CANVAS_W = 1080
CANVAS_H = 2200

# MI NEXUS palette
BG_TOP = (6, 12, 10)
BG_BOTTOM = (2, 4, 4)
NEON_GREEN = (57, 255, 20)
SOFT_GREEN = (120, 220, 140)
NEON_RED = (255, 60, 60)
GOLD = (255, 208, 80)
SILVER = (210, 215, 220)
CARD_BG = (14, 22, 20)
CARD_BORDER = (60, 255, 140)


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _vertical_gradient(w, h, top_color, bottom_color):
    base = Image.new("RGB", (w, h), top_color)
    top = Image.new("RGB", (w, h), top_color)
    bottom = Image.new("RGB", (w, h), bottom_color)
    mask = Image.new("L", (w, h))
    mask_data = []
    for y in range(h):
        mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    base.paste(bottom, (0, 0), mask)
    return base


def _rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _drop_shadow(canvas, box, radius, offset=(0, 10), blur=22, opacity=140):
    """Draws a soft blurred shadow behind a card box for pseudo-3D depth."""
    x0, y0, x1, y1 = box
    ox, oy = offset
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    sdraw.rounded_rectangle((x0 + ox, y0 + oy, x1 + ox, y1 + oy), radius=radius, fill=(0, 0, 0, opacity))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow_layer)


def _bevel_card(draw, box, radius, fill, top_light, bottom_dark, width=3):
    """
    Fakes a 3D beveled-glass edge: draws the card fill, then a bright
    top-left partial arc/line and a darker bottom-right partial line so
    the card reads as having physical depth rather than a flat outline.
    """
    x0, y0, x1, y1 = box
    _rounded_rect(draw, box, radius, fill=fill)
    # bottom-right dark edge (shadow side)
    draw.arc((x0, y0, x1, y1), start=20, end=160, fill=bottom_dark, width=width)
    # top-left light edge (highlight side)
    draw.arc((x0, y0, x1, y1), start=200, end=340, fill=top_light, width=width)
    # crisp thin outline on top for definition
    draw.rounded_rectangle(box, radius=radius, outline=top_light, width=1)


def _glass_shine(canvas, box, radius, opacity=34):
    """Adds a soft diagonal highlight band across the top of a card, like
    light glinting off glass — reinforces the premium/3D feel."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    shine_layer = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shine_layer)
    sdraw.polygon(
        [(0, 0), (w * 0.55, 0), (w * 0.25, h * 0.5), (0, h * 0.5)],
        fill=(255, 255, 255, opacity)
    )
    shine_layer = shine_layer.filter(ImageFilter.GaussianBlur(6))
    mask = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    # Clip the shine to the card's rounded shape before compositing, so it
    # never spills outside the card's corners.
    clipped_shine = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    clipped_shine.paste(shine_layer, (0, 0), mask)
    composed = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    composed.paste(clipped_shine, (int(x0), int(y0)), clipped_shine)
    canvas.alpha_composite(composed)


def _pro_ribbon(canvas, top_right_xy, accent):
    # Small diagonal 'PRO' ribbon badge in a card's top-right corner.
    x, y = top_right_xy
    ribbon = Image.new("RGBA", (170, 170), (0, 0, 0, 0))
    rdraw = ImageDraw.Draw(ribbon)
    rdraw.polygon([(30, 0), (170, 0), (170, 140), (140, 170), (0, 40)], fill=accent + (235,))
    ribbon = ribbon.rotate(0)
    font = _font(FONT_BOLD, 24)
    rdraw.text((100, 45), "PRO", font=font, fill=(10, 15, 12), anchor="mm")
    canvas.alpha_composite(ribbon, (int(x) - 170, int(y)))


def _draw_dots(draw, center_x, y, count, filled_count, color, radius=7, spacing=22):
    """Draws a row of small dots, first `filled_count` filled, rest hollow — used as an intensity meter."""
    total_w = spacing * (count - 1)
    start_x = center_x - total_w / 2
    for i in range(count):
        cx = start_x + i * spacing
        if i < filled_count:
            draw.ellipse((cx - radius, y - radius, cx + radius, y + radius), fill=color)
        else:
            draw.ellipse((cx - radius, y - radius, cx + radius, y + radius), outline=(80, 90, 88), width=2)


def _draw_bull_icon(draw, cx, cy, size, color):
    """Geometric bull silhouette: rounded body, curved horns, sturdy legs, upward horn tips for a 'bullish' read."""
    body_w, body_h = size, size * 0.48
    body_top = cy - body_h * 0.3
    body_bottom = cy + body_h * 0.5

    # body (rounded)
    draw.rounded_rectangle(
        (cx - body_w / 2, body_top, cx + body_w / 2, body_bottom),
        radius=body_h * 0.5, outline=color, width=5
    )

    # head (small circle above body, left side)
    head_r = size * 0.16
    head_cx = cx - body_w * 0.32
    head_cy = body_top - head_r * 0.6
    draw.ellipse((head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r),
                 outline=color, width=5)

    # horns (curved arcs sweeping upward and outward from the head)
    horn_r = size * 0.20
    draw.arc((head_cx - horn_r * 1.6, head_cy - horn_r * 1.7,
              head_cx + horn_r * 0.4, head_cy + horn_r * 0.3), 200, 320, fill=color, width=5)
    draw.arc((head_cx - horn_r * 0.4, head_cy - horn_r * 1.9,
              head_cx + horn_r * 1.6, head_cy + horn_r * 0.1), 220, 340, fill=color, width=5)

    # legs
    for lx in (-0.32, -0.12, 0.12, 0.32):
        draw.line((cx + lx * body_w, body_bottom - 4, cx + lx * body_w, body_bottom + size * 0.22),
                   fill=color, width=5)

    # upward tail flick (bullish motion cue)
    draw.line((cx + body_w * 0.48, cy, cx + body_w * 0.72, cy - size * 0.28), fill=color, width=5)
    draw.line((cx + body_w * 0.72, cy - size * 0.28, cx + body_w * 0.62, cy - size * 0.22), fill=color, width=5)
    draw.line((cx + body_w * 0.72, cy - size * 0.28, cx + body_w * 0.80, cy - size * 0.14), fill=color, width=5)


def _draw_bear_icon(draw, cx, cy, size, color):
    """Geometric bear silhouette: rounder heavy body, round ears, downward motion cue for 'bearish' read."""
    body_w, body_h = size * 1.05, size * 0.52
    body_top = cy - body_h * 0.25
    body_bottom = cy + body_h * 0.55

    # body (rounded, heavier/rounder than the bull)
    draw.rounded_rectangle(
        (cx - body_w / 2, body_top, cx + body_w / 2, body_bottom),
        radius=body_h * 0.55, outline=color, width=5
    )

    # head (rounder, centered-left)
    head_r = size * 0.19
    head_cx = cx - body_w * 0.28
    head_cy = body_top - head_r * 0.5
    draw.ellipse((head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r),
                 outline=color, width=5)

    # small round ears
    ear_r = size * 0.09
    draw.ellipse((head_cx - head_r * 0.7 - ear_r, head_cy - head_r * 0.9 - ear_r,
                  head_cx - head_r * 0.7 + ear_r, head_cy - head_r * 0.9 + ear_r), outline=color, width=4)
    draw.ellipse((head_cx + head_r * 0.7 - ear_r, head_cy - head_r * 0.9 - ear_r,
                  head_cx + head_r * 0.7 + ear_r, head_cy - head_r * 0.9 + ear_r), outline=color, width=4)

    # snout
    draw.ellipse((head_cx - head_r * 0.55, head_cy + head_r * 0.15,
                  head_cx + head_r * 0.75, head_cy + head_r * 0.85), outline=color, width=4)

    # legs (heavier stance)
    for lx in (-0.34, -0.12, 0.12, 0.34):
        draw.line((cx + lx * body_w, body_bottom - 4, cx + lx * body_w, body_bottom + size * 0.2),
                   fill=color, width=6)

    # downward motion cue (bearish claw-swipe / falling arrow)
    draw.line((cx + body_w * 0.42, cy, cx + body_w * 0.66, cy + size * 0.30), fill=color, width=5)
    draw.line((cx + body_w * 0.66, cy + size * 0.30, cx + body_w * 0.54, cy + size * 0.26), fill=color, width=5)
    draw.line((cx + body_w * 0.66, cy + size * 0.30, cx + body_w * 0.70, cy + size * 0.14), fill=color, width=5)


def _draw_wave(draw, box, color, amplitude_ratio=0.5, cycles=3.5):
    """Draws a simple sine-like zig-zag wave inside the given box (volatility visual)."""
    import math
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    mid_y = y0 + h / 2
    amp = (h / 2) * amplitude_ratio
    points = []
    steps = 60
    for i in range(steps + 1):
        t = i / steps
        x = x0 + t * w
        y = mid_y + amp * math.sin(t * cycles * 2 * math.pi)
        points.append((x, y))
    draw.line(points, fill=color, width=4, joint="curve")


def _glow_text(img, xy, text, font, fill, glow_color, glow_radius=8, anchor="la"):
    """Draws text with a soft neon glow behind it."""
    txt_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(txt_layer)
    d.text(xy, text, font=font, fill=glow_color, anchor=anchor)
    txt_layer = txt_layer.filter(ImageFilter.GaussianBlur(glow_radius))
    img.alpha_composite(txt_layer)
    d2 = ImageDraw.Draw(img)
    d2.text(xy, text, font=font, fill=fill, anchor=anchor)



def _paste_chart(canvas, chart_bgr_path_or_img, box):
    """Pastes chart image (fit) into the given box with rounded mask."""
    from PIL import Image as PILImage
    if isinstance(chart_bgr_path_or_img, str):
        chart = PILImage.open(chart_bgr_path_or_img).convert("RGB")
    else:
        chart = chart_bgr_path_or_img.convert("RGB")

    bx0, by0, bx1, by1 = box
    bw, bh = bx1 - bx0, by1 - by0

    # Fit chart into box maintaining aspect ratio, center-crop if needed
    chart_ratio = chart.width / chart.height
    box_ratio = bw / bh

    if chart_ratio > box_ratio:
        new_h = bh
        new_w = int(bh * chart_ratio)
    else:
        new_w = bw
        new_h = int(bw / chart_ratio)

    chart_resized = chart.resize((new_w, new_h), Image.LANCZOS)

    # center crop
    left = (new_w - bw) // 2
    top = (new_h - bh) // 2
    chart_cropped = chart_resized.crop((left, top, left + bw, top + bh))

    mask = Image.new("L", (bw, bh), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0, 0, bw, bh), radius=28, fill=255)

    canvas.paste(chart_cropped, (bx0, by0), mask)
    return chart_cropped, (bx0, by0, bw, bh)


def render_result_card(
    chart_image_path,
    prediction,          # dict from predict_next_candle()
    pair_name="Chart Analysis",
    timeframe_label="1 MIN",
    utc_offset_hours=5,
    logo_path=None,
    output_path="/tmp/mi_nexus_result.png",
    candles=None,        # optional: Candle objects for the premium 3D digital chart redraw
):
    canvas = _vertical_gradient(CANVAS_W, CANVAS_H, BG_TOP, BG_BOTTOM).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    direction = prediction["direction"]
    confidence = prediction["confidence"]
    strength = prediction.get("strength", "MODERATE")
    patterns = prediction["patterns"]
    is_up = direction == "UP"
    accent = NEON_GREEN if is_up else NEON_RED

    sub_font = _font(FONT_REG, 30)

    # Logo (optional)
    y_cursor = 36
    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo_size = 100
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        canvas.alpha_composite(logo, ((CANVAS_W - logo_size) // 2, y_cursor))
        y_cursor += logo_size + 8

    header_font = _font(FONT_BOLD, 50)
    _glow_text(canvas, (CANVAS_W // 2, y_cursor), "MI NEXUS", header_font,
               fill=(255, 255, 255), glow_color=NEON_GREEN, glow_radius=6, anchor="ma")
    y_cursor += 58
    draw.text((CANVAS_W // 2, y_cursor), "ANALYZE  •  PREDICT  •  PROFIT",
              font=sub_font, fill=SOFT_GREEN, anchor="ma")
    y_cursor += 36

    pro_tag_font = _font(FONT_BOLD, 20)
    pro_tag_text = "⚙ V5 PRO ENGINE"
    pro_tag_w = draw.textlength(pro_tag_text, font=pro_tag_font)
    pro_tag_box = (CANVAS_W // 2 - pro_tag_w / 2 - 16, y_cursor,
                   CANVAS_W // 2 + pro_tag_w / 2 + 16, y_cursor + 32)
    _rounded_rect(draw, pro_tag_box, radius=16, fill=(18, 26, 24), outline=GOLD, width=1)
    draw.text((CANVAS_W // 2, y_cursor + 16), pro_tag_text, font=pro_tag_font, fill=GOLD, anchor="mm")
    y_cursor += 46

    # Pair name badge
    pair_font = _font(FONT_BOLD, 32)
    pair_text = f"★ {pair_name} ★"
    pair_w = draw.textlength(pair_text, font=pair_font)
    badge_pad = 24
    badge_box = (CANVAS_W // 2 - pair_w / 2 - badge_pad, y_cursor,
                 CANVAS_W // 2 + pair_w / 2 + badge_pad, y_cursor + 54)
    _rounded_rect(draw, badge_box, radius=27, fill=(20, 30, 28), outline=SOFT_GREEN, width=2)
    draw.text((CANVAS_W // 2, y_cursor + 27), pair_text, font=pair_font, fill=(255, 255, 255), anchor="mm")
    y_cursor += 74

    # ---------------- Chart Card (3D depth: shadow + bevel + glass shine) ----------------
    card_top = y_cursor
    card_bottom = card_top + 840
    card_box = (40, card_top, CANVAS_W - 40, card_bottom)
    _drop_shadow(canvas, card_box, radius=32, offset=(0, 14), blur=26, opacity=150)
    draw = ImageDraw.Draw(canvas)
    _bevel_card(draw, card_box, radius=32, fill=CARD_BG,
                top_light=(120, 255, 180), bottom_dark=(0, 0, 0), width=4)
    draw.rounded_rectangle(card_box, radius=32, outline=CARD_BORDER, width=2)
    _glass_shine(canvas, card_box, radius=32, opacity=26)
    draw = ImageDraw.Draw(canvas)
    _pro_ribbon(canvas, (CANVAS_W - 40, card_top), accent)
    draw = ImageDraw.Draw(canvas)

    chart_box = (70, card_top + 25, CANVAS_W - 70, card_bottom - 210)
    _paste_chart(canvas, chart_image_path, chart_box)
    draw = ImageDraw.Draw(canvas)  # refresh draw handle after paste

    # Direction arrow marker overlay (top-right of chart box)
    arrow_symbol = "▲ UP" if is_up else "▼ DOWN"
    marker_box = (chart_box[2] - 240, chart_box[1] + 18, chart_box[2] - 18, chart_box[1] + 90)
    _rounded_rect(draw, marker_box, radius=18, fill=(0, 0, 0, 190), outline=accent, width=3)
    draw.text(((marker_box[0] + marker_box[2]) // 2, (marker_box[1] + marker_box[3]) // 2),
               arrow_symbol, font=_font(FONT_BOLD, 34), fill=accent, anchor="mm")

    # Strength badge (top-left of chart box)
    strength_font = _font(FONT_BOLD, 24)
    strength_text = f"● {strength}"
    strength_w = draw.textlength(strength_text, font=strength_font)
    sbadge_box = (chart_box[0] + 18, chart_box[1] + 18, chart_box[0] + 18 + strength_w + 30, chart_box[1] + 62)
    _rounded_rect(draw, sbadge_box, radius=14, fill=(0, 0, 0, 190), outline=accent, width=2)
    draw.text((sbadge_box[0] + 15, (sbadge_box[1] + sbadge_box[3]) // 2), strength_text,
              font=strength_font, fill=accent, anchor="lm")

    # ---------------- Prediction Info Row (inside card) ----------------
    info_y = chart_box[3] + 20
    label_font = _font(FONT_BOLD, 40)
    small_font = _font(FONT_REG, 26)

    _glow_text(canvas, (CANVAS_W // 2, info_y), f"NEXT CANDLE: {direction}",
               label_font, fill=(255, 255, 255), glow_color=accent, glow_radius=6, anchor="ma")
    draw = ImageDraw.Draw(canvas)
    info_y += 58

    # Confidence bar (with glass shine strip + soft glow for a premium feel)
    bar_w = CANVAS_W - 200
    bar_x0 = 100
    bar_y0 = info_y
    bar_h = 30
    _drop_shadow(canvas, (bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h), radius=15,
                 offset=(0, 4), blur=10, opacity=90)
    draw = ImageDraw.Draw(canvas)
    _rounded_rect(draw, (bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h), radius=15,
                  fill=(28, 38, 36), outline=(55, 75, 70), width=1)
    fill_w = max(bar_h, int(bar_w * (confidence / 100)))
    _rounded_rect(draw, (bar_x0, bar_y0, bar_x0 + fill_w, bar_y0 + bar_h), radius=15, fill=accent)
    # thin bright highlight line near the top of the fill for a glassy 3D look
    if fill_w > 16:
        draw.line((bar_x0 + 8, bar_y0 + 6, bar_x0 + fill_w - 8, bar_y0 + 6),
                  fill=tuple(min(255, c + 90) for c in accent), width=2)
    draw.text((CANVAS_W // 2, bar_y0 + bar_h + 22), f"CONFIDENCE: {confidence}%",
              font=small_font, fill=SILVER, anchor="ma")

    # ---------------- Details Card (3D depth) ----------------
    details_top = card_bottom + 24
    details_bottom = details_top + 520
    details_box = (40, details_top, CANVAS_W - 40, details_bottom)
    _drop_shadow(canvas, details_box, radius=28, offset=(0, 10), blur=20, opacity=120)
    draw = ImageDraw.Draw(canvas)
    _bevel_card(draw, details_box, radius=28, fill=CARD_BG,
                top_light=(90, 130, 115), bottom_dark=(0, 0, 0), width=3)
    draw.rounded_rectangle(details_box, radius=28, outline=(50, 70, 65), width=1)

    dx = 70
    dy = details_top + 20
    row_font = _font(FONT_REG, 28)
    row_font_b = _font(FONT_BOLD, 28)

    draw.text((dx, dy), "Timeframe:", font=row_font, fill=SILVER)
    draw.text((CANVAS_W - 70, dy), timeframe_label, font=row_font_b, fill=(255, 255, 255), anchor="ra")
    dy += 46

    tz = timezone(timedelta(hours=utc_offset_hours))
    now_str = datetime.now(tz).strftime("%H:%M:%S")
    draw.text((dx, dy), f"Time (UTC{'+' if utc_offset_hours >= 0 else ''}{utc_offset_hours}):",
              font=row_font, fill=SILVER)
    draw.text((CANVAS_W - 70, dy), now_str, font=row_font_b, fill=(255, 255, 255), anchor="ra")
    dy += 46

    draw.text((dx, dy), "Trend Bias:", font=row_font, fill=SILVER)
    bias_val = prediction.get("trend_bias", 0)
    bias_label = "Bullish" if bias_val > 0.05 else ("Bearish" if bias_val < -0.05 else "Flat")
    draw.text((CANVAS_W - 70, dy), bias_label, font=row_font_b, fill=(255, 255, 255), anchor="ra")
    dy += 46

    draw.text((dx, dy), "Market Condition:", font=row_font, fill=SILVER)
    choppiness = prediction.get("choppiness", 0)
    if choppiness < 0.3:
        condition_label, condition_color = "Clean Trend", NEON_GREEN
    elif choppiness < 0.6:
        condition_label, condition_color = "Mixed", GOLD
    else:
        condition_label, condition_color = "Choppy", NEON_RED
    draw.text((CANVAS_W - 70, dy), condition_label, font=row_font_b, fill=condition_color, anchor="ra")
    dy += 52

    draw.text((dx, dy), "Patterns Detected:", font=row_font, fill=SILVER)
    dy += 42

    breakdown = prediction.get("breakdown", [])
    top_patterns = sorted(breakdown, key=lambda p: p["reliability"], reverse=True)[:5]
    pat_font = _font(FONT_REG, 24)
    for p in top_patterns:
        sig_symbol = "▲" if p["signal"] == "bullish" else ("▼" if p["signal"] == "bearish" else "●")
        sig_color = NEON_GREEN if p["signal"] == "bullish" else (NEON_RED if p["signal"] == "bearish" else SILVER)
        line = f"{sig_symbol} {p['name']}"
        draw.text((dx + 10, dy), line, font=pat_font, fill=sig_color)
        draw.text((CANVAS_W - 70, dy), f"{int(p['reliability'])}% reliability",
                   font=_font(FONT_REG, 22), fill=SILVER, anchor="ra")
        dy += 38

    # ---------------- Two-Column Insight Cards: Market Sentiment + Volatility ----------------
    insight_top = details_bottom + 24
    insight_h = 260
    col_gap = 20
    col_w = (CANVAS_W - 80 - col_gap) / 2

    sentiment_box = (40, insight_top, 40 + col_w, insight_top + insight_h)
    volatility_box = (40 + col_w + col_gap, insight_top, CANVAS_W - 40, insight_top + insight_h)

    # --- Market Sentiment card (3D depth) ---
    _drop_shadow(canvas, sentiment_box, radius=24, offset=(0, 8), blur=16, opacity=110)
    draw = ImageDraw.Draw(canvas)
    _bevel_card(draw, sentiment_box, radius=24, fill=CARD_BG,
                top_light=tuple(min(255, c + 60) for c in accent), bottom_dark=(0, 0, 0), width=3)
    draw.rounded_rectangle(sentiment_box, radius=24, outline=accent, width=1)
    sc_cx = (sentiment_box[0] + sentiment_box[2]) / 2
    label_font_sm = _font(FONT_BOLD, 22)
    draw.text((sc_cx, sentiment_box[1] + 26), "MARKET SENTIMENT", font=label_font_sm, fill=accent, anchor="ma")

    icon_cy = sentiment_box[1] + 105
    if is_up:
        _draw_bull_icon(draw, sc_cx, icon_cy, 100, accent)
    else:
        _draw_bear_icon(draw, sc_cx, icon_cy, 100, accent)

    sentiment_label_font = _font(FONT_BOLD, 30)
    sentiment_text = "BULLISH" if is_up else "BEARISH"
    draw.text((sc_cx, sentiment_box[1] + 165), sentiment_text, font=sentiment_label_font, fill=accent, anchor="ma")

    # Dot intensity meter reflecting confidence (out of 6 dots)
    filled_dots = max(1, min(6, round((confidence - 50) / 50 * 6)))
    _draw_dots(draw, sc_cx, sentiment_box[1] + 215, 6, filled_dots, accent)

    # --- Volatility card (3D depth) ---
    _drop_shadow(canvas, volatility_box, radius=24, offset=(0, 8), blur=16, opacity=110)
    draw = ImageDraw.Draw(canvas)
    _bevel_card(draw, volatility_box, radius=24, fill=CARD_BG,
                top_light=(150, 255, 190), bottom_dark=(0, 0, 0), width=3)
    draw.rounded_rectangle(volatility_box, radius=24, outline=NEON_GREEN, width=1)
    vc_cx = (volatility_box[0] + volatility_box[2]) / 2
    draw.text((vc_cx, volatility_box[1] + 26), "VOLATILITY", font=label_font_sm, fill=NEON_GREEN, anchor="ma")

    wave_box = (volatility_box[0] + 24, volatility_box[1] + 65, volatility_box[2] - 24, volatility_box[1] + 140)
    choppiness = prediction.get("choppiness", 0)
    if choppiness < 0.3:
        vol_label, vol_color, vol_dots, wave_cycles = "LOW", NEON_GREEN, 2, 2.0
    elif choppiness < 0.6:
        vol_label, vol_color, vol_dots, wave_cycles = "MEDIUM", GOLD, 4, 3.0
    else:
        vol_label, vol_color, vol_dots, wave_cycles = "HIGH", NEON_RED, 6, 4.5
    _draw_wave(draw, wave_box, vol_color, amplitude_ratio=0.55, cycles=wave_cycles)

    draw.text((vc_cx, volatility_box[1] + 165), vol_label, font=sentiment_label_font, fill=vol_color, anchor="ma")
    _draw_dots(draw, vc_cx, volatility_box[1] + 215, 6, vol_dots, vol_color)

    # ---------------- Tip Box ----------------
    tip_top = insight_top + insight_h + 20
    tip_bottom = tip_top + 70
    tip_box = (40, tip_top, CANVAS_W - 40, tip_bottom)
    _rounded_rect(draw, tip_box, radius=20, fill=CARD_BG, outline=(50, 70, 65), width=2)

    if confidence >= 85:
        tip_text = "Strong setup — still confirm before entering."
    elif choppiness >= 0.6:
        tip_text = "Choppy market — consider waiting this one out."
    else:
        tip_text = "Wait for confirmation before entering a trade."

    tip_font = _font(FONT_REG, 24)
    tip_font_b = _font(FONT_BOLD, 24)
    tip_x = 70
    draw.text((tip_x, (tip_top + tip_bottom) / 2), "💡 TIP:", font=tip_font_b, fill=GOLD, anchor="lm")
    tip_label_w = draw.textlength("💡 TIP:  ", font=tip_font_b)
    draw.text((tip_x + tip_label_w, (tip_top + tip_bottom) / 2), tip_text, font=tip_font, fill=SILVER, anchor="lm")

    footer_y_start = tip_bottom + 30

    # ---------------- Footer ----------------
    footer_font = _font(FONT_REG, 26)
    draw.text((CANVAS_W // 2, footer_y_start + 30),
              "⚠ Educational analysis only — not financial advice",
              font=footer_font, fill=(140, 150, 150), anchor="ma")
    draw.text((CANVAS_W // 2, footer_y_start + 60),
              "MI NEXUS © Muslim Islam Network",
              font=footer_font, fill=SOFT_GREEN, anchor="ma")

    final_height = footer_y_start + 110
    canvas = canvas.crop((0, 0, CANVAS_W, min(CANVAS_H, final_height) if final_height < CANVAS_H else CANVAS_H))
    if final_height > CANVAS_H:
        # extend canvas if content overflowed the default height
        extended = Image.new("RGBA", (CANVAS_W, final_height), BG_BOTTOM + (255,))
        extended.paste(canvas, (0, 0))
        canvas = extended

    canvas.convert("RGB").save(output_path, quality=95)
    return output_path
