"""
MI NEXUS - Pair/Asset Detector
Uses OCR (Tesseract) to read the pair/asset name typically shown at the
top-left or top-center of broker chart screenshots (e.g. "EUR/USD OTC").
Pure local processing - no external API.
"""

import re
import cv2
import pytesseract

# Common currency/asset tokens to help validate OCR guesses
KNOWN_TOKENS = [
    "EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY",
    "BTC", "ETH", "XRP", "LTC", "BNB", "SOL", "DOGE",
    "XAU", "XAG", "OIL", "GOLD", "SILVER",
    "OTC", "INDEX", "STOCK"
]

PAIR_REGEX = re.compile(
    r"\b([A-Z]{3,4})\s*[/\-]\s*([A-Z]{3,4})\b", re.IGNORECASE
)
OTC_REGEX = re.compile(r"\bOTC\b", re.IGNORECASE)


def _preprocess_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def detect_pair_name(image_path):
    """
    Scans the top region of the screenshot (where broker platforms usually
    show the asset/pair name) and tries to OCR + pattern-match a pair name.
    Returns a string like "EUR/USD OTC" or None if not confidently detected.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None

    h, w = img.shape[:2]

    # Try a few likely regions: top-left, top-center strip
    regions = [
        img[0:int(h * 0.08), 0:int(w * 0.45)],       # top-left
        img[0:int(h * 0.10), int(w * 0.15):int(w * 0.85)],  # top-center wide
    ]

    best_match = None
    for region in regions:
        if region.size == 0:
            continue
        try:
            processed = _preprocess_for_ocr(region)
            text = pytesseract.image_to_string(processed, config="--psm 7")
        except Exception:
            continue

        text = text.strip().upper()
        if not text:
            continue

        match = PAIR_REGEX.search(text)
        if match:
            base, quote = match.group(1), match.group(2)
            if base.upper() != "OTC" and quote.upper() != "OTC" and (base in KNOWN_TOKENS or quote in KNOWN_TOKENS or len(base) in (3, 4)):
                pair_str = f"{base}/{quote}"
                if OTC_REGEX.search(text):
                    pair_str += " OTC"
                best_match = pair_str
                break

    return best_match
