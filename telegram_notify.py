"""
Simple Telegram notification helper.
"""
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

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
    try:
        resp = requests.post(
            f"{API_BASE}/sendPhoto",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"success": False, "error": data.get("description"), "message_id": None}
        return {"success": True, "error": None, "message_id": data["result"]["message_id"]}
    except Exception as e:
        return {"success": False, "error": str(e), "message_id": None}

