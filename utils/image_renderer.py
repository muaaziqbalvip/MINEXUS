"""
MI NEXUS - Premium Image Renderer v20
Builds beautiful, colorful, 3D signal cards & menu banners.
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime, timezone, timedelta

# ─── Font Setup (Windows-compatible fallback) ─────────────────────────────────
FONT_DIR_WIN = "C:/Windows/Fonts"
FONT_DIR_LINUX = "/usr/share/fonts/truetype/dejavu"

def _find_font(bold=False):
    """Find best available font, fallback to PIL default."""
    candidates_bold = [
        os.path.join(FONT_DIR_WIN, "arialbd.ttf"),
        os.path.join(FONT_DIR_WIN, "Arial Bold.ttf"),
        os.path.join(FONT_DIR_WIN, "calibrib.ttf"),
        os.path.join(FONT_DIR_LINUX, "DejaVuSans-Bold.ttf"),
    ]
    candidates_reg = [
        os.path.join(FONT_DIR_WIN, "arial.ttf"),
        os.path.join(FONT_DIR_WIN, "Arial.ttf"),
        os.path.join(FONT_DIR_WIN, "calibri.ttf"),
        os.path.join(FONT_DIR_LINUX, "DejaVuSans.ttf"),
    ]
    candidates = candidates_bold if bold else candidates_reg
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

FONT_BOLD_PATH = _find_font(bold=True)
FONT_REG_PATH = _find_font(bold=False)

def _font(size, bold=False):
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    return ImageFont.load_default()

# ─── Canvas & Color Palette ───────────────────────────────────────────────────
CW = 1080  # Canvas Width
CH = 2200  # Canvas Height

# Dark background colors
BG_DARK = (8, 10, 24)
BG_MID  = (12, 16, 36)

# Neon accent colors
NEON_GREEN  = (0, 255, 128)
NEON_RED    = (255, 50, 100)
NEON_BLUE   = (60, 140, 255)
NEON_PURPLE = (180, 60, 255)
NEON_GOLD   = (255, 200, 60)
NEON_CYAN   = (0, 220, 255)

SILVER = (200, 210, 220)
WHITE  = (255, 255, 255)
CARD_BG = (16, 20, 44)
CARD_BG2 = (20, 14, 40)


# ─── Core Drawing Helpers ─────────────────────────────────────────────────────

def _gradient_bg(w, h, top_color, bottom_color):
    """Creates a smooth vertical gradient background."""
    img = Image.new("RGBA", (w, h), top_color + (255,))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return img


def _draw_colorful_bokeh(canvas, count=18):
    """Draws soft glowing circles for a beautiful bokeh/neon background effect."""
    import random
    w, h = canvas.size
    colors = [
        (60, 255, 140, 30),   # green
        (255, 60, 120, 30),   # pink
        (60, 120, 255, 30),   # blue
        (255, 200, 60, 25),   # gold
        (180, 60, 255, 25),   # purple
        (0, 220, 255, 25),    # cyan
    ]
    # Use fixed seed for consistent look
    rng = random.Random(42)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for _ in range(count):
        cx = rng.randint(0, w)
        cy = rng.randint(0, h)
        r = rng.randint(120, 400)
        color = rng.choice(colors)
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        gdraw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        glow = glow.filter(ImageFilter.GaussianBlur(r // 3))
        layer = Image.alpha_composite(layer, glow)
    canvas.alpha_composite(layer)


def _draw_grid_lines(canvas, color=(60, 255, 140, 10), step=80):
    """Draws subtle tech grid lines over the canvas."""
    w, h = canvas.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    for x in range(0, w, step):
        ldraw.line([(x, 0), (x, h)], fill=color, width=1)
    for y in range(0, h, step):
        ldraw.line([(0, y), (w, y)], fill=color, width=1)
    canvas.alpha_composite(layer)


def _glow_ellipse(canvas, cx, cy, rx, ry, color, alpha_max=120, blur=40):
    """Draws a soft glowing ellipse."""
    w, h = canvas.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ldraw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color + (alpha_max,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


def _neon_border_card(canvas, box, radius, fill, border_color, border_width=3, glow_blur=12, glow_alpha=180):
    """Draws a card with a glowing neon border — the signature premium 3D look."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = canvas.size

    # 1. Outer glow
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)
    gdraw.rounded_rectangle((x0, y0, x1, y1), radius=radius,
                             outline=border_color + (glow_alpha,), width=border_width + 4)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_blur))
    canvas.alpha_composite(glow_layer)

    # 2. Card fill
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill + (230,))

    # 3. Crisp border
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius,
                            outline=border_color, width=border_width)

    # 4. Glass shine strip on top
    shine = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shine_draw = ImageDraw.Draw(shine)
    shine_h = (y1 - y0) // 3
    shine_draw.polygon([
        (x0 + radius, y0),
        (x1 - radius, y0),
        (x1 - radius, y0 + shine_h),
        (x0 + radius, y0 + shine_h // 2),
    ], fill=(255, 255, 255, 22))
    canvas.alpha_composite(shine)


def _glow_text(canvas, xy, text, size, bold=True, fill=WHITE, glow_color=NEON_GREEN, glow_r=10, anchor="la"):
    """Draws text with a beautiful neon glow behind it."""
    font = _font(size, bold=bold)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text(xy, text, font=font, fill=glow_color + (200,), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(glow_r))
    canvas.alpha_composite(layer)
    d2 = ImageDraw.Draw(canvas)
    d2.text(xy, text, font=font, fill=fill, anchor=anchor)


def _color_badge(canvas, box, radius, bg_color, border_color, text, text_size=28, text_color=WHITE):
    """Draws a colorful 3D glossy pill/badge with text."""
    _neon_border_card(canvas, box, radius, bg_color, border_color, border_width=2, glow_blur=8, glow_alpha=150)
    draw = ImageDraw.Draw(canvas)
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    draw.text((cx, cy), text, font=_font(text_size, bold=True), fill=text_color, anchor="mm")


def _confidence_bar(canvas, x0, y, bar_w, bar_h, confidence, accent_color):
    """Draws a premium animated-style confidence bar with glow."""
    draw = ImageDraw.Draw(canvas)
    # Track background
    draw.rounded_rectangle((x0, y, x0 + bar_w, y + bar_h), radius=bar_h // 2,
                            fill=(30, 35, 60, 200))
    # Fill amount
    fill_w = max(bar_h, int(bar_w * confidence / 100))
    draw.rounded_rectangle((x0, y, x0 + fill_w, y + bar_h), radius=bar_h // 2,
                            fill=accent_color)
    # Shine on fill
    if fill_w > 20:
        draw.line([(x0 + 10, y + bar_h // 3), (x0 + fill_w - 10, y + bar_h // 3)],
                  fill=(255, 255, 255, 100), width=2)
    # Glow on edges
    glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)
    gdraw.rounded_rectangle((x0, y, x0 + fill_w, y + bar_h), radius=bar_h // 2,
                             outline=accent_color + (180,), width=3)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(5))
    canvas.alpha_composite(glow_layer)


def _paste_chart(canvas, chart_path, box, border_color):
    """Pastes chart with rounded clip and neon border."""
    try:
        chart = Image.open(chart_path).convert("RGB")
    except Exception:
        return

    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = x1 - x0, y1 - y0

    # Fit & crop
    cr = chart.width / chart.height
    br = bw / bh
    if cr > br:
        nh, nw = bh, int(bh * cr)
    else:
        nw, nh = bw, int(bw / cr)
    chart = chart.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - bw) // 2, (nh - bh) // 2
    chart = chart.crop((left, top, left + bw, top + bh))

    # Rounded mask
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw, bh), radius=22, fill=255)
    canvas.paste(chart, (x0, y0), mask)

    # Neon border around chart
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.rounded_rectangle((x0, y0, x1, y1), radius=22, outline=border_color + (160,), width=4)
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    canvas.alpha_composite(glow)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, outline=border_color, width=2)


