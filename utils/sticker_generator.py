"""
MI NEXUS - Signal Sticker Generator
Creates branded UP/DOWN sticker images (WEBP, 512x512, transparent background)
sent alongside signals in groups for a premium visual alert.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

STICKER_SIZE = 512

NEON_GREEN = (57, 255, 20)
NEON_RED = (255, 60, 60)
WHITE = (255, 255, 255)


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


def generate_direction_sticker(direction, confidence=None, output_path=None):
    """
    direction: "UP" or "DOWN"
    Returns path to a 512x512 transparent WEBP sticker.
    """
    is_up = direction.upper() == "UP"
    accent = NEON_GREEN if is_up else NEON_RED
    arrow = "▲" if is_up else "▼"

    img = Image.new("RGBA", (STICKER_SIZE, STICKER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = STICKER_SIZE // 2
    radius = 200

    # Outer glow ring
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=accent, width=18
    )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(glow_layer)

    # Solid ring
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=accent, width=10
    )
    # Dark fill circle
    inner_r = radius - 14
    draw.ellipse(
        (center - inner_r, center - inner_r, center + inner_r, center + inner_r),
        fill=(10, 16, 14, 235)
    )

    # Big arrow
    arrow_font = _font(190)
    _glow_text(img, (center, center - 40), arrow, arrow_font, fill=WHITE,
               glow_color=accent, glow_radius=16, anchor="mm")

    # Direction text
    label_font = _font(64)
    _glow_text(img, (center, center + 110), direction.upper(), label_font, fill=WHITE,
               glow_color=accent, glow_radius=8, anchor="mm")

    # Confidence (optional)
    if confidence is not None:
        conf_font = _font(34)
        draw.text((center, center + 170), f"{confidence}%", font=conf_font, fill=accent, anchor="mm")

    # Brand tag
    brand_font = _font(26)
    draw.text((center, STICKER_SIZE - 30), "MI NEXUS", font=brand_font, fill=(200, 200, 200, 220), anchor="mm")

    if output_path is None:
        output_path = f"/tmp/mi_nexus_sticker_{direction.lower()}.webp"
    img.save(output_path, "WEBP")
    return output_path
