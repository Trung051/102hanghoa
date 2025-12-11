"""
Google Drive upload helper using service account.
"""
import io
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SERVICE_ACCOUNT_FILE = "service_account.json"
# Upload to specific folder (Shared Drive folder you shared with the service account)
try:
    from config import DRIVE_FOLDER_ID
except Exception:
    DRIVE_FOLDER_ID = None

SCOPES = [
    # drive.file đủ để ghi file được cấp quyền/thư mục đã chia sẻ
    "https://www.googleapis.com/auth/drive.file",
    # phòng khi cần quyền rộng hơn cho Shared Drive
    "https://www.googleapis.com/auth/drive"
]


def _get_drive_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return None, f"File {SERVICE_ACCOUNT_FILE} không tồn tại"
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service, None
    except Exception as e:
        return None, f"Lỗi khởi tạo Google Drive: {e}"


def upload_file_to_drive(file_bytes: bytes, filename: str, mime_type: str):
    """
    Upload a file to Google Drive and return webViewLink.
    """
    service, err = _get_drive_service()
    if err:
        return {"success": False, "error": err, "url": None}

    metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        metadata["parents"] = [DRIVE_FOLDER_ID]

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)

    try:
        file = (
            service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, webViewLink, parents",
                supportsAllDrives=True,
            )
            .execute()
        )
        return {
            "success": True,
            "error": None,
            "url": file.get("webViewLink"),
            "id": file.get("id"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "url": None}

