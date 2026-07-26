"""
MI NEXUS - Signal Sticker Provider (VIP Edition)
Prefers YOUR OWN custom sticker files (drop them in assets/stickers/) and
only falls back to an auto-generated VIP-style sticker if a custom one
isn't provided for that slot.
"""

import os
import shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

STICKER_SIZE = 512

NEON_GREEN = (57, 255, 20)
NEON_RED = (255, 60, 60)
GOLD = (255, 208, 80)
WHITE = (255, 255, 255)

STICKERS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "stickers")

# Drop your own files with these exact names in assets/stickers/ to use them
# instead of the auto-generated ones. Supported: .webp (preferred), .png, .jpg
CUSTOM_STICKER_SLOTS = {
    "up": "up",
    "down": "down",
    "session": "session_start",
    "win": "win",
    "loss": "loss",
}


def _find_custom_sticker(slot_name):
    """Looks for a user-provided sticker file for the given slot name."""
    if not os.path.isdir(STICKERS_DIR):
        return None
    base_name = CUSTOM_STICKER_SLOTS.get(slot_name, slot_name)
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(STICKERS_DIR, base_name + ext)
        if os.path.exists(candidate):
            return candidate
    return None


def _use_custom_or_generate(slot_name, generator_fn, output_path):
    """
    Core logic: if the user dropped their own sticker file for this slot,
    convert/copy it to the requested output_path. Otherwise call the
    auto-generate fallback function.
    """
    custom_path = _find_custom_sticker(slot_name)
    if custom_path:
        try:
            if custom_path.lower().endswith(".webp"):
                shutil.copy(custom_path, output_path)
            else:
                # Convert PNG/JPG to WEBP so Telegram accepts it as a sticker
                img = Image.open(custom_path).convert("RGBA")
                img.save(output_path, "WEBP")
            return output_path
        except Exception:
            pass  # fall through to auto-generate if the custom file is broken
    return generator_fn()


def _font(size):
    try:
        return ImageFont.truetype(FONT_BOLD, size)
    except Exception:
        return ImageFont.load_default()


def _glow_text(img, xy, text, font, fill, glow_color, glow_radius=14, anchor="mm"):
    txt_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(txt_layer)
    d.text(xy, text, font=font, fill=glow_color, anchor=anchor)
    txt_layer = txt_layer.filter(ImageFilter.GaussianBlur(glow_radius))
    img.alpha_composite(txt_layer)
    d2 = ImageDraw.Draw(img)
    d2.text(xy, text, font=font, fill=fill, anchor=anchor)


