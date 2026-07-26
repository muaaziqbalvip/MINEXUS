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


PRICE_REGEX = re.compile(r"\b(\d{1,6}\.\d{2,6})\b")


def _detect_price_label(image_path):
    """
    Fallback: Quotex-style screenshots often show only a live price badge
    (e.g. "3195.26") rather than a pair name. OCR the right-edge strip
    where that badge usually sits.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    # price badge is typically top-right area of the chart
    region = img[0:int(h * 0.15), int(w * 0.65):w]
    if region.size == 0:
        return None
    try:
        processed = _preprocess_for_ocr(region)
        text = pytesseract.image_to_string(processed, config="--psm 7")
    except Exception:
        return None
    match = PRICE_REGEX.search(text)
    return match.group(1) if match else None


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

    if best_match:
        return best_match

    # Fallback: no pair-name text found (common on Quotex trade screens which
    # only show a live price badge, not the asset name). Surface the price
    # instead of a generic placeholder so the card still shows something useful.
    price = _detect_price_label(image_path)
    if price:
        return f"Live Price: {price}"

    return None
