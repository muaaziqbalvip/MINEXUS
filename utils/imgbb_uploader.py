"""
MI NEXUS - imgBB Uploader
Uploads images (payment screenshots, admin QR codes) to imgBB so we can
store a permanent URL in Firestore instead of raw file bytes.
"""

import os
import base64
import requests

IMGBB_API_URL = "https://api.imgbb.com/1/upload"


def upload_image(local_file_path, name=None):
    """
    Uploads a local image file to imgBB.
    Returns the hosted image URL, or None if the upload failed.
    """
    api_key = os.environ.get("IMGBB_API_KEY")
    if not api_key:
        return None

    try:
        with open(local_file_path, "rb") as f:
            image_data = base64.b64encode(f.read())

        payload = {
            "key": api_key,
            "image": image_data,
        }
        if name:
            payload["name"] = name

        response = requests.post(IMGBB_API_URL, data=payload, timeout=20)
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            return result["data"]["url"]
        return None
    except Exception:
        return None
