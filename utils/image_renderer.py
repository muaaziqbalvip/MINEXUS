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
CANVAS_H = 1920

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
    y_cursor += 40

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

    # ---------------- Chart Card ----------------
    card_top = y_cursor
    card_bottom = card_top + 840
    card_box = (40, card_top, CANVAS_W - 40, card_bottom)
    _rounded_rect(draw, card_box, radius=32, fill=CARD_BG, outline=CARD_BORDER, width=3)

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

    # Confidence bar
    bar_w = CANVAS_W - 200
    bar_x0 = 100
    bar_y0 = info_y
    bar_h = 26
    _rounded_rect(draw, (bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h), radius=13,
                  fill=(30, 40, 38))
    fill_w = int(bar_w * (confidence / 100))
    _rounded_rect(draw, (bar_x0, bar_y0, bar_x0 + fill_w, bar_y0 + bar_h), radius=13, fill=accent)
    draw.text((CANVAS_W // 2, bar_y0 + bar_h + 20), f"CONFIDENCE: {confidence}%",
              font=small_font, fill=SILVER, anchor="ma")

    # ---------------- Details Card ----------------
    details_top = card_bottom + 24
    details_bottom = details_top + 480
    details_box = (40, details_top, CANVAS_W - 40, details_bottom)
    _rounded_rect(draw, details_box, radius=28, fill=CARD_BG, outline=(50, 70, 65), width=2)

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
    dy += 46

    draw.text((dx, dy), "Patterns Detected:", font=row_font, fill=SILVER)
    dy += 42

    breakdown = prediction.get("breakdown", [])
    top_patterns = sorted(breakdown, key=lambda p: p["reliability"], reverse=True)[:4]
    pat_font = _font(FONT_REG, 24)
    for p in top_patterns:
        sig_symbol = "▲" if p["signal"] == "bullish" else ("▼" if p["signal"] == "bearish" else "●")
        sig_color = NEON_GREEN if p["signal"] == "bullish" else (NEON_RED if p["signal"] == "bearish" else SILVER)
        line = f"{sig_symbol} {p['name']}"
        draw.text((dx + 10, dy), line, font=pat_font, fill=sig_color)
        draw.text((CANVAS_W - 70, dy), f"{int(p['reliability'])}% reliability",
                   font=_font(FONT_REG, 22), fill=SILVER, anchor="ra")
        dy += 38

    # ---------------- Footer ----------------
    footer_font = _font(FONT_REG, 26)
    draw.text((CANVAS_W // 2, CANVAS_H - 60),
              "⚠ Educational analysis only — not financial advice",
              font=footer_font, fill=(140, 150, 150), anchor="ma")
    draw.text((CANVAS_W // 2, CANVAS_H - 30),
              "MI NEXUS © Muslim Islam Network",
              font=footer_font, fill=SOFT_GREEN, anchor="ma")

    canvas.convert("RGB").save(output_path, quality=95)
    return output_path
