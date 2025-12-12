"""
Simple Telegram notification helper.
"""
import requests
try:
    from settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # type: ignore
except ModuleNotFoundError:
    from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # type: ignore

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_text(message: str):
    try:
        resp = requests.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"success": False, "error": data.get("description"), "message_id": None}
        return {"success": True, "error": None, "message_id": data["result"]["message_id"]}
    except Exception as e:
        return {"success": False, "error": str(e), "message_id": None}


def send_photo(photo_url: str, caption: str):
    """
    Send photo to Telegram.
    If photo_url is a Google Drive link, download it first and send as file.
    Otherwise, send as URL.
    """
    try:
        # Check if it's a Google Drive URL
        if "drive.google.com" in photo_url and "/uc?" in photo_url:
            # Download image from Google Drive
            try:
                img_resp = requests.get(photo_url, timeout=15, allow_redirects=True)
                if img_resp.status_code == 200:
                    # Send as file (multipart/form-data)
                    files = {'photo': ('image.jpg', img_resp.content, 'image/jpeg')}
                    data = {
                        'chat_id': TELEGRAM_CHAT_ID,
                        'caption': caption,
                        'parse_mode': 'HTML'
                    }
                    resp = requests.post(
                        f"{API_BASE}/sendPhoto",
                        files=files,
                        data=data,
                        timeout=30,
                    )
                    result = resp.json()
                    if not result.get("ok"):
                        return {"success": False, "error": result.get("description"), "message_id": None}
                    return {"success": True, "error": None, "message_id": result["result"]["message_id"]}
                else:
                    # Fallback: try as URL
                    return _send_photo_as_url(photo_url, caption)
            except Exception as e:
                print(f"Error downloading image from Drive: {e}")
                # Fallback: try as URL
                return _send_photo_as_url(photo_url, caption)
        else:
            # Direct URL, send as URL
            return _send_photo_as_url(photo_url, caption)
    except Exception as e:
        return {"success": False, "error": str(e), "message_id": None}


def _send_photo_as_url(photo_url: str, caption: str):
    """Send photo using URL (for non-Google Drive URLs)"""
    try:
        resp = requests.post(
            f"{API_BASE}/sendPhoto",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"success": False, "error": data.get("description"), "message_id": None}
        return {"success": True, "error": None, "message_id": data["result"]["message_id"]}
    except Exception as e:
        return {"success": False, "error": str(e), "message_id": None}

