"""
Configuration file for Shipment Management App
Supports reading secrets from Streamlit Cloud or environment variables.
"""
import os

try:
    import streamlit as st  # Available at runtime in Streamlit
except ImportError:
    st = None


def get_secret(name, default=None):
    """Fetch secret from st.secrets or environment with fallback."""
    if st is not None and name in st.secrets:
        return st.secrets[name]
    val = os.getenv(name)
    if val is not None:
        return val
    return default


# User credentials for simple authentication
USERS = {
    'admin': 'admin123',
    'user': 'user123',
    'staff': 'staff123'
}

# Shipment status values
STATUS_VALUES = ['Phiếu tạm', 'Đang gửi', 'Đã nhận', 'Hư hỏng', 'Mất', 'Chuyển kho']

# Default status for new shipments
DEFAULT_STATUS = 'Đang gửi'

# Default suppliers data (will be seeded into database)
DEFAULT_SUPPLIERS = [
    {
        'id': 1,
        'name': 'GHN',
        'contact': '0987654321',
        'address': 'Hà Nội',
        'is_active': True
    },
    {
        'id': 2,
        'name': 'J&T',
        'contact': '0912345678',
        'address': 'TP.HCM',
        'is_active': True
    },
    {
        'id': 3,
        'name': 'Ahamove',
        'contact': '0998765432',
        'address': 'TP.HCM',
        'is_active': True
    }
]

# Database file path
DB_PATH = 'shipments.db'

# Telegram settings (read from secrets/env; fallback to existing values)
TELEGRAM_TOKEN = get_secret('TELEGRAM_TOKEN', '8292303287:AAFn5UVMHgVAmuBdkdlCnfbwME7noLyHDIw')
TELEGRAM_CHAT_ID_RAW = get_secret('TELEGRAM_CHAT_ID', '-1003093937806')
try:
    TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID_RAW)
except Exception:
    TELEGRAM_CHAT_ID = -1003093937806

# Drive folder for normal shipments (phiếu bình thường)
DRIVE_FOLDER_ID = get_secret('DRIVE_FOLDER_ID', '1xP9msTCgN2sFvJCW2zjSQU-yEeQdS0yV')

# Drive folder for transfer slips (phiếu chuyển)
DRIVE_TRANSFER_FOLDER_ID = get_secret('DRIVE_TRANSFER_FOLDER_ID', '1uEp4nwk1Ld85eug1rx27fkFtcjuWz3Zw')

