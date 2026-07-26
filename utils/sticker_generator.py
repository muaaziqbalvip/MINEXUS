"""
MI NEXUS - Sticker Provider
Uses ONLY your own custom sticker files. Drop them into assets/stickers/
with the exact filenames below. No auto-generation — if a file is missing,
the bot simply skips sending a sticker for that slot (signal image/text
still goes out normally).
"""

import os
import shutil
from PIL import Image

STICKERS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "stickers")

# Exact filenames to drop into assets/stickers/
STICKER_FILES = {
    "up": "up",
    "down": "down",
    "session": "session_start",
    "win": "win",
    "loss": "loss",
}


def _find_sticker_file(slot_name):
    if not os.path.isdir(STICKERS_DIR):
        return None
    base_name = STICKER_FILES.get(slot_name, slot_name)
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(STICKERS_DIR, base_name + ext)
        if os.path.exists(candidate):
            return candidate
    return None


def get_sticker(slot_name, output_path=None):
    """
    Returns the path to a ready-to-send WEBP sticker for the given slot
    ("up", "down", "session", "win", "loss"), or None if you haven't
    provided a file for that slot yet.
    """
    source_path = _find_sticker_file(slot_name)
    if not source_path:
        return None

    if output_path is None:
        output_path = f"/tmp/mi_nexus_sticker_{slot_name}.webp"

    try:
        if source_path.lower().endswith(".webp"):
            shutil.copy(source_path, output_path)
        else:
            img = Image.open(source_path).convert("RGBA")
            img.save(output_path, "WEBP")
        return output_path
    except Exception:
        return None


def get_direction_sticker(direction, output_path=None):
    slot = "up" if direction.upper() == "UP" else "down"
    return get_sticker(slot, output_path)


def get_session_start_sticker(output_path=None):
    return get_sticker("session", output_path)


def get_result_sticker(is_win, output_path=None):
    slot = "win" if is_win else "loss"
    return get_sticker(slot, output_path)


def list_missing_stickers():
    """Returns a list of slot names that don't have a sticker file yet."""
    missing = []
    for slot in STICKER_FILES:
        if not _find_sticker_file(slot):
            missing.append(slot)
    return missing