def _vip_ring_base(accent, logo_path=None):
    """Builds the shared VIP ring + logo badge background used by all stickers."""
    img = Image.new("RGBA", (STICKER_SIZE, STICKER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = STICKER_SIZE // 2
    radius = 220

    # Outer gold VIP ring (glow)
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse((center - radius, center - radius, center + radius, center + radius),
               outline=GOLD, width=10)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(glow_layer)

    # Accent glow ring (inner, direction-colored)
    accent_glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ad = ImageDraw.Draw(accent_glow)
    ad.ellipse((center - radius + 16, center - radius + 16, center + radius - 16, center + radius - 16),
               outline=accent, width=14)
    accent_glow = accent_glow.filter(ImageFilter.GaussianBlur(12))
    img.alpha_composite(accent_glow)

    # Solid rings
    draw.ellipse((center - radius, center - radius, center + radius, center + radius),
                 outline=GOLD, width=6)
    draw.ellipse((center - radius + 16, center - radius + 16, center + radius - 16, center + radius - 16),
                 outline=accent, width=8)

    # Dark fill circle
    inner_r = radius - 26
    draw.ellipse((center - inner_r, center - inner_r, center + inner_r, center + inner_r),
                 fill=(8, 12, 11, 240))

    # VIP tag top
    vip_font = _font(30)
    draw.text((center, center - radius + 46), "★ VIP ★", font=vip_font, fill=GOLD, anchor="mm")

    return img, draw, center


def _generate_direction_sticker_fallback(direction, confidence, output_path):
    """Auto-generated fallback (used only if you haven't provided your own sticker)."""
    is_up = direction.upper() == "UP"
    accent = NEON_GREEN if is_up else NEON_RED
    arrow = "▲" if is_up else "▼"

    img, draw, center = _vip_ring_base(accent)

    arrow_font = _font(150)
    _glow_text(img, (center, center - 30), arrow, arrow_font, fill=WHITE,
               glow_color=accent, glow_radius=16, anchor="mm")

    label_font = _font(58)
    _glow_text(img, (center, center + 95), direction.upper(), label_font, fill=WHITE,
               glow_color=accent, glow_radius=8, anchor="mm")

    if confidence is not None:
        conf_font = _font(30)
        draw.text((center, center + 150), f"{confidence}% Confidence", font=conf_font, fill=accent, anchor="mm")

    brand_font = _font(24)
    draw.text((center, STICKER_SIZE - 34), "MI NEXUS", font=brand_font, fill=(220, 220, 220, 230), anchor="mm")

    img.save(output_path, "WEBP")
    return output_path


def generate_direction_sticker(direction, confidence=None, output_path=None, logo_path=None):
    """
    direction: "UP" or "DOWN"
    Uses YOUR custom sticker (assets/stickers/up.webp or down.webp) if present,
    otherwise auto-generates a VIP-style fallback.
    """
    if output_path is None:
        output_path = f"/tmp/mi_nexus_sticker_{direction.lower()}.webp"

    slot = "up" if direction.upper() == "UP" else "down"
    return _use_custom_or_generate(
        slot,
        lambda: _generate_direction_sticker_fallback(direction, confidence, output_path),
        output_path,
    )


def _generate_session_start_sticker_fallback(pair_name, timeframe, output_path):
    accent = GOLD
    img, draw, center = _vip_ring_base(accent)

    icon_font = _font(120)
    _glow_text(img, (center, center - 50), "●", icon_font, fill=WHITE,
               glow_color=accent, glow_radius=14, anchor="mm")

    label_font = _font(46)
    _glow_text(img, (center, center + 60), "SESSION", label_font, fill=WHITE,
               glow_color=accent, glow_radius=8, anchor="mm")
    label_font2 = _font(40)
    draw.text((center, center + 110), "STARTED", font=label_font2, fill=GOLD, anchor="mm")

    if pair_name:
        small_font = _font(26)
        draw.text((center, center + 155), pair_name, font=small_font, fill=(230, 230, 230), anchor="mm")

    brand_font = _font(24)
    draw.text((center, STICKER_SIZE - 34), "MI NEXUS", font=brand_font, fill=(220, 220, 220, 230), anchor="mm")

    img.save(output_path, "WEBP")
    return output_path


def generate_session_start_sticker(pair_name=None, timeframe=None, output_path=None):
    """
    Uses YOUR custom sticker (assets/stickers/session_start.webp) if present,
    otherwise auto-generates a VIP 'Session Started' fallback.
    """
    if output_path is None:
        output_path = "/tmp/mi_nexus_sticker_session.webp"

    return _use_custom_or_generate(
        "session",
        lambda: _generate_session_start_sticker_fallback(pair_name, timeframe, output_path),
        output_path,
    )


def _generate_result_sticker_fallback(is_win, output_path):
    accent = NEON_GREEN if is_win else NEON_RED
    img, draw, center = _vip_ring_base(accent)

    symbol = "✔" if is_win else "✘"
    icon_font = _font(150)
    _glow_text(img, (center, center - 30), symbol, icon_font, fill=WHITE,
               glow_color=accent, glow_radius=16, anchor="mm")

    label_font = _font(58)
    text = "WIN" if is_win else "LOSS"
    _glow_text(img, (center, center + 100), text, label_font, fill=WHITE,
               glow_color=accent, glow_radius=8, anchor="mm")

    sub_font = _font(28)
    sub_text = "Great Trade!" if is_win else "Next One's Ours"
    draw.text((center, center + 155), sub_text, font=sub_font, fill=accent, anchor="mm")

    brand_font = _font(24)
    draw.text((center, STICKER_SIZE - 34), "MI NEXUS", font=brand_font, fill=(220, 220, 220, 230), anchor="mm")

    img.save(output_path, "WEBP")
    return output_path


def generate_result_sticker(is_win, output_path=None):
    """
    Uses YOUR custom sticker (assets/stickers/win.webp or loss.webp) if present,
    otherwise auto-generates a VIP WIN/LOSS fallback.
    """
    if output_path is None:
        output_path = f"/tmp/mi_nexus_sticker_{'win' if is_win else 'loss'}.webp"

    slot = "win" if is_win else "loss"
    return _use_custom_or_generate(
        slot,
        lambda: _generate_result_sticker_fallback(is_win, output_path),
        output_path,
    )