# ─── Main Signal Card ─────────────────────────────────────────────────────────

def render_result_card(
    chart_image_path,
    prediction,
    pair_name="Chart Analysis",
    timeframe_label="1 MIN",
    trade_duration_label=None,
    utc_offset_hours=5,
    logo_path=None,
    output_path="/tmp/mi_nexus_result.png",
    candles=None,
):
    """Renders a premium 3D colorful signal card image."""
    canvas = _gradient_bg(CW, CH, BG_DARK, BG_MID)
    canvas = canvas.convert("RGBA")

    direction   = prediction.get("direction", "UP")
    confidence  = prediction.get("confidence", 70)
    strength    = prediction.get("strength", "MODERATE")
    is_up       = direction == "UP"
    accent      = NEON_GREEN if is_up else NEON_RED
    accent2     = NEON_CYAN  if is_up else NEON_PURPLE

    # ── 1. Colorful Bokeh Background ──────────────────────────────────────────
    _draw_colorful_bokeh(canvas, count=16)
    _draw_grid_lines(canvas, color=(100, 140, 255, 8))

    # ── 2. Header Band ────────────────────────────────────────────────────────
    header_h = 230
    header_layer = Image.new("RGBA", (CW, header_h), (0, 0, 0, 0))
    hl_draw = ImageDraw.Draw(header_layer)
    for y in range(header_h):
        t = y / max(1, header_h - 1)
        a = int(200 * (1 - t))
        hl_draw.line([(0, y), (CW, y)], fill=(10, 14, 40, a))
    canvas.alpha_composite(header_layer)

    # Logo
    logo_size = 160
    logo_x, logo_y = 34, 30
    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        _glow_ellipse(canvas, logo_x + logo_size // 2, logo_y + logo_size // 2,
                      logo_size // 2 + 30, logo_size // 2 + 30, NEON_GREEN, alpha_max=60, blur=30)
        canvas.alpha_composite(logo, (logo_x, logo_y))

    # Wordmark
    tx = logo_x + logo_size + 24
    _glow_text(canvas, (tx, logo_y + 10), "MI NEXUS", 82, bold=True,
               fill=WHITE, glow_color=accent, glow_r=14, anchor="la")
    draw = ImageDraw.Draw(canvas)
    draw.text((tx + 4, logo_y + 106), "PRO v20  ★  ANALYZE · PREDICT · PROFIT",
              font=_font(26), fill=accent2, anchor="la")

    # Pair name pill
    y_cursor = header_h + 10
    _color_badge(canvas, (CW // 2 - 280, y_cursor, CW // 2 + 280, y_cursor + 60),
                 radius=30, bg_color=CARD_BG, border_color=accent,
                 text=f"★  {pair_name.upper()}  ★", text_size=34, text_color=WHITE)
    y_cursor += 78

    # ── 3. Direction Hero Card ────────────────────────────────────────────────
    dir_card_box = (30, y_cursor, CW - 30, y_cursor + 140)
    dir_bg = (10, 40, 20) if is_up else (40, 10, 20)
    _neon_border_card(canvas, dir_card_box, 36, dir_bg, accent,
                      border_width=4, glow_blur=20, glow_alpha=220)

    arrow_txt  = "▲  CALL / BUY  — PRICE GOING UP ▲" if is_up else "▼  PUT / SELL  — PRICE GOING DOWN ▼"
    _glow_text(canvas, (CW // 2, y_cursor + 70), arrow_txt, 48, bold=True,
               fill=WHITE, glow_color=accent, glow_r=12, anchor="mm")
    y_cursor += 158

    # Confidence Bar
    draw = ImageDraw.Draw(canvas)
    draw.text((CW // 2, y_cursor + 8), f"CONFIDENCE: {confidence}%",
              font=_font(30, bold=True), fill=accent, anchor="ma")
    y_cursor += 40
    _confidence_bar(canvas, 60, y_cursor, CW - 120, 36, confidence, accent)
    y_cursor += 56

    # Strength badge
    str_colors = {
        "VERY STRONG": (NEON_GOLD,    (50, 40, 0)),
        "STRONG":      (NEON_GREEN,   (0, 40, 20)),
        "MODERATE":    (NEON_CYAN,    (0, 30, 40)),
        "WEAK":        (NEON_PURPLE,  (30, 0, 40)),
    }
    s_border, s_bg = str_colors.get(strength, (SILVER, CARD_BG))
    _color_badge(canvas, (CW // 2 - 200, y_cursor, CW // 2 + 200, y_cursor + 52),
                 radius=26, bg_color=s_bg, border_color=s_border,
                 text=f"⚡ SIGNAL STRENGTH: {strength}", text_size=28, text_color=WHITE)
    y_cursor += 70

    # ── 4. Chart Window ───────────────────────────────────────────────────────
    chart_box = (30, y_cursor, CW - 30, y_cursor + 820)
    _paste_chart(canvas, chart_image_path, chart_box, accent)

    # Direction badge overlay on chart
    dir_badge_box = (CW - 340, y_cursor + 20, CW - 40, y_cursor + 100)
    _color_badge(canvas, dir_badge_box, 20,
                 bg_color=(10, 40, 20) if is_up else (40, 10, 20),
                 border_color=accent,
                 text="▲ UP" if is_up else "▼ DOWN", text_size=36, text_color=WHITE)

    y_cursor += 838

    # ── 5. Technical Details Card ─────────────────────────────────────────────
    tech      = prediction.get("technical_indicators", {})
    choppiness = prediction.get("choppiness", 0)
    bias_val  = prediction.get("trend_bias", 0)

    if choppiness < 0.3:
        cond_label, cond_color = "✅ CLEAN TREND", NEON_GREEN
    elif choppiness < 0.6:
        cond_label, cond_color = "⚠️ MIXED MARKET", NEON_GOLD
    else:
        cond_label, cond_color = "❌ CHOPPY", NEON_RED

    bias_label = "BULLISH 🐂" if bias_val > 0.05 else ("BEARISH 🐻" if bias_val < -0.05 else "FLAT ↔")
    bias_color = NEON_GREEN if bias_val > 0.05 else (NEON_RED if bias_val < -0.05 else SILVER)

    tz = timezone(timedelta(hours=utc_offset_hours))
    time_str = datetime.now(tz).strftime("%H:%M:%S")

    detail_card_box = (30, y_cursor, CW - 30, y_cursor + 320)
    _neon_border_card(canvas, detail_card_box, 28, CARD_BG2, NEON_BLUE,
                      border_width=2, glow_blur=10, glow_alpha=120)
    draw = ImageDraw.Draw(canvas)

    dx, dy = 60, y_cursor + 22
    lbl_f = _font(26)
    val_f = _font(28, bold=True)

    # Row helper
    def row(label, value, value_color=WHITE):
        nonlocal dy
        draw.text((dx, dy), label, font=lbl_f, fill=SILVER, anchor="la")
        draw.text((CW // 2, dy), value, font=val_f, fill=value_color, anchor="la")
        dy += 46

    row("⏱ Timeframe:", timeframe_label)
    if trade_duration_label:
        row("⏳ Trade Duration:", trade_duration_label, NEON_GOLD)
    row(f"🕐 Signal Time (UTC{'+' if utc_offset_hours >= 0 else ''}{utc_offset_hours}):", time_str)
    row("📈 Market Condition:", cond_label, cond_color)
    row("📊 Trend Bias:", bias_label, bias_color)

    # RSI
    rsi_val = tech.get("calculated_rsi")
    if rsi_val is not None:
        rsi_zone = "OVERBOUGHT 🔴" if rsi_val >= 70 else ("OVERSOLD 🟢" if rsi_val <= 30 else "NEUTRAL ⚪")
        rsi_color = NEON_RED if rsi_val >= 70 else (NEON_GREEN if rsi_val <= 30 else SILVER)
        row(f"📉 RSI ({rsi_val:.0f}):", rsi_zone, rsi_color)

    y_cursor += 338

    # ── 6. Patterns Card ──────────────────────────────────────────────────────
    breakdown = prediction.get("breakdown", [])
    top_patterns = sorted(breakdown, key=lambda p: p["reliability"], reverse=True)[:6]

    if top_patterns:
        pat_card_h = 50 + len(top_patterns) * 52
        pat_card_box = (30, y_cursor, CW - 30, y_cursor + pat_card_h)
        _neon_border_card(canvas, pat_card_box, 24, CARD_BG, NEON_PURPLE,
                          border_width=2, glow_blur=8)
        draw = ImageDraw.Draw(canvas)
        draw.text((CW // 2, y_cursor + 26), "🕯️  PATTERNS DETECTED",
                  font=_font(28, bold=True), fill=NEON_PURPLE, anchor="ma")

        py = y_cursor + 62
        pcol_w = (CW - 90) // 2
        for i, p in enumerate(top_patterns):
            col = i % 2
            px = 60 + col * (pcol_w + 30)
            sig = "▲" if p["signal"] == "bullish" else ("▼" if p["signal"] == "bearish" else "●")
            sc = NEON_GREEN if p["signal"] == "bullish" else (NEON_RED if p["signal"] == "bearish" else SILVER)
            name = p["name"][:24]
            draw.text((px, py if col == 0 else py), f"{sig} {name}  ({int(p['reliability'])}%)",
                      font=_font(24), fill=sc, anchor="la")
            if col == 1:
                py += 52
        y_cursor += pat_card_h + 20

    # ── 7. AI Block ───────────────────────────────────────────────────────────
    ai_result = prediction.get("ai_result")
    if ai_result and "error" not in ai_result:
        ai_dir  = ai_result.get("direction", "?")
        ai_conf = ai_result.get("confidence", 0)
        ai_agrees = prediction.get("ai_agrees")
        ai_reasoning = prediction.get("ai_reasoning", ai_result.get("reasoning", ""))[:110]

        agree_txt = "✅ AGREES" if ai_agrees else "⚠️ DIFFERS"
        ai_card_box = (30, y_cursor, CW - 30, y_cursor + 180)
        _neon_border_card(canvas, ai_card_box, 22, CARD_BG2, NEON_CYAN,
                          border_width=2, glow_blur=8)
        draw = ImageDraw.Draw(canvas)
        draw.text((60, y_cursor + 22), "🤖 GROQ AI DEEP ANALYSIS",
                  font=_font(28, bold=True), fill=NEON_CYAN, anchor="la")
        draw.text((60, y_cursor + 72), f"Direction: {ai_dir} ({ai_conf:.0f}%) — {agree_txt}",
                  font=_font(28, bold=True), fill=WHITE, anchor="la")
        if ai_reasoning:
            draw.text((60, y_cursor + 118), f'"{ai_reasoning}..."',
                      font=_font(22), fill=SILVER, anchor="la")
        y_cursor += 198

    # ── 8. Tip Box ────────────────────────────────────────────────────────────
    if confidence >= 85:
        tip = "STRONG SIGNAL — Confirm entry before placing trade."
    elif choppiness >= 0.6:
        tip = "CHOPPY MARKET — Wait for a clearer pattern."
    else:
        tip = "Wait for price confirmation before entering your trade."

    tip_box = (30, y_cursor, CW - 30, y_cursor + 72)
    _neon_border_card(canvas, tip_box, 22, (20, 18, 10), NEON_GOLD, border_width=2, glow_blur=6)
    draw = ImageDraw.Draw(canvas)
    draw.text((CW // 2, y_cursor + 36), f"💡 TIP: {tip}",
              font=_font(26), fill=NEON_GOLD, anchor="mm")
    y_cursor += 90

    # ── 9. Footer ─────────────────────────────────────────────────────────────
    draw = ImageDraw.Draw(canvas)
    draw.text((CW // 2, y_cursor + 28), "⚠ Educational analysis only — not financial advice",
              font=_font(24), fill=(150, 155, 165), anchor="ma")
    draw.text((CW // 2, y_cursor + 60), "MI NEXUS © Muslim Islam Network",
              font=_font(26, bold=True), fill=NEON_GREEN, anchor="ma")

    final_h = y_cursor + 100
    # Crop or extend to final height
    if final_h < CH:
        canvas = canvas.crop((0, 0, CW, final_h))
    else:
        extended = Image.new("RGBA", (CW, final_h), BG_DARK + (255,))
        extended.paste(canvas, (0, 0))
        canvas = extended

    canvas.convert("RGB").save(output_path, quality=95)
    return output_path


# ─── Menu Banner ──────────────────────────────────────────────────────────────

def render_menu_banner(output_path="/tmp/mi_nexus_menu.png"):
    """
    Generates a stunning, colorful 3D banner image for the main menu.
    Full of neon glows, colorful bokeh, and premium text.
    """
    W, H = 1080, 600
    canvas = _gradient_bg(W, H, (5, 8, 25), (10, 6, 35))
    canvas = canvas.convert("RGBA")

    # Background bokeh
    _draw_colorful_bokeh(canvas, count=20)
    _draw_grid_lines(canvas, color=(80, 120, 255, 10))

    # Big glow orbs
    _glow_ellipse(canvas, W // 2, H // 2, 420, 260, (0, 140, 255), alpha_max=40, blur=80)
    _glow_ellipse(canvas, 100, 80, 200, 160, (0, 255, 128), alpha_max=35, blur=60)
    _glow_ellipse(canvas, W - 100, H - 80, 200, 160, (255, 60, 120), alpha_max=35, blur=60)

    # Bottom colorful gradient bar
    bar_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(bar_layer)
    bar_colors = [(255, 60, 120), (180, 60, 255), (60, 120, 255), (0, 220, 255), (0, 255, 128), (255, 200, 60)]
    seg_w = W // len(bar_colors)
    for i, c in enumerate(bar_colors):
        bdraw.rectangle((i * seg_w, H - 10, (i + 1) * seg_w, H), fill=c + (200,))
    bar_layer = bar_layer.filter(ImageFilter.GaussianBlur(2))
    canvas.alpha_composite(bar_layer)

    # Main Title
    _glow_text(canvas, (W // 2, H // 2 - 120), "MI NEXUS PRO", 100, bold=True,
               fill=WHITE, glow_color=NEON_GREEN, glow_r=20, anchor="mm")

    # Version badge
    _color_badge(canvas, (W // 2 - 130, H // 2 - 50, W // 2 + 130, H // 2 + 10),
                 radius=28, bg_color=CARD_BG, border_color=NEON_CYAN,
                 text="VERSION 20", text_size=30, text_color=NEON_CYAN)

    # Tagline
    _glow_text(canvas, (W // 2, H // 2 + 65), "🏆  THE ULTIMATE TRADING AI BOT  🏆", 34, bold=False,
               fill=(220, 230, 255), glow_color=NEON_PURPLE, glow_r=10, anchor="mm")

    # Bottom stats row (colored badges)
    badges = [
        ("100+ PATTERNS", NEON_GREEN),
        ("AI POWERED", NEON_CYAN),
        ("GROQ VISION", NEON_PURPLE),
        ("LIVE SIGNALS", NEON_GOLD),
    ]
    total_badge_w = len(badges) * 240 + (len(badges) - 1) * 16
    bx_start = (W - total_badge_w) // 2
    by = H // 2 + 120
    for label, color in badges:
        _color_badge(canvas, (bx_start, by, bx_start + 230, by + 52),
                     radius=26, bg_color=CARD_BG2, border_color=color,
                     text=label, text_size=24, text_color=color)
        bx_start += 246

    canvas.convert("RGB").save(output_path, quality=95)
    return output_path


# ─── WIN / LOSS Result Stamp ──────────────────────────────────────────────────

def render_result_stamp(image_path, result_type):
    """
    Overlays a beautiful colorful WIN / LOSS stamp on an existing signal card.
    result_type: 'win' or 'loss'
    """
    try:
        img = Image.open(image_path).convert("RGBA")
    except Exception:
        return image_path

    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    if result_type.lower() == "win":
        color      = NEON_GREEN
        bg_tint    = (10, 60, 20, 120)
        stamp_text = "✅  TRADE WIN!"
        emoji_text = "🏆🎉🎊"
    else:
        color      = NEON_RED
        bg_tint    = (60, 10, 20, 120)
        stamp_text = "❌  TRADE LOST"
        emoji_text = "💪📉⚠️"

    # Semi-transparent color tint over entire image
    draw.rectangle((0, 0, w, h), fill=bg_tint)

    # Main stamp box — centered, rotated
    font_big = _font(min(w // 8, 120), bold=True)
    font_sub = _font(min(w // 14, 60), bold=False)

    txt_w_approx = w * 0.75
    box_h = h // 6
    cx, cy = w // 2, h // 2

    # Outer glow
    glow_rect = (cx - txt_w_approx // 2 - 50, cy - box_h // 2 - 30,
                 cx + txt_w_approx // 2 + 50, cy + box_h // 2 + 30)
    for grow in range(20, 0, -1):
        a = int(200 * (1 - grow / 20) ** 2)
        draw.rounded_rectangle(
            (glow_rect[0] - grow, glow_rect[1] - grow,
             glow_rect[2] + grow, glow_rect[3] + grow),
            radius=36, outline=color + (a,), width=1
        )

    # Stamp box fill
    draw.rounded_rectangle(glow_rect, radius=36, fill=(10, 14, 30, 220))
    draw.rounded_rectangle(glow_rect, radius=36, outline=color, width=8)

    # Stamp text
    draw.text((cx, cy - 20), stamp_text, font=font_big, fill=color, anchor="mm")
    draw.text((cx, cy + box_h // 2 + 10), emoji_text, font=font_sub,
              fill=WHITE, anchor="mm")

    # Rotate the stamp slightly
    layer = layer.rotate(-12, resample=Image.BICUBIC, center=(cx, cy))

    img.alpha_composite(layer)

    out_path = image_path.replace(".png", f"_stamped_{result_type}.png")
    if out_path == image_path:
        out_path = image_path + f"_stamped_{result_type}.png"
    img.convert("RGB").save(out_path, quality=95)
    return out_path
