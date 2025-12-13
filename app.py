"""
Streamlit Shipment Management Application
Main application file with UI and business logic
"""

import streamlit as st
from PIL import Image
import pandas as pd
from datetime import datetime
import cv2
import qrcode
import base64
from io import BytesIO
import streamlit.components.v1 as components
import requests
import html

# Write service_account.json from secrets/env if missing (for Streamlit Cloud)
import os

def _write_sa_json(raw: str):
    """Write service account JSON to file, sanitizing newline issues if needed."""
    import json
    import re

    def try_json(content: str):
        try:
            json.loads(content)
            return True
        except Exception:
            return False

    candidate = raw
    # First attempt: as-is
    if not try_json(candidate):
        # Normalize CRLF
        candidate = candidate.replace("\r\n", "\n")
    if not try_json(candidate):
        # Escape actual newlines inside private_key string if present
        def _escape_pk(match):
            body = match.group(1)
            body = body.replace("\r\n", "\n").replace("\n", "\\n")
            return f'"private_key": "{body}"'

        candidate = re.sub(r'"private_key":\s*"([^"]+?)"', _escape_pk, candidate, flags=re.S)

    # Last check
    if not try_json(candidate):
        raise ValueError("Service account JSON invalid after sanitization.")

    with open("service_account.json", "w", encoding="utf-8") as f:
        f.write(candidate)


def ensure_service_account_file():
    """Rewrite service_account.json from secrets/env on every startup to avoid stale/bad files."""
    raw = None
    if st is not None and "SERVICE_ACCOUNT_JSON" in st.secrets:
        raw = st.secrets["SERVICE_ACCOUNT_JSON"]
    if raw is None:
        raw = os.getenv("SERVICE_ACCOUNT_JSON")
    if raw:
        _write_sa_json(raw)

# Import modules
# Ensure local config/database modules take precedence
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_database, save_shipment, update_shipment_status, update_shipment,
    get_all_shipments, get_shipment_by_qr_code, get_suppliers, get_audit_log,
    get_all_suppliers, add_supplier, update_supplier, delete_supplier,
    set_user_password, get_all_users, get_shipment_by_id, create_store,
    get_all_stores, assign_user_to_store, delete_user, get_user,
    create_transfer_slip, add_shipment_to_transfer_slip, get_transfer_slip,
    get_transfer_slip_items, get_active_transfer_slip, get_all_transfer_slips,
    update_transfer_slip, update_transfer_slip_shipments_status, clear_all_data,
    auto_update_status_after_1hour, get_active_shipments, cleanup_audit_log
)
from qr_scanner import decode_qr_from_image
from auth import require_login, get_current_user, logout, is_admin, is_store_user, get_store_name_from_username
try:
    from settings import STATUS_VALUES, REQUEST_TYPES  # type: ignore
except ModuleNotFoundError:
    from config import STATUS_VALUES, REQUEST_TYPES  # type: ignore
from google_sheets import push_shipments_to_sheets, test_connection
from drive_upload import upload_file_to_drive, upload_file_to_transfer_folder, upload_multiple_files_to_drive
from telegram_notify import send_text, send_photo
from telegram_helpers import notify_shipment_if_received

# Label/printing helpers defaults
LABEL_DEFAULT_WIDTH_MM = 50
LABEL_DEFAULT_HEIGHT_MM = 30


def ensure_label_defaults():
    """Ensure label size defaults exist in session state."""
    if 'label_width_mm' not in st.session_state:
        st.session_state['label_width_mm'] = LABEL_DEFAULT_WIDTH_MM
    if 'label_height_mm' not in st.session_state:
        st.session_state['label_height_mm'] = LABEL_DEFAULT_HEIGHT_MM


def generate_qr_base64(data: str) -> str:
    """Generate a base64 PNG for a QR code (larger size for better scanning)."""
    qr = qrcode.QRCode(box_size=6, border=2)  # Increased box_size from 4 to 6, border from 1 to 2
    qr.add_data(data or "")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def render_label_component(shipment: dict):
    """Render a printable label for a shipment with QR + info."""
    ensure_label_defaults()
    width = st.session_state.get('label_width_mm', LABEL_DEFAULT_WIDTH_MM)
    height = st.session_state.get('label_height_mm', LABEL_DEFAULT_HEIGHT_MM)
    qr_b64 = generate_qr_base64(shipment.get('qr_code', ''))
    device_name = shipment.get('device_name', '')
    imei = shipment.get('imei', '')
    qr_code = shipment.get('qr_code', '')
    capacity = shipment.get('capacity', '')

    html = build_label_html(qr_b64, qr_code, device_name, imei, capacity, width, height, include_print_button=True, wrapper_id="label-area")
    components.html(html, height=220, scrolling=False)


def build_label_html(qr_b64: str, qr_code: str, device_name: str, imei: str, capacity: str, width: float, height: float,
                     include_print_button: bool, wrapper_id: str) -> str:
    # Chỉ lấy 6 số cuối của IMEI
    imei_short = imei[-6:] if imei and len(imei) >= 6 else imei
    
    btn_html = ""
    if include_print_button:
        btn_html = """
        <div style="margin-top:8px;">
          <button onclick="window.print()" style="
            background:#ef4444;
            color:white;
            border:none;
            padding:8px 12px;
            border-radius:8px;
            cursor:pointer;
          ">In tem</button>
        </div>
        """
    return f"""
    <div style="font-family:Arial,sans-serif;">
      <div id="{wrapper_id}" style="
        width:{width}mm;
        height:{height}mm;
        padding:3mm;
        box-sizing:border-box;
        border:1px dashed #d1d5db;
        display:flex;
        gap:4px;
        align-items:center;
        page-break-inside: avoid;
      ">
        <div style="flex:0 0 50%;">
          <img src="data:image/png;base64,{qr_b64}" style="width:100%;height:auto;max-width:100%;" />
        </div>
        <div style="flex:1 1 50%; font-size:9px; line-height:1.2;">
          <div style="margin-bottom:2px;"><strong>QR:</strong> {qr_code}</div>
          <div style="margin-bottom:2px;"><strong>TB:</strong> {device_name}</div>
          <div style="margin-bottom:2px;"><strong>IMEI:</strong> {imei_short}</div>
            <div><strong>Lỗi / Tình trạng:</strong> {capacity}</div>
        </div>
      </div>
      {btn_html}
    <style>
        @media print {{
          body {{
            margin:0;
          }}
          button {{
            display:none;
          }}
          #{wrapper_id} {{
            border:none;
          }}
        }}
      </style>
    </div>
    """


def render_labels_bulk(shipments):
    """Render multiple labels at once and trigger a single print dialog."""
    ensure_label_defaults()
    width = st.session_state.get('label_width_mm', LABEL_DEFAULT_WIDTH_MM)
    height = st.session_state.get('label_height_mm', LABEL_DEFAULT_HEIGHT_MM)

    labels_html_parts = []
    for idx, sh in enumerate(shipments):
        qr_b64 = generate_qr_base64(sh.get('qr_code', ''))
        part = build_label_html(
            qr_b64=qr_b64,
            qr_code=sh.get('qr_code', ''),
            device_name=sh.get('device_name', ''),
            imei=sh.get('imei', ''),
            capacity=sh.get('capacity', ''),
            width=width,
            height=height,
            include_print_button=False,
            wrapper_id=f"label-{idx}"
        )
        labels_html_parts.append(part)

    full_html = f"""
    <div style="font-family:Arial,sans-serif;">
      <div style="display:flex; flex-direction:column; gap:12px;">
        {''.join(labels_html_parts)}
      </div>
      <div style="margin-top:12px;">
        <button onclick="window.print()" style="
          background:#ef4444;
          color:white;
          border:none;
          padding:10px 14px;
          border-radius:10px;
          cursor:pointer;
        ">In tất cả tem đã chọn</button>
      </div>
      <style>
        @media print {{
          body {{
            margin:0;
          }}
          button {{
            display:none;
          }}
          [id^="label-"] {{
            border:none !important;
          }}
        }}
      </style>
    </div>
    """
    components.html(full_html, height=400, scrolling=True)

# ----------------------- UI Helpers ----------------------- #
@st.cache_data(ttl=3600, show_spinner=False, max_entries=5)  # Cache 1 giờ, tối đa 5 ảnh
def _get_drive_image_bytes(file_id):
    """
    Tải ảnh từ Drive một lần và cache lại
    - Cache tối đa 5 ảnh, tự động xóa ảnh cũ nhất khi quá 5
    - Chỉ tải khi chưa có trong cache, không làm nặng server
    """
    try:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(download_url, timeout=10, stream=True)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        print(f"Error loading image {file_id}: {e}")
    return None


def display_drive_image(image_url, width=300, caption=""):
    """
    Hiển thị ảnh từ Google Drive tự động (không cần expander)
    - Tự động tải và hiển thị ảnh khi được gọi
    - Cache tối đa 5 ảnh, tự động xóa ảnh cũ khi quá giới hạn
    """
    try:
        # Extract file ID from URL
        file_id = None
        if 'uc?export=download&id=' in image_url:
            file_id = image_url.split('id=')[-1]
        elif 'id=' in image_url:
            file_id = image_url.split('id=')[-1].split('&')[0]
        
        if file_id:
            # Tải ảnh với cache (tối đa 5 ảnh)
            image_bytes = _get_drive_image_bytes(file_id)
            
            if image_bytes:
                img = Image.open(BytesIO(image_bytes))
                st.image(img, width=width, caption=caption)
                st.markdown(f"[Mở ảnh trên Drive]({image_url})")
            else:
                st.warning("Không thể tải ảnh từ Drive")
                st.markdown(f"[Mở ảnh trên Drive]({image_url})")
            return True
        else:
            # Fallback: try direct URL
            try:
                st.image(image_url, width=width, caption=caption)
                return True
            except:
                st.markdown(f"[Mở ảnh]({image_url})")
                return False
    except Exception as e:
        st.warning(f"Không thể hiển thị ảnh: {str(e)}")
        st.markdown(f"[Mở ảnh trên Drive]({image_url})")
        return False


def inject_sidebar_styles():
    """Apply custom styles for a cleaner, more professional sidebar."""
    st.markdown(
        """
        <style>
        /* Sidebar container */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
            border-right: 1px solid #e5e7eb;
            padding-top: 12px;
        }
        /* Title and user info */
        [data-testid="stSidebar"] .sidebar-title {
            font-size: 20px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 12px;
        }
        [data-testid="stSidebar"] .sidebar-user {
            font-size: 14px;
            color: #4b5563;
            margin-bottom: 6px;
        }
        [data-testid="stSidebar"] .sidebar-label {
            font-size: 13px;
            font-weight: 600;
            color: #111827;
            margin: 12px 0 6px 0;
        }
        /* Nav buttons - base */
        [data-testid="stSidebar"] .stButton>button {
            width: 100%;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            color: #111827;
            border-radius: 10px;
            padding: 10px 12px;
            font-weight: 600;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            transition: all 0.15s ease;
        }
        /* Secondary (default) */
        [data-testid="stSidebar"] .stButton>button[data-testid="baseButton-secondary"] {
            background: #ffffff;
            color: #111827;
            border: 1px solid #e5e7eb;
        }
        [data-testid="stSidebar"] .stButton>button:hover {
            border-color: #3b82f6;
            box-shadow: 0 4px 10px rgba(59,130,246,0.16);
            transform: translateY(-1px);
        }
        /* Primary (selected) */
        [data-testid="stSidebar"] .stButton>button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #fff;
            border: 1px solid #1d4ed8;
            box-shadow: 0 6px 16px rgba(37,99,235,0.28);
        }
        [data-testid="stSidebar"] .stButton>button[data-testid="baseButton-primary"]:hover {
            filter: brightness(1.02);
            transform: translateY(-1px);
        }
        /* Logout button */
        [data-testid="stSidebar"] .logout-btn>button {
            width: 100%;
            border-radius: 8px;
            border: 1px solid #fca5a5;
            background: #fff1f2;
            color: #b91c1c;
            font-weight: 600;
        }
        [data-testid="stSidebar"] .logout-btn>button:hover {
            border-color: #ef4444;
            background: #ffe4e6;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_main_styles():
    """Apply global spacing tweaks for better mobile experience and dashboard styling."""
    st.markdown(
        """
        <style>
        /* Compact main padding for small screens */
        @media (max-width: 768px) {
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-top: 1rem;
                padding-bottom: 2rem;
                padding-left: 0.9rem;
                padding-right: 0.9rem;
            }
        }
        
        </style>
        """,
        unsafe_allow_html=True,
    )

# Function definitions
def scan_qr_screen():
    """Unified screen for scanning QR code - handles both new and existing shipments"""
    current_user = get_current_user()
    
    # Initialize session state for camera
    if 'show_camera' not in st.session_state:
        st.session_state['show_camera'] = False
    if 'scanned_qr_code' not in st.session_state:
        st.session_state['scanned_qr_code'] = None
    if 'found_shipment' not in st.session_state:
        st.session_state['found_shipment'] = None
    
    # Check if we have a found shipment to display
    found_shipment = st.session_state.get('found_shipment', None)
    scanned_qr_code = st.session_state.get('scanned_qr_code', None)
    # If we found a shipment, show it
    if found_shipment:
        show_shipment_info(current_user, found_shipment)
        return
    # If we have scanned QR code but no shipment found, show create form
    if scanned_qr_code and not found_shipment:
        show_create_shipment_form(current_user, scanned_qr_code)
        return
    
    # Main layout
    st.subheader("Quét QR Code")
    st.caption("Chụp ảnh để nhận dạng QR.")
    # Button to start scanning
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("📷 Bắt đầu quét", type="primary", key="start_scan_btn"):
            st.session_state['show_camera'] = True
            st.session_state['scanned_qr_code'] = None
            st.session_state['found_shipment'] = None
            st.session_state['webrtc_qr'] = None
            st.rerun()
    
    with col_btn2:
        if st.session_state['show_camera']:
            if st.button("❌ Dừng quét", key="stop_scan_btn"):
                st.session_state['show_camera'] = False
                st.rerun()
    
    # Show camera if enabled
    if st.session_state['show_camera']:
        st.info("Đưa QR code vào khung hình và chụp ảnh. Hệ thống sẽ tự động nhận diện.")
        
        picture = st.camera_input("📷 Quét mã QR", key="scan_camera")
        
        if picture is not None:
            # Show processing indicator
            with st.spinner("Đang xử lý và nhận diện QR code..."):
                try:
                    # Decode QR code automatically
                    image = Image.open(picture)
                    qr_text = decode_qr_from_image(image)
                except Exception as e:
                    st.error(f"❌ Lỗi khi xử lý ảnh: {str(e)}")
                    qr_text = None
                    # Check if pyzbar is available
                    try:
                        from qr_scanner import PYZBAR_AVAILABLE
                        if not PYZBAR_AVAILABLE:
                            st.error("**❌ Lỗi: Thư viện pyzbar chưa được cài đặt hoặc thiếu zbar DLL!**")
                            st.info("""
                            **Hướng dẫn cài đặt:**
                            1. Cài đặt pyzbar: `python -m pip install pyzbar`
                            2. Trên Windows, cần cài thêm zbar DLL:
                               - Tải từ: https://github.com/NuGet/Home/issues/3901
                               - Hoặc cài qua conda: `conda install -c conda-forge zbar`
                            3. Khởi động lại ứng dụng
                            """)
                    except:
                        pass
            
            if qr_text:
                # Chỉ lấy mã QR (toàn bộ chuỗi quét được)
                qr_code = qr_text.strip()
                
                if qr_code:
                    # Check if shipment already exists
                    existing_shipment = get_shipment_by_qr_code(qr_code)
                    
                    if existing_shipment:
                        # Shipment exists - show info
                        st.session_state['found_shipment'] = existing_shipment
                        st.session_state['scanned_qr_code'] = qr_code
                        st.session_state['show_camera'] = False
                        st.rerun()
                    else:
                        # New shipment - show create form
                        st.success("✅ Đã nhận diện QR code! Đang chuyển sang form tạo phiếu...")
                        st.session_state['scanned_qr_code'] = qr_code
                        st.session_state['show_camera'] = False
                        st.rerun()
            else:
                st.warning("⚠️ Không phát hiện QR code trong ảnh. Vui lòng thử lại.")
                
                # Check if OpenCV is available
                try:
                    from qr_scanner import CV2_AVAILABLE
                    if not CV2_AVAILABLE:
                        st.error("**❌ Lỗi: Thư viện opencv-python chưa được cài đặt!**")
                        st.info("""
                        **Hướng dẫn cài đặt:**
                        1. Cài đặt opencv-python: `python -m pip install opencv-python`
                        2. Khởi động lại ứng dụng
                        """)
                except:
                    pass
                
                st.info("**Mẹo để quét thành công:**")
                st.info("   - Đảm bảo QR code rõ ràng và đủ ánh sáng")
                st.info("   - Giữ camera ổn định, không bị mờ")
                st.info("   - QR code phải nằm hoàn toàn trong khung hình")
                st.info("   - Thử chụp lại với góc độ khác")
    else:
        st.info("Click nút 'Bắt đầu quét' để mở camera và quét QR code")


def show_shipment_info(current_user, shipment):
    """Show existing shipment information with option to mark as received"""
    st.subheader("📦 Thông Tin Phiếu Gửi Hàng")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.success("✅ Phiếu đã tồn tại trong hệ thống!")
        
        # Display full shipment information
        st.write("### Chi Tiết Phiếu")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.write(f"**Mã QR Code:** {shipment['qr_code']}")
            st.write(f"**IMEI:** {shipment['imei']}")
            st.write(f"**Tên thiết bị:** {shipment['device_name']}")
            st.write(f"**Lỗi / Tình trạng:** {shipment['capacity']}")
        
        with info_col2:
            st.write(f"**Nhà cung cấp:** {shipment['supplier']}")
            st.write(f"**Trạng thái:** {shipment['status']}")
            st.write(f"**Thời gian gửi:** {shipment['sent_time']}")
            if shipment['received_time']:
                st.write(f"**Thời gian nhận:** {shipment['received_time']}")
            st.write(f"**Người tạo:** {shipment['created_by']}")
            if shipment['updated_by']:
                st.write(f"**Người cập nhật:** {shipment['updated_by']}")
        
        if shipment['notes']:
            st.write(f"**Ghi chú:** {shipment['notes']}")
        
        # Display existing images if any
        if shipment.get('image_url'):
            st.write("### Ảnh Đính Kèm")
            image_urls = shipment['image_url'].split(';')
            for idx, img_url in enumerate(image_urls, 1):
                if img_url.strip():
                    try:
                        st.image(img_url.strip(), width=300, caption=f"Ảnh {idx}")
                    except:
                        st.markdown(f"[Mở ảnh {idx}]({img_url.strip()})")
        
        # Button to scan again
        if st.button("🔄 Quét lại QR code", key="rescan_btn"):
            st.session_state['found_shipment'] = None
            st.session_state['scanned_qr_code'] = None
            st.session_state['show_camera'] = True
            st.rerun()
    
    with col2:
        st.subheader("Cập Nhật Trạng Thái")
        
        current_status = shipment['status']
        st.info(f"Trạng thái hiện tại: **{current_status}**")
        
        # Only show "Đã nhận" button if not yet received
        if current_status != 'Đã nhận':
            # Quick upload images for "Đã nhận" button
            quick_upload_images = st.file_uploader(
                "📷 Thêm ảnh khi đánh dấu 'Đã nhận' (tùy chọn)", 
                type=["png", "jpg", "jpeg"], 
                accept_multiple_files=True, 
                key="upload_image_quick_received"
            )
            
            if st.button("✅ Đã Nhận", type="primary", key="mark_received_btn"):
                # Upload images if provided
                image_url = None
                if quick_upload_images:
                    with st.spinner(f"Đang upload {len(quick_upload_images)} ảnh lên Google Drive (song song)..."):
                        # Prepare files data for parallel upload
                        sanitized_qr = shipment['qr_code'].strip().replace(" ", "_") or "qr_image"
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        files_data = []
                        for idx, f in enumerate(quick_upload_images, start=1):
                            file_bytes = f.getvalue()
                            mime = f.type or "image/jpeg"
                            orig_name = f.name or "image.jpg"
                            ext = ""
                            if "." in orig_name:
                                ext = orig_name.split(".")[-1]
                            if not ext:
                                ext = "jpg"
                            drive_filename = f"{sanitized_qr}_received_{timestamp}_anh{idx}.{ext}"
                            files_data.append({
                                'file_bytes': file_bytes,
                                'filename': drive_filename,
                                'mime_type': mime,
                                'index': idx
                            })
                        
                        # Upload all files in parallel
                        upload_results = upload_multiple_files_to_drive(files_data, max_workers=5)
                        
                        # Process results
                        urls = []
                        success_count = 0
                        for result in upload_results:
                            if result['success']:
                                urls.append(result['url'])
                                success_count += 1
                                print(f"✅ Upload ảnh {result['index']} thành công: {result['url']}")
                            else:
                                st.error(f"❌ Upload ảnh {result['index']} thất bại: {result['error']}")
                                print(f"❌ Upload ảnh {result['index']} thất bại: {result['error']}")
                        
                        if urls:
                            image_url = ";".join(urls)
                            st.success(f"📸 Đã upload {success_count}/{len(quick_upload_images)} ảnh lên Drive")
                            print(f"📸 Image URLs: {image_url}")
                        else:
                            st.error("❌ Không có ảnh nào được upload thành công!")
                            st.stop()
                
                result = update_shipment_status(
                    qr_code=shipment['qr_code'],
                    new_status='Đã nhận',
                    updated_by=current_user,
                    notes=None,
                    image_url=image_url if image_url else None
                )
                
                if result['success']:
                    st.success("✅ Đã cập nhật trạng thái thành: **Đã nhận**")
                    if image_url:
                        st.success(f"✅ Đã thêm {len(quick_upload_images)} ảnh vào phiếu")
                        st.info(f"🔗 Link ảnh: {image_url[:100]}..." if len(image_url) > 100 else f"🔗 Link ảnh: {image_url}")
                    st.balloons()
                    # Refresh shipment data first to get updated image_url
                    updated_shipment = get_shipment_by_qr_code(shipment['qr_code'])
                    if updated_shipment:
                        st.session_state['found_shipment'] = updated_shipment
                        # Notify Telegram with updated shipment data
                        if image_url:
                            num_images = len(quick_upload_images) if quick_upload_images else len(image_url.split(';')) if image_url else 0
                            with st.spinner(f"Đang gửi {num_images} ảnh lên Telegram..."):
                                print(f"📤 Gửi Telegram với {num_images} ảnh: {updated_shipment.get('image_url', 'N/A')}")
                                telegram_result = notify_shipment_if_received(
                                    updated_shipment['id'], 
                                    force=True, 
                                    is_update_image=True
                                )
                                if telegram_result and telegram_result.get('success'):
                                    st.success(f"✅ Đã gửi {num_images} ảnh lên Telegram")
                                    print(f"✅ Telegram gửi thành công: {telegram_result}")
                                elif telegram_result:
                                    st.warning(f"⚠️ Gửi Telegram: {telegram_result.get('error', 'Lỗi không xác định')}")
                                    print(f"❌ Telegram lỗi: {telegram_result.get('error', 'Lỗi không xác định')}")
                                else:
                                    st.warning("⚠️ Không nhận được phản hồi từ Telegram")
                                    print("❌ Telegram không trả về kết quả")
                        else:
                            print(f"📤 Gửi Telegram không có ảnh")
                            notify_shipment_if_received(
                                updated_shipment['id'], 
                                force=True, 
                                is_update_image=False
                            )
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
        else:
            st.success("✅ Phiếu đã được tiếp nhận")
        
        # Option to change to other status
        new_status = st.selectbox(
            "Thay đổi trạng thái:",
            STATUS_VALUES,
            index=STATUS_VALUES.index(current_status) if current_status in STATUS_VALUES else 0,
            key="status_select"
        )
        
        notes = st.text_area("Ghi chú cập nhật:", key="update_notes")
        
        # Upload images
        uploaded_images = st.file_uploader(
            "📷 Thêm ảnh (tùy chọn, chọn nhiều)", 
            type=["png", "jpg", "jpeg"], 
            accept_multiple_files=True, 
            key="upload_image_qr_update"
        )
        
        if st.button("🔄 Cập Nhật", key="update_status_btn"):
            if new_status != current_status or uploaded_images or notes:
                # Upload images if provided
                image_url = None
                if uploaded_images:
                    with st.spinner(f"Đang upload {len(uploaded_images)} ảnh lên Google Drive (song song)..."):
                        # Prepare files data for parallel upload
                        sanitized_qr = shipment['qr_code'].strip().replace(" ", "_").replace("/", "_") or "qr_image"
                        sanitized_status = new_status.replace(" ", "_").replace("/", "_") if new_status else "unknown"
                        files_data = []
                        for idx, f in enumerate(uploaded_images, start=1):
                            file_bytes = f.getvalue()
                            mime = f.type or "image/jpeg"
                            orig_name = f.name or "image.jpg"
                            ext = ""
                            if "." in orig_name:
                                ext = orig_name.split(".")[-1]
                            if not ext:
                                ext = "jpg"
                            # Tên file: mã QR + trạng thái + stt
                            drive_filename = f"{sanitized_qr}_{sanitized_status}_{idx}.{ext}"
                            files_data.append({
                                'file_bytes': file_bytes,
                                'filename': drive_filename,
                                'mime_type': mime,
                                'index': idx
                            })
                        
                        # Upload all files in parallel
                        upload_results = upload_multiple_files_to_drive(files_data, max_workers=5)
                        
                        # Process results
                        urls = []
                        success_count = 0
                        for result in upload_results:
                            if result['success']:
                                urls.append(result['url'])
                                success_count += 1
                                print(f"✅ Upload ảnh {result['index']} thành công: {result['url']}")
                            else:
                                st.error(f"❌ Upload ảnh {result['index']} thất bại: {result['error']}")
                                print(f"❌ Upload ảnh {result['index']} thất bại: {result['error']}")
                        
                        if urls:
                            image_url = ";".join(urls)
                            st.success(f"📸 Đã upload {success_count}/{len(uploaded_images)} ảnh lên Drive")
                            print(f"📸 Image URLs: {image_url}")
                        else:
                            st.error("❌ Không có ảnh nào được upload thành công!")
                            st.stop()
                
                result = update_shipment_status(
                    qr_code=shipment['qr_code'],
                    new_status=new_status,
                    updated_by=current_user,
                    notes=notes if notes else None,
                    image_url=image_url if image_url else None
                )
                
                if result['success']:
                    if new_status != current_status:
                        st.success(f"✅ Đã cập nhật trạng thái thành: **{new_status}**")
                    else:
                        st.success("✅ Đã cập nhật phiếu thành công!")
                    if image_url:
                        st.success(f"✅ Đã thêm {len(uploaded_images)} ảnh vào phiếu")
                        st.info(f"🔗 Link ảnh: {image_url[:100]}..." if len(image_url) > 100 else f"🔗 Link ảnh: {image_url}")
                    st.balloons()
                    # Refresh shipment data first to get updated image_url
                    updated_shipment = get_shipment_by_qr_code(shipment['qr_code'])
                    if updated_shipment:
                        st.session_state['found_shipment'] = updated_shipment
                        # Notify Telegram if Đã nhận
                        if new_status == 'Đã nhận':
                            if image_url:
                                with st.spinner("Đang gửi ảnh lên Telegram..."):
                                    print(f"📤 Gửi Telegram với ảnh: {updated_shipment.get('image_url', 'N/A')}")
                                    telegram_result = notify_shipment_if_received(
                                        updated_shipment['id'], 
                                        force=True, 
                                        is_update_image=True
                                    )
                                    if telegram_result and telegram_result.get('success'):
                                        st.success("✅ Đã gửi ảnh lên Telegram")
                                        print(f"✅ Telegram gửi thành công: {telegram_result}")
                                    elif telegram_result:
                                        st.warning(f"⚠️ Gửi Telegram: {telegram_result.get('error', 'Lỗi không xác định')}")
                                        print(f"❌ Telegram lỗi: {telegram_result.get('error', 'Lỗi không xác định')}")
                                    else:
                                        st.warning("⚠️ Không nhận được phản hồi từ Telegram")
                                        print("❌ Telegram không trả về kết quả")
                            else:
                                print(f"📤 Gửi Telegram không có ảnh")
                                notify_shipment_if_received(
                                    updated_shipment['id'], 
                                    force=True, 
                                    is_update_image=False
                                )
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
            else:
                st.warning("⚠️ Vui lòng thay đổi trạng thái, thêm ảnh hoặc ghi chú để cập nhật!")


def show_create_shipment_form(current_user, qr_code):
    """Show form to create shipment from scanned QR code"""
    st.subheader("📝 Tạo Phiếu Gửi Hàng")
    
    # Initialize form data in session state if not exists
    if 'form_qr_code' not in st.session_state:
        st.session_state['form_qr_code'] = qr_code
    if 'form_imei' not in st.session_state:
        st.session_state['form_imei'] = ''
    if 'form_device_name' not in st.session_state:
        st.session_state['form_device_name'] = ''
    if 'form_capacity' not in st.session_state:
        st.session_state['form_capacity'] = ''
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.success("✅ Đã quét QR code thành công!")
        st.write("**Vui lòng kiểm tra và điền đầy đủ thông tin:**")
        
        # Editable form fields
        qr_code = st.text_input(
            "Mã QR Code:",
            value=st.session_state['form_qr_code'],
            key="input_qr_code",
            help="Mã QR code từ phiếu"
        )
        st.session_state['form_qr_code'] = qr_code
        
        imei = st.text_input(
            "IMEI:",
            value=st.session_state['form_imei'],
            key="input_imei",
            help="IMEI của thiết bị"
        )
        st.session_state['form_imei'] = imei
        
        device_name = st.text_input(
            "Tên thiết bị:",
            value=st.session_state['form_device_name'],
            key="input_device_name",
            help="Tên thiết bị (ví dụ: iPhone 15 Pro Max)"
        )
        st.session_state['form_device_name'] = device_name
        
        capacity = st.text_input(
            "Lỗi / Tình trạng *:",
            value=st.session_state['form_capacity'],
            key="input_capacity",
            help="Lỗi hoặc tình trạng thiết bị"
        )
        st.session_state['form_capacity'] = capacity
        
        # Show which fields are empty
        empty_fields = []
        if not qr_code.strip():
            empty_fields.append("Mã QR Code")
        if not imei.strip():
            empty_fields.append("IMEI")
        if not device_name.strip():
            empty_fields.append("Tên thiết bị")
        if not capacity.strip():
            empty_fields.append("Lỗi / Tình trạng")
        
        if empty_fields:
            st.warning(f"⚠️ Các trường còn trống: {', '.join(empty_fields)}")
        
        # Button to scan again
        if st.button("🔄 Quét lại QR code", key="rescan_btn"):
            # Clear form data
            for key in ['form_qr_code', 'form_imei', 'form_device_name', 'form_capacity', 'scanned_qr_code']:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state['show_camera'] = True
            st.rerun()
    
    with col2:
        st.subheader("Thông Tin Phiếu")
        
        # Kiểm tra user có phải cửa hàng không
        store_user = is_store_user()
        store_name = None
        if store_user:
            store_name = get_store_name_from_username(current_user)
            st.info(f"🏪 Tạo phiếu cho: **{store_name}**")
        
        # Trường cửa hàng (chỉ hiện cho user cửa hàng)
        if store_user:
            store_name_input = st.text_input(
                "Tên cửa hàng:",
                value=store_name,
                key="store_name_input",
                disabled=True,
                help="Tự động điền từ tài khoản đăng nhập"
            )
        else:
            store_name_input = st.text_input(
                "Tên cửa hàng (nếu có):",
                value="",
                key="store_name_input",
                help="Nhập tên cửa hàng nếu có"
            )
            if store_name_input.strip():
                store_name = store_name_input.strip()
        
        # Get suppliers
        suppliers_df = get_suppliers()
        if suppliers_df.empty:
            st.error("❌ Chưa có nhà cung cấp trong hệ thống")
            return
        
        supplier = st.selectbox(
            "Nhà cung cấp gửi:",
            suppliers_df['name'].tolist(),
            key="supplier_select"
        )
        
        # Loại yêu cầu (bắt buộc)
        request_type = st.selectbox(
            "Loại yêu cầu *:",
            REQUEST_TYPES,
            key="request_type_select",
            help="Chọn loại yêu cầu (bắt buộc)"
        )
        
        notes = st.text_area("Ghi chú:", key="notes_input")
        uploaded_images_create = st.file_uploader("Upload ảnh (tùy chọn, chọn nhiều)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="upload_image_create")
        
        if st.button("💾 Lưu Phiếu", type="primary", key="save_btn"):
            # Validate required fields
            if not qr_code.strip():
                st.error("❌ Vui lòng nhập Mã QR Code!")
            elif not imei.strip():
                st.error("❌ Vui lòng nhập IMEI!")
            elif not device_name.strip():
                st.error("❌ Vui lòng nhập Tên thiết bị!")
            elif not capacity.strip():
                st.error("❌ Vui lòng nhập Lỗi / Tình trạng!")
            elif not request_type:
                st.error("❌ Vui lòng chọn Loại yêu cầu!")
            else:
                image_url = None
                if uploaded_images_create:
                    urls = []
                    current_status = 'Đã nhận'  # Default status for new shipments
                    sanitized_qr = qr_code.strip().replace(" ", "_").replace("/", "_") or "qr_image"
                    sanitized_status = current_status.replace(" ", "_").replace("/", "_")
                    for idx, f in enumerate(uploaded_images_create, start=1):
                        file_bytes = f.getvalue()
                        mime = f.type or "image/jpeg"
                        orig_name = f.name or "image.jpg"
                        ext = ""
                        if "." in orig_name:
                            ext = orig_name.split(".")[-1]
                        if not ext:
                            ext = "jpg"
                        # Tên file: mã QR + trạng thái + stt
                        drive_filename = f"{sanitized_qr}_{sanitized_status}_{idx}.{ext}"
                        upload_res = upload_file_to_drive(file_bytes, drive_filename, mime)
                        if upload_res['success']:
                            urls.append(upload_res['url'])
                        else:
                            st.error(f"❌ Upload ảnh {idx} thất bại: {upload_res['error']}")
                            st.stop()
                    if urls:
                        image_url = ";".join(urls)

                # Set status mặc định: "Đã nhận"
                default_status = 'Đã nhận'
                
                result = save_shipment(
                    qr_code=qr_code.strip(),
                    imei=imei.strip(),
                    device_name=device_name.strip(),
                    capacity=capacity.strip(),
                    supplier=supplier,
                    created_by=current_user,
                    notes=notes if notes else None,
                    image_url=image_url,
                    status=default_status,
                    store_name=store_name,
                    request_type=request_type
                )
                
                if result['success']:
                    st.success(f"✅ Phiếu #{result['id']} đã được lưu thành công!")
                    st.balloons()
                    # Notify only if default status is already Đã nhận (unlikely); skip otherwise
                    if supplier and STATUS_VALUES and STATUS_VALUES[0] == 'Đã nhận':
                        notify_shipment_if_received(result['id'], force=True)
                    # Clear scanned data and form data
                    for key in ['scanned_qr_code', 'show_camera', 
                               'form_qr_code', 'form_imei', 'form_device_name', 'form_capacity', 'found_shipment']:
                        if key in st.session_state:
                            del st.session_state[key]
                    # Clear form
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")


def receive_shipment_screen():
    """Screen for scanning QR code to receive/update shipment"""
    current_user = get_current_user()
    
    # Initialize session state for camera
    if 'show_camera_receive' not in st.session_state:
        st.session_state['show_camera_receive'] = False
    if 'shipment_found' not in st.session_state:
        st.session_state['shipment_found'] = False
    
    # Get found shipment from session
    found_shipment = st.session_state.get('found_shipment', None)
    
    # If shipment already found, show update form directly
    if found_shipment and st.session_state.get('shipment_found', False):
        st.session_state['show_camera_receive'] = False
        show_update_shipment_form(current_user, found_shipment)
        return
    
    # Main layout
    st.subheader("Quét QR Code để Tiếp Nhận Hàng")
    
    # Button to start scanning
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("Bắt đầu quét", type="primary", key="start_scan_receive_btn"):
            st.session_state['show_camera_receive'] = True
            st.session_state['shipment_found'] = False
            st.rerun()
    
    with col_btn2:
        if st.session_state['show_camera_receive']:
            if st.button("Dừng quét", key="stop_scan_receive_btn"):
                st.session_state['show_camera_receive'] = False
                st.rerun()
    
    # Show camera if enabled
    if st.session_state['show_camera_receive']:
        st.info("Đưa QR code vào khung hình và chụp ảnh. Hệ thống sẽ tự động nhận diện.")
        
        picture = st.camera_input("Quét mã QR", key="receive_camera")
        
        if picture is not None:
            # Show processing indicator
            with st.spinner("Đang xử lý và nhận diện QR code..."):
                # Decode QR code automatically
                image = Image.open(picture)
                qr_text = decode_qr_from_image(image)
            
            if qr_text:
                # Chỉ lấy mã QR (toàn bộ chuỗi quét được)
                qr_code = qr_text.strip()
                
                if qr_code:
                    # Find shipment in database
                    shipment_data = get_shipment_by_qr_code(qr_code)
                    
                    if shipment_data:
                        # Successfully found
                        st.success("Tìm thấy phiếu! Đang chuyển sang tab cập nhật...")
                        
                        # Store in session state
                        st.session_state['found_shipment'] = shipment_data
                        st.session_state['shipment_found'] = True
                        st.session_state['show_camera_receive'] = False
                        
                        # Auto switch to update form
                        st.rerun()
                    else:
                        st.error(f"Không tìm thấy phiếu với mã QR: `{qr_code}`")
                        st.info("Vui lòng kiểm tra lại mã QR hoặc thử lại.")
                        st.info("Click 'Dừng quét' để quay lại.")
            else:
                st.warning("⚠️ Không phát hiện QR code trong ảnh. Vui lòng thử lại.")
                st.info("**Mẹo để quét thành công:**")
                st.info("   - Đảm bảo QR code rõ ràng và đủ ánh sáng")
                st.info("   - Giữ camera ổn định, không bị mờ")
                st.info("   - QR code phải nằm hoàn toàn trong khung hình")
                st.info("   - Thử chụp lại với góc độ khác")
    else:
        # Show instruction when camera is off
        if not found_shipment:
            st.info("Click nút 'Bắt đầu quét' để mở camera và quét QR code")
        else:
            # Show form if shipment found
            show_update_shipment_form(current_user, found_shipment)


def show_update_shipment_form(current_user, found_shipment):
    """Show form to update shipment status"""
    st.subheader("Cập Nhật Trạng Thái Phiếu")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.success("Đã tìm thấy phiếu!")
        st.write("**Thông tin phiếu:**")
        
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.write(f"**Mã QR:** {found_shipment['qr_code']}")
            st.write(f"**IMEI:** {found_shipment['imei']}")
            st.write(f"**Tên máy:** {found_shipment['device_name']}")
        with info_col2:
            st.write(f"**Lỗi / Tình trạng:** {found_shipment['capacity']}")
            st.write(f"**NCC:** {found_shipment['supplier']}")
            st.write(f"**Thời gian gửi:** {found_shipment['sent_time']}")
        
        # Button to scan again
        if st.button("🔄 Quét lại QR code", key="rescan_receive_btn"):
            st.session_state['found_shipment'] = None
            st.session_state['shipment_found'] = False
            st.session_state['show_camera_receive'] = True
            st.rerun()
    
    with col2:
        st.subheader("Cập Nhật Trạng Thái")
        
        current_status = found_shipment['status']
        store_name = found_shipment.get('store_name', '')
        if store_name:
            st.info(f"🏪 Cửa hàng: **{store_name}**")
        st.info(f"Trạng thái hiện tại: **{current_status}**")
        
        # Tạo danh sách trạng thái động (bao gồm "Gửi + tên NCC")
        suppliers_df = get_suppliers()
        status_options = STATUS_VALUES.copy()
        
        # Thêm các trạng thái "Gửi + tên NCC" nếu chưa có
        for _, supplier_row in suppliers_df.iterrows():
            supplier_name = supplier_row['name']
            send_status = f"Gửi {supplier_name}"
            if send_status not in status_options:
                status_options.append(send_status)
        
        new_status = st.selectbox(
            "Trạng thái mới:",
            status_options,
            index=status_options.index(current_status) if current_status in status_options else 0,
            key="status_select"
        )
        
        notes = st.text_area("Ghi chú cập nhật:", key="update_notes")
        
        if st.button("Cập Nhật", type="primary", key="update_btn"):
            if new_status != current_status:
                result = update_shipment_status(
                    qr_code=found_shipment['qr_code'],
                    new_status=new_status,
                    updated_by=current_user,
                    notes=notes if notes else None
                )
                
                if result['success']:
                    st.success(f"Đã cập nhật trạng thái thành: **{new_status}**")
                    st.balloons()
                    # Notify Telegram nếu đã nhận hoặc hoàn thành
                    if new_status in ['Đã nhận', 'Hoàn thành chuyển cửa hàng']:
                        res = notify_shipment_if_received(found_shipment['id'], force=True)
                        if res and not res.get('success'):
                            st.warning(f"Không gửi được Telegram: {res.get('error')}")
                    # Clear found shipment
                    if 'found_shipment' in st.session_state:
                        del st.session_state['found_shipment']
                    if 'shipment_found' in st.session_state:
                        st.session_state['shipment_found'] = False
                    if 'show_camera_receive' in st.session_state:
                        st.session_state['show_camera_receive'] = False
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
            else:
                st.warning("⚠️ Vui lòng chọn trạng thái khác với trạng thái hiện tại!")


def show_shipment_detail_popup(shipment_id):
    """Show shipment detail popup with history and update time"""
    shipment = get_shipment_by_id(shipment_id)
    if not shipment:
        st.error("Không tìm thấy phiếu")
        return
    
    with st.expander(f"📋 Chi tiết phiếu: {shipment.get('qr_code', '')}", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Mã Yêu Cầu:** {shipment.get('qr_code', '')}")
            st.write(f"**Tên Hàng:** {shipment.get('device_name', '')}")
            st.write(f"**IMEI:** {shipment.get('imei', '')}")
            st.write(f"**Lỗi/Tình trạng:** {shipment.get('capacity', '')}")
            st.write(f"**Nhà cung cấp:** {shipment.get('supplier', '')}")
            st.write(f"**Loại yêu cầu:** {shipment.get('request_type', '')}")
        
        with col2:
            st.write(f"**Trạng thái:** {shipment.get('status', '')}")
            sent_time_str = ""
            if shipment.get('sent_time'):
                try:
                    sent_time_str = pd.to_datetime(shipment.get('sent_time')).strftime('%d/%m/%Y %H:%M:%S')
                except:
                    sent_time_str = shipment.get('sent_time', '')
            st.write(f"**Ngày nhận:** {sent_time_str}")
            
            completed_time_str = ""
            if shipment.get('completed_time'):
                try:
                    completed_time_str = pd.to_datetime(shipment.get('completed_time')).strftime('%d/%m/%Y %H:%M:%S')
                except:
                    completed_time_str = shipment.get('completed_time', '')
            st.write(f"**Ngày trả:** {completed_time_str if completed_time_str else '-'}")
            
            # Thời gian cập nhật trạng thái
            last_updated_str = ""
            if shipment.get('last_updated'):
                try:
                    last_updated_str = pd.to_datetime(shipment.get('last_updated')).strftime('%d/%m/%Y %H:%M:%S')
                except:
                    last_updated_str = shipment.get('last_updated', '')
            
            # Box thời gian update
            st.markdown(f"""
            <div style="
                background: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 0.5rem;
                padding: 0.75rem;
                margin-top: 0.5rem;
            ">
                <strong style="color: #0369a1;">⏰ Thời gian cập nhật trạng thái:</strong><br>
                <span style="color: #1e40af; font-weight: 500;">{last_updated_str if last_updated_str else 'Chưa có'}</span>
            </div>
            """, unsafe_allow_html=True)
            
            st.write(f"**Cửa hàng:** {shipment.get('store_name', '') or '-'}")
            st.write(f"**Ghi chú:** {shipment.get('notes', '') or '-'}")
        
        # Show images if available
        if shipment.get('image_url'):
            st.subheader("Ảnh")
            image_urls = shipment['image_url'].split(';')
            for img_url in image_urls:
                if img_url.strip():
                    try:
                        st.image(img_url.strip(), width=300)
                    except:
                        st.write(f"Link ảnh: {img_url.strip()}")
        
        # Show audit log
        st.divider()
        st.subheader("Lịch sử thay đổi")
        audit_df = get_audit_log()
        if not audit_df.empty:
            audit_df = audit_df[audit_df['shipment_id'] == shipment_id]
            if not audit_df.empty:
                audit_df_display = audit_df[['timestamp', 'action', 'old_value', 'new_value', 'changed_by']].copy()
                audit_df_display = audit_df_display.sort_values('timestamp', ascending=False)
                st.dataframe(audit_df_display, use_container_width=True, hide_index=True)
            else:
                st.info("Chưa có lịch sử thay đổi cho phiếu này.")
        else:
            st.info("Chưa có lịch sử thay đổi.")


def show_audit_log():
    """Show audit log of all changes"""
    st.header("📋 Lịch Sử Thay Đổi")
    
    # Tự động xóa các bản ghi cũ khi vượt quá 100
    try:
        cleanup_result = cleanup_audit_log(max_rows=100)
        if cleanup_result['success'] and cleanup_result['deleted_count'] > 0:
            st.info(f"🗑️ Đã tự động xóa {cleanup_result['deleted_count']} bản ghi cũ (giữ lại 100 bản ghi mới nhất)")
    except Exception as e:
        print(f"Error cleaning up audit log: {e}")
    
    # Get audit log
    limit = st.slider("Số lượng bản ghi:", 10, 500, 100, 10)
    df = get_audit_log(limit=limit)
    
    if df.empty:
        st.info("📭 Chưa có lịch sử thay đổi")
        return
    
    # Display audit log
    st.dataframe(
        df,
        use_container_width=True,
        height=500,
        hide_index=True
    )
    
    # Export button
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Tải Excel (CSV)",
        data=csv,
        file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


def show_manage_shipments():
    """Show screen to manage all shipments with edit functionality"""
    ensure_label_defaults()
    st.header("📋 Quản Lý Phiếu Gửi Hàng")
    current_user = get_current_user()
    
    # Quick actions
    with st.expander("➕ Tạo phiếu (nhập tay)", expanded=False):
        st.write("Chuyển sang tab 'Quét QR' để tạo phiếu từ QR, hoặc dùng form dưới đây.")
        with st.form("manual_create_form"):
            qr = st.text_input("Mã QR Code *")
            imei = st.text_input("IMEI *")
            device_name = st.text_input("Tên thiết bị *")
            capacity = st.text_input("Lỗi / Tình trạng *")
            suppliers_df = get_suppliers()
            # Nếu tài khoản cửa hàng: khóa NCC (không chọn)
            store_user = is_store_user()
            if store_user:
                supplier = st.selectbox("Nhà cung cấp (khóa với cửa hàng)", ["(Cửa hàng không chọn NCC)"], index=0, disabled=True)
            else:
                supplier = st.selectbox("Nhà cung cấp", suppliers_df['name'].tolist() if not suppliers_df.empty else [])
            uploaded_image_manual = st.file_uploader("Upload ảnh (tùy chọn, chọn nhiều)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="upload_image_manual")
            
            # Trường cửa hàng
            store_name = None
            if store_user:
                store_name = get_store_name_from_username(current_user)
                store_input = st.text_input("Cửa hàng:", value=store_name, disabled=True)
            else:
                store_input = st.text_input("Cửa hàng (nếu có):", value="")
                if store_input.strip():
                    store_name = store_input.strip()
            
            # Loại yêu cầu (bắt buộc)
            request_type_manual = st.selectbox(
                "Loại yêu cầu *:",
                REQUEST_TYPES,
                key="request_type_manual",
                help="Chọn loại yêu cầu (bắt buộc)"
            )
            
            notes = st.text_area("Ghi chú")
            if st.form_submit_button("💾 Lưu phiếu mới", type="primary"):
                if not qr or not imei or not device_name or not capacity:
                    st.error("Vui lòng nhập đủ Mã QR, IMEI, Tên thiết bị, Lỗi/Tình trạng")
                elif not request_type_manual:
                    st.error("Vui lòng chọn Loại yêu cầu!")
                else:
                    image_url = None
                    if uploaded_image_manual:
                        urls = []
                        current_status = 'Đã nhận'  # Default status for new shipments
                        sanitized_qr = qr.strip().replace(" ", "_").replace("/", "_") or "qr_image"
                        sanitized_status = current_status.replace(" ", "_").replace("/", "_")
                        for idx, f in enumerate(uploaded_image_manual, start=1):
                            file_bytes = f.getvalue()
                            mime = f.type or "image/jpeg"
                            orig_name = f.name or "image.jpg"
                            ext = ""
                            if "." in orig_name:
                                ext = orig_name.split(".")[-1]
                            if not ext:
                                ext = "jpg"
                            # Tên file: mã QR + trạng thái + stt
                            drive_filename = f"{sanitized_qr}_{sanitized_status}_{idx}.{ext}"
                            upload_res = upload_file_to_drive(file_bytes, drive_filename, mime)
                            if upload_res['success']:
                                urls.append(upload_res['url'])
                                st.success(f"✅ Upload ảnh {idx} thành công: {upload_res['url'][:50]}...")
                            else:
                                st.error(f"❌ Upload ảnh {idx} thất bại: {upload_res['error']}")
                                st.stop()
                        if urls:
                            image_url = ";".join(urls)

                    # Tài khoản cửa hàng: mặc định Đã nhận
                    default_status = 'Đã nhận'
                    res = save_shipment(
                        qr.strip(), imei.strip(), device_name.strip(), capacity.strip(), 
                        supplier if not store_user else 'Cửa hàng', current_user, notes if notes else None,
                        status=default_status, store_name=store_name, image_url=image_url, request_type=request_type_manual
                    )
                    if res['success']:
                        st.success(f"Đã tạo phiếu #{res['id']}")
                        # Refresh list and metrics
                        st.rerun()
                    else:
                        st.error(f"Lỗi: {res['error']}")

    with st.expander("📂 Tạo nhiều phiếu từ Excel", expanded=False):
        st.write("Upload file Excel (bỏ qua header, đọc từ hàng 2) với các cột: B=Mã yêu cầu(QR), Z=Tên hàng (Tên thiết bị), AF=Serial/IMEI, AI=Ghi chú (Lỗi/Tình trạng).")
        suppliers_df = get_suppliers()
        supplier_options = ["Chưa chọn"] + (suppliers_df['name'].tolist() if not suppliers_df.empty else [])
        bulk_supplier = st.selectbox("Nhà cung cấp áp dụng", supplier_options, key="bulk_supplier")
        # Loại yêu cầu (bắt buộc)
        bulk_request_type = st.selectbox(
            "Loại yêu cầu *:",
            REQUEST_TYPES,
            key="bulk_request_type",
            help="Chọn loại yêu cầu (bắt buộc)"
        )
        uploaded_file = st.file_uploader("Chọn file Excel", type=["xlsx", "xls"], key="bulk_excel")
        if uploaded_file is not None:
            if st.button("Xử lý file", type="primary", key="bulk_process"):
                try:
                    df = pd.read_excel(uploaded_file, header=None)
                    # Column indices: B=1, Z=25, AF=31, AI=34 (0-based). Bỏ dòng 0 (header)
                    if df.shape[0] > 0:
                        df = df.iloc[1:]
                    needed_cols = {1: 'qr_code', 25: 'device_name', 31: 'imei', 34: 'capacity'}
                    missing_cols = [c for c in needed_cols if c >= df.shape[1]]
                    if missing_cols:
                        st.error("File không đủ cột cần thiết (B,Z,AF,AI).")
                    else:
                        df = df[list(needed_cols.keys())]
                        df.rename(columns=needed_cols, inplace=True)
                        success, fail = 0, 0
                        errors = []
                        for idx, row in df.iterrows():
                            qr_val = str(row.get('qr_code') or '').strip()
                            imei_val = str(row.get('imei') or '').strip()
                            device_val = str(row.get('device_name') or '').strip()
                            cap_val = str(row.get('capacity') or '').strip()
                            if not qr_val:
                                fail += 1
                                errors.append(f"Dòng {idx+1}: thiếu Mã QR")
                                continue
                            if not imei_val or not device_val or not cap_val:
                                fail += 1
                                errors.append(f"Dòng {idx+1}: thiếu IMEI/Tên/Lỗi-Tình trạng")
                                continue
                            # Xác định store_name nếu là user cửa hàng
                            store_user = is_store_user()
                            store_name = None
                            if store_user:
                                store_name = get_store_name_from_username(current_user)
                            
                            res = save_shipment(
                                qr_code=qr_val,
                                imei=imei_val,
                                device_name=device_val,
                                capacity=cap_val,
                                supplier=bulk_supplier if bulk_supplier != "Chưa chọn" else "Chưa chọn",
                                created_by=current_user,
                                notes=None,
                                status="Đã nhận",
                                store_name=store_name,
                                request_type=bulk_request_type
                            )
                            if res['success']:
                                success += 1
                            else:
                                fail += 1
                                errors.append(f"Dòng {idx+1}: {res['error']}")
                        st.success(f"Đã tạo {success} phiếu. Lỗi: {fail}.")
                        if errors:
                            with st.expander("Chi tiết lỗi", expanded=False):
                                for e in errors:
                                    st.write("- " + e)
                except Exception as e:
                    st.error(f"Lỗi đọc file: {e}")

    # Get all shipments
    df = get_all_shipments()
    
    if df.empty:
        st.info("📭 Chưa có phiếu gửi hàng nào")
        return
    
    # In-tem expander (giống như Tạo nhiều phiếu từ Excel)
    with st.expander("🖨️ In tem (chọn phiếu)", expanded=False):
        st.caption("Tìm kiếm theo mã QR/thiết bị/IMEI, chọn nhiều phiếu, sau đó bấm In.")
        all_options = df.apply(
            lambda r: {
                "id": r['id'],
                "label": f"{r['qr_code']} | {r['device_name']} | {r['imei']}"
            },
            axis=1
        ).tolist()

        search_term = st.text_input("Tìm mã QR / thiết bị / IMEI", key="label_search_term")
        if search_term:
            term = search_term.lower().strip()
            filtered_opts = [o for o in all_options if term in o['label'].lower()]
        else:
            filtered_opts = all_options

        option_labels = [o['label'] for o in filtered_opts]
        option_ids = [o['id'] for o in filtered_opts]

        selected_labels = st.multiselect(
            "Chọn phiếu:",
            options=option_labels,
            default=st.session_state.get('label_picker_selected', []),
            key="label_picker_multiselect"
        )

        # Persist selection
        st.session_state['label_picker_selected'] = selected_labels
        selected_ids = [option_ids[option_labels.index(lbl)] for lbl in selected_labels] if selected_labels else []

        st.write(f"Đã chọn: {len(selected_ids)} phiếu")
        col_lp1, col_lp2 = st.columns([1, 3])
        with col_lp1:
            if st.button("🖨️ In các phiếu đã chọn", key="label_picker_print", use_container_width=True):
                selected_shipments = df[df['id'].isin(selected_ids)].to_dict(orient='records')
                if selected_shipments:
                    st.success(f"Đang chuẩn bị {len(selected_shipments)} tem...")
                    render_labels_bulk(selected_shipments)
                else:
                    st.warning("Chưa chọn phiếu nào để in.")
        with col_lp2:
            st.write("")  # spacer

    with st.expander("🔎 Bộ lọc (trạng thái / NCC / QR)", expanded=False):
        col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
            filter_status = st.multiselect(
                "Trạng thái:",
                STATUS_VALUES,
                default=STATUS_VALUES,
                key="manage_filter_status"
            )
        
    with col2:
            suppliers_list = df['supplier'].unique().tolist()
            filter_supplier = st.multiselect(
                "NCC:",
                suppliers_list,
                default=suppliers_list,
                key="manage_filter_supplier"
            )
        
    with col3:
            search_qr = st.text_input("Mã QR:", key="search_qr")
    
    # Apply filters
    filtered_df = df[
        (df['status'].isin(filter_status)) &
        (df['supplier'].isin(filter_supplier))
    ]
    
    if search_qr:
        filtered_df = filtered_df[filtered_df['qr_code'].str.contains(search_qr, case=False, na=False)]
    
    # Display shipments
    st.subheader(f"Tổng số: {len(filtered_df)} phiếu")
    
    for idx, row in filtered_df.iterrows():
        with st.expander(f"{row['qr_code']} - {row['device_name']} ({row['status']})", expanded=False):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.write("**Thông tin phiếu:**")
            info_col1, info_col2 = st.columns(2)
            
            with info_col1:
                st.write(f"**Mã QR:** {row['qr_code']}")
                st.write(f"**IMEI:** {row['imei']}")
                st.write(f"**Tên thiết bị:** {row['device_name']}")
                st.write(f"**Lỗi / Tình trạng:** {row['capacity']}")
            
            with info_col2:
                st.write(f"**NCC:** {row['supplier']}")
                st.write(f"**Trạng thái:** {row['status']}")
                if pd.notna(row.get('store_name')) and row.get('store_name'):
                    st.write(f"**Cửa hàng:** {row['store_name']}")
                st.write(f"**Thời gian gửi:** {row['sent_time']}")
                if pd.notna(row['received_time']):
                    st.write(f"**Thời gian nhận:** {row['received_time']}")
                if pd.notna(row.get('last_updated')) and row.get('last_updated'):
                    st.write(f"**Cập nhật lúc:** {row['last_updated']}")
                st.write(f"**Người tạo:** {row['created_by']}")
                if pd.notna(row['updated_by']):
                    st.write(f"**Người cập nhật:** {row['updated_by']}")
            
            if pd.notna(row['notes']) and row['notes']:
                st.write(f"**Ghi chú:** {row['notes']}")

            # Print label button
            print_btn_key = f"print_label_{row['id']}"
            if st.button("🖨️ In tem QR", key=print_btn_key):
                st.session_state['label_preview_id'] = row['id']
            if st.session_state.get('label_preview_id') == row['id']:
                st.info("Xem trước tem. Bấm 'In tem' trong khung để in (chọn máy in/bkhổ giấy trong hộp thoại).")
                render_label_component(row)
            
        with col2:
            # Loại yêu cầu - hiển thị to rõ ở góc bên phải
            request_type = row.get('request_type', 'Chưa xác định')
            st.markdown(f"""
                <div style="
                margin-bottom: 1rem;
            ">
                <div style="font-size: 0.875rem; color: #6b7280; margin-bottom: 0.25rem;">Loại yêu cầu</div>
                <div style="font-size: 1.125rem; font-weight: 700; color: #3b82f6;">{request_type}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Image upload status
            if not row.get('image_url'):
                st.markdown("<span style='color:#b91c1c;font-weight:600'>Chưa upload ảnh</span>", unsafe_allow_html=True)
            else:
                # Hỗ trợ nhiều ảnh (phân tách bằng ';')
                urls = str(row.get('image_url') or '').split(';')
                urls = [u for u in urls if u.strip()]
                if urls:
                    for i, u in enumerate(urls):
                        display_drive_image(u, width=200, caption=f"Ảnh {i+1}")
            
            edit_key = f'edit_shipment_{row["id"]}'
            is_editing = st.session_state.get(edit_key, False)
            
            if st.button("✏️ Chỉnh sửa" if not is_editing else "❌ Hủy", key=f"btn_edit_{row['id']}"):
                st.session_state[edit_key] = not is_editing
                st.rerun()
        
        # Edit form
        if st.session_state.get(edit_key, False):
            st.divider()
            st.write("### ✏️ Chỉnh Sửa Phiếu")
            
            with st.form(f"edit_shipment_form_{row['id']}"):
                col_form1, col_form2 = st.columns(2)
                
                with col_form1:
                    edit_qr_code = st.text_input("Mã QR Code:", value=row['qr_code'], key=f"edit_qr_{row['id']}")
                    edit_imei = st.text_input("IMEI:", value=row['imei'], key=f"edit_imei_{row['id']}")
                    edit_device_name = st.text_input("Tên thiết bị:", value=row['device_name'], key=f"edit_device_{row['id']}")
                    edit_capacity = st.text_input("Lỗi / Tình trạng:", value=row['capacity'], key=f"edit_capacity_{row['id']}")
                
                with col_form2:
                    suppliers_df = get_suppliers()
                    current_supplier_idx = 0
                    if suppliers_df['name'].tolist():
                        try:
                            current_supplier_idx = suppliers_df['name'].tolist().index(row['supplier'])
                        except:
                            pass
                    
                    edit_supplier = st.selectbox(
                        "Nhà cung cấp:",
                        suppliers_df['name'].tolist(),
                        index=current_supplier_idx,
                        key=f"edit_supplier_{row['id']}"
                    )
                    
                    # Tạo danh sách trạng thái động (bao gồm "Gửi + tên NCC")
                    status_options = STATUS_VALUES.copy()
                    for _, supplier_row in suppliers_df.iterrows():
                        supplier_name = supplier_row['name']
                        send_status = f"Gửi {supplier_name}"
                        if send_status not in status_options:
                            status_options.append(send_status)
                    
                    current_status_idx = 0
                    if row['status'] in status_options:
                        current_status_idx = status_options.index(row['status'])
                    
                    edit_status = st.selectbox(
                        "Trạng thái:",
                        status_options,
                        index=current_status_idx,
                        key=f"edit_status_{row['id']}"
                    )
                    
                    # Loại yêu cầu
                    current_request_type = row.get('request_type', REQUEST_TYPES[0] if REQUEST_TYPES else '')
                    request_type_idx = 0
                    if current_request_type in REQUEST_TYPES:
                        request_type_idx = REQUEST_TYPES.index(current_request_type)
                    edit_request_type = st.selectbox(
                        "Loại yêu cầu:",
                        REQUEST_TYPES,
                        index=request_type_idx,
                        key=f"edit_request_type_{row['id']}"
                    )
                    
                    edit_store_name = st.text_input(
                        "Cửa hàng:",
                        value=row.get('store_name', '') if pd.notna(row.get('store_name')) else '',
                        key=f"edit_store_{row['id']}",
                        help="Tên cửa hàng (nếu có)"
                    )
                    
                    edit_notes = st.text_area("Ghi chú:", value=row['notes'] if pd.notna(row['notes']) else '', key=f"edit_notes_{row['id']}")
                    uploaded_image = st.file_uploader("Upload ảnh (tùy chọn, chọn nhiều)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key=f"upload_image_{row['id']}")
                
                col_submit1, col_submit2 = st.columns(2)
                with col_submit1:
                    if st.form_submit_button("💾 Lưu thay đổi", type="primary"):
                        current_user = get_current_user()

                        image_url = row.get('image_url')
                        if uploaded_image:
                            urls = []
                            for idx, f in enumerate(uploaded_image, start=1):
                                file_bytes = f.getvalue()
                                mime = f.type or "image/jpeg"
                                orig_name = f.name or "image.jpg"
                                ext = ""
                                if "." in orig_name:
                                    ext = orig_name.split(".")[-1]
                                if not ext:
                                    ext = "jpg"
                                    sanitized_qr = edit_qr_code.strip().replace(" ", "_").replace("/", "_") or "qr_image"
                                    sanitized_status = edit_status.replace(" ", "_").replace("/", "_") if edit_status else "unknown"
                                    # Tên file: mã QR + trạng thái + stt
                                    drive_filename = f"{sanitized_qr}_{sanitized_status}_{idx}.{ext}"
                                upload_res = upload_file_to_drive(file_bytes, drive_filename, mime)
                                if upload_res['success']:
                                    urls.append(upload_res['url'])
                                else:
                                    st.error(f"❌ Upload ảnh {idx} thất bại: {upload_res['error']}")
                                    st.stop()
                            if urls:
                                image_url = ";".join(urls)

                        result = update_shipment(
                            shipment_id=row['id'],
                            qr_code=edit_qr_code.strip(),
                            imei=edit_imei.strip(),
                            device_name=edit_device_name.strip(),
                            capacity=edit_capacity.strip(),
                            supplier=edit_supplier,
                            status=edit_status,
                            notes=edit_notes.strip() if edit_notes.strip() else None,
                            updated_by=current_user,
                            image_url=image_url,
                            store_name=edit_store_name.strip() if edit_store_name.strip() else None,
                            request_type=edit_request_type
                        )
                        
                        if result['success']:
                            st.success("✅ Đã cập nhật thành công!")
                            # Notify Telegram if status is one of: Đã nhận, Chuyển kho, Gửi NCC sửa, Chuyển cửa hàng
                            updated = get_shipment_by_qr_code(edit_qr_code.strip())
                            if updated and updated.get('status') in ['Đã nhận', 'Chuyển kho', 'Gửi NCC sửa', 'Chuyển cửa hàng']:
                                res = notify_shipment_if_received(
                                    updated['id'],
                                    force=not row.get('telegram_message_id'),
                                    is_update_image=(uploaded_image is not None)
                                )
                                if res and not res.get('success'):
                                    st.warning(f"Không gửi được Telegram: {res.get('error')}")
                            edit_key = f'edit_shipment_{row["id"]}'
                            if edit_key in st.session_state:
                                del st.session_state[edit_key]
                            st.rerun()
                        else:
                            st.error(f"❌ {result['error']}")
                
                with col_submit2:
                    if st.form_submit_button("❌ Hủy"):
                        edit_key = f'edit_shipment_{row["id"]}'
                        if edit_key in st.session_state:
                            del st.session_state[edit_key]
                        st.rerun()
        
            st.divider()


def show_dashboard():
    """Dashboard hiển thị phiếu theo loại yêu cầu với bộ lọc và phân trang - Thiết kế mới"""
    st.header("📊 Dashboard Quản Lý Sửa Chữa")
    
    # Khởi tạo session state cho dashboard
    if 'dashboard_request_type' not in st.session_state:
        st.session_state['dashboard_request_type'] = REQUEST_TYPES[0] if REQUEST_TYPES else ''
    if 'dashboard_detail_id' not in st.session_state:
        st.session_state['dashboard_detail_id'] = None
    
    # Tabs cho các loại yêu cầu
    tab_names = REQUEST_TYPES if REQUEST_TYPES else []
    if not tab_names:
        st.error("Chưa có loại yêu cầu nào được cấu hình")
        return
    
    tabs = st.tabs(tab_names)
    
    # Xác định tab được chọn dựa trên index tab được click
    # Streamlit tự động quản lý tab selection, ta chỉ cần lấy index
    selected_tab_idx = 0
    for idx, tab_name in enumerate(tab_names):
        if tab_name == st.session_state.get('dashboard_request_type', tab_names[0]):
            selected_tab_idx = idx
            break
    
    # Xử lý từng tab
    for tab_idx, (tab, request_type) in enumerate(zip(tabs, tab_names)):
        with tab:
            # Cập nhật request_type khi tab này được chọn (chỉ tab active mới chạy code này)
            page_key = f"dashboard_page_{request_type}"
            if st.session_state.get('dashboard_request_type') != request_type:
                st.session_state['dashboard_request_type'] = request_type
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1
            
            # Bộ lọc
            col_filter1, col_filter2, col_filter3 = st.columns([1, 1, 2])
            
            with col_filter1:
                status_options = ['Toàn bộ'] + STATUS_VALUES
                status_key = f"status_filter_{request_type}"
                if status_key not in st.session_state:
                    st.session_state[status_key] = 'Toàn bộ'
                
                current_status_idx = 0
                if st.session_state[status_key] in status_options:
                    current_status_idx = status_options.index(st.session_state[status_key])
                
                selected_status = st.selectbox(
                    "Trạng thái:",
                    status_options,
                    index=current_status_idx,
                    key=status_key
                )
                if selected_status != st.session_state[status_key]:
                    st.session_state[status_key] = selected_status
                    page_key = f"dashboard_page_{request_type}"
                    st.session_state[page_key] = 1
                    st.rerun()
            
            with col_filter2:
                time_options = ['Hôm nay', 'Tuần này', 'Tháng này', 'Toàn bộ']
                time_key = f"time_filter_{request_type}"
                if time_key not in st.session_state:
                    st.session_state[time_key] = 'Hôm nay'
                
                current_time_idx = 0
                if st.session_state[time_key] in time_options:
                    current_time_idx = time_options.index(st.session_state[time_key])
                
                selected_time = st.selectbox(
                    "Thời gian:",
                    time_options,
                    index=current_time_idx,
                    key=time_key
                )
                if selected_time != st.session_state[time_key]:
                    st.session_state[time_key] = selected_time
                    page_key = f"dashboard_page_{request_type}"
                    st.session_state[page_key] = 1
                    st.rerun()
            
            with col_filter3:
                st.write("")  # Spacer
            
            # Lấy dữ liệu
            df = get_all_shipments()
            
            if df.empty:
                st.info("📭 Chưa có phiếu nào")
                continue
            
            # Lọc theo loại yêu cầu
            filtered_df = df[df['request_type'] == request_type].copy()
            
            # Lọc theo trạng thái
            status_key = f"status_filter_{request_type}"
            selected_status = st.session_state.get(status_key, 'Toàn bộ')
            if selected_status != 'Toàn bộ':
                filtered_df = filtered_df[filtered_df['status'] == selected_status]
            
            # Lọc theo thời gian
            from datetime import datetime, timedelta
            now = datetime.now()
            
            time_key = f"time_filter_{request_type}"
            selected_time = st.session_state.get(time_key, 'Hôm nay')
            
            if selected_time == 'Hôm nay':
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                filtered_df = filtered_df[
                    pd.to_datetime(filtered_df['sent_time'], errors='coerce') >= today_start
                ]
            elif st.session_state['dashboard_time_filter'] == 'Tuần này':
                week_start = now - timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                filtered_df = filtered_df[
                    pd.to_datetime(filtered_df['sent_time'], errors='coerce') >= week_start
                ]
            elif selected_time == 'Tháng này':
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                filtered_df = filtered_df[
                    pd.to_datetime(filtered_df['sent_time'], errors='coerce') >= month_start
                ]
            # 'Toàn bộ' không cần lọc thêm
            
            # Sắp xếp theo last_updated (mới nhất trước)
            filtered_df['last_updated_parsed'] = pd.to_datetime(filtered_df['last_updated'], errors='coerce')
            filtered_df = filtered_df.sort_values('last_updated_parsed', ascending=False, na_position='last')
            
            # Phân trang: 10 phiếu mỗi trang
            items_per_page = 10
            total_items = len(filtered_df)
            total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 1
            
            # Nút điều hướng phân trang
            page_key = f"dashboard_page_{request_type}"
            if page_key not in st.session_state:
                st.session_state[page_key] = 1
            
            # Sử dụng page key riêng cho mỗi request type
            current_page = st.session_state[page_key]
            if current_page > total_pages:
                st.session_state[page_key] = total_pages
                current_page = total_pages
            if current_page < 1:
                st.session_state[page_key] = 1
                current_page = 1
            
            start_idx = (current_page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_df = filtered_df.iloc[start_idx:end_idx]
            
            # Hiển thị thông tin phân trang
            st.caption(f"Hiển thị {start_idx + 1}-{min(end_idx, total_items)} trong tổng số {total_items} phiếu")
            
            if total_pages > 1:
                col_page1, col_page2, col_page3 = st.columns([1, 2, 1])
                with col_page1:
                    if st.button("◀ Trước", key=f"prev_page_{request_type}", disabled=(st.session_state[page_key] <= 1)):
                        st.session_state[page_key] -= 1
                        st.rerun()
                with col_page2:
                    st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Trang {st.session_state[page_key]}/{total_pages}</div>", unsafe_allow_html=True)
                with col_page3:
                    if st.button("Sau ▶", key=f"next_page_{request_type}", disabled=(st.session_state[page_key] >= total_pages)):
                        st.session_state[page_key] += 1
                        st.rerun()
            
            # Hiển thị bảng dữ liệu - Thiết kế mới
            if page_df.empty:
                st.info("📭 Không có phiếu nào phù hợp với bộ lọc")
            else:
                # CSS cho dashboard mới
                st.markdown("""
                <style>
                .dashboard-list-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 1rem 0;
                    background: white;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                .dashboard-list-table th {
                    background: #4a90e2;
                    color: white;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 0.9rem;
                    border: 1px solid #3a7bc8;
                }
                .dashboard-list-table td {
                    padding: 10px 12px;
                    border: 1px solid #e5e7eb;
                    font-size: 0.875rem;
                }
                .dashboard-list-table tr:nth-child(even) {
                    background: #f9fafb;
                }
                .dashboard-list-table tr:hover {
                    background: #f3f4f6;
                }
                .selected-row {
                    background: #10b981 !important;
                    color: white;
                }
                .selected-row td {
                    color: white;
                    font-weight: 600;
                }
                .status-text {
                    font-weight: 600;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # Tạo bảng danh sách phiếu
                list_data = []
                for idx, row in page_df.iterrows():
                    qr_code = str(row.get('qr_code', ''))
                    row_id = row['id']
                    
                    # Thời gian (sent_time hoặc received_time)
                    time_str = ''
                    if pd.notna(row.get('sent_time')):
                        try:
                            time_str = pd.to_datetime(row['sent_time']).strftime('%d/%m/%Y %H:%M')
                        except:
                            time_str = str(row.get('sent_time', ''))[:16]
                    elif pd.notna(row.get('received_time')):
                        try:
                            time_str = pd.to_datetime(row['received_time']).strftime('%d/%m/%Y %H:%M')
                        except:
                            time_str = str(row.get('received_time', ''))[:16]
                    
                    # Khách hàng (mặc định "Khách lẻ" hoặc từ store_name)
                    customer = "Khách lẻ"
                    if pd.notna(row.get('store_name')) and row.get('store_name'):
                        customer = str(row.get('store_name', 'Khách lẻ'))
                    
                    # Khách cần trả và đã trả (mặc định 0)
                    need_pay = "0"
                    paid = "0"
                    
                    # Trạng thái
                    status = str(row.get('status', ''))
                    
                    list_data.append({
                        'id': row_id,
                        'qr_code': qr_code,
                        'time': time_str,
                        'customer': customer,
                        'need_pay': need_pay,
                        'paid': paid,
                        'status': status
                    })
                
                # Hiển thị bảng danh sách
                selected_detail_id = st.session_state.get('dashboard_detail_id')
                
                list_html = """
                <div style="overflow-x: auto;">
                <table class="dashboard-list-table" style="width: 100%;">
                    <thead>
                        <tr>
                            <th style="width: 5%;"></th>
                            <th style="width: 15%;">Mã yêu cầu</th>
                            <th style="width: 15%;">Thời gian</th>
                            <th style="width: 15%;">Khách hàng</th>
                            <th style="width: 12%;">Khách cần trả</th>
                            <th style="width: 12%;">Khách đã trả</th>
                            <th style="width: 26%;">Trạng thái</th>
                        </tr>
                    </thead>
                    <tbody>
                """
                
                for item in list_data:
                    row_class = 'selected-row' if item['id'] == selected_detail_id else ''
                    qr_escaped = html.escape(item['qr_code'])
                    time_escaped = html.escape(item['time'])
                    customer_escaped = html.escape(item['customer'])
                    status_escaped = html.escape(item['status'])
                    
                    list_html += f"""
                        <tr class="{row_class}">
                            <td><input type="checkbox"></td>
                            <td>{qr_escaped}</td>
                            <td>{time_escaped}</td>
                            <td>{customer_escaped}</td>
                            <td>{item['need_pay']}</td>
                            <td>{item['paid']}</td>
                            <td class="status-text">{status_escaped}</td>
                        </tr>
                    """
                
                list_html += """
                    </tbody>
                </table>
                </div>
                """
                
                st.markdown(list_html, unsafe_allow_html=True)
                
                # Tạo nút click cho từng mã QR
                st.write("**Nhấn vào mã QR để xem chi tiết:**")
                num_cols = min(len(list_data), 5)
                if num_cols > 0:
                    qr_cols = st.columns(num_cols)
                    for col_idx, item in enumerate(list_data):
                        with qr_cols[col_idx % num_cols]:
                            qr_btn_key = f"qr_btn_{item['id']}_{request_type}"
                            if st.button(
                                item['qr_code'],
                                key=qr_btn_key,
                                use_container_width=True,
                                type="primary" if item['id'] == selected_detail_id else "secondary"
                            ):
                                if st.session_state.get('dashboard_detail_id') == item['id']:
                                    # Nếu đã chọn, bỏ chọn
                                    st.session_state['dashboard_detail_id'] = None
                                else:
                                    # Chọn phiếu mới
                                    st.session_state['dashboard_detail_id'] = item['id']
                                st.rerun()
                
                # Hiển thị chi tiết nếu có phiếu được chọn
                if selected_detail_id:
                    detail_shipment = get_shipment_by_id(selected_detail_id)
                    
                    if detail_shipment:
                        # Header xanh lá với thông tin phiếu được chọn
                        st.markdown(f"""
                        <div style="background: #10b981; color: white; padding: 12px; border-radius: 8px; margin: 16px 0;">
                            <div style="display: flex; align-items: center; gap: 16px;">
                                <input type="checkbox" checked style="width: 20px; height: 20px;">
                                <span style="font-weight: 700; font-size: 1.1rem;">{html.escape(detail_shipment.get('qr_code', ''))}</span>
                                <span>{html.escape(list_data[0]['time'] if list_data else '')}</span>
                                <span>{html.escape(list_data[0]['customer'] if list_data else 'Khách lẻ')}</span>
                                <span style="margin-left: auto;">0</span>
                                <span>0</span>
                                <span>{html.escape(detail_shipment.get('status', ''))}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Tab "Thông tin"
                        info_tab = st.tabs(["Thông tin"])[0]
                        with info_tab:
                            col_info1, col_info2, col_info3 = st.columns([2, 2, 2])
                            
                            with col_info1:
                                st.write(f"**Mã yêu cầu:** {detail_shipment.get('qr_code', '')}")
                                time_display = ''
                                if pd.notna(detail_shipment.get('sent_time')):
                                    try:
                                        time_display = pd.to_datetime(detail_shipment['sent_time']).strftime('%d/%m/%Y %H:%M')
                                    except:
                                        time_display = str(detail_shipment.get('sent_time', ''))[:16]
                                st.write(f"**Thời gian:** {time_display}")
                                st.write(f"**Ngày cập nhật:** {detail_shipment.get('last_updated', '')[:16] if detail_shipment.get('last_updated') else ''}")
                                st.write(f"**Người nhận:** {detail_shipment.get('created_by', '')}")
                                st.write(f"**Chi nhánh:** {detail_shipment.get('store_name', 'Chưa có')}")
                            
                            with col_info2:
                                customer_display = "Khách lẻ"
                                if detail_shipment.get('store_name'):
                                    customer_display = detail_shipment.get('store_name')
                                st.write(f"**Khách hàng:** {customer_display}")
                                st.write(f"**Bảng giá:** Bảng giá chung")
                                st.write(f"**Trạng thái:** {detail_shipment.get('status', '')}")
                                st.write(f"**Nơi tiếp nhận:** Tại cửa hàng")
                            
                            with col_info3:
                                st.text_area("Ghi chú", value=detail_shipment.get('notes', '') or '', height=150, key=f"notes_{selected_detail_id}")
                        
                        # Bảng chi tiết item
                        st.markdown("### Chi tiết sản phẩm")
                        item_table_data = [{
                            'Mã hàng': detail_shipment.get('qr_code', ''),
                            'Tên hàng': detail_shipment.get('device_name', ''),
                            'IMEI': detail_shipment.get('imei', ''),
                            'Ghi chú hàng yêu cầu': detail_shipment.get('capacity', ''),
                            'Số lượng': '1',
                            'Trạng thái sửa chữa': detail_shipment.get('status', ''),
                            'Ngày hoàn thành': detail_shipment.get('completed_time', '')[:10] if detail_shipment.get('completed_time') else '',
                            'Tổng phí': '0'
                        }]
                        
                        item_df = pd.DataFrame(item_table_data)
                        st.dataframe(item_df, use_container_width=True, hide_index=True)
                        
                        # Tổng kết
                        col_sum1, col_sum2 = st.columns([3, 1])
                        with col_sum1:
                            st.write("**Tổng số lượng:** 1")
                            st.write("**Tổng tiền hàng:** 0")
                            st.write("**Giảm giá đơn hàng:** 0")
                            st.write("**Khách cần trả:** 0")
                            st.write("**Khách đã trả:** 0")
                            st.write("**Còn cần trả:** 0")
                        
                        with col_sum2:
                            if st.button("Xuất file", key=f"export_{selected_detail_id}", use_container_width=True):
                                st.info("Chức năng xuất file đang được phát triển")
                        
                        # Form cập nhật trạng thái
                        st.divider()
                        st.subheader("Cập nhật trạng thái")
                        
                        col_update1, col_update2 = st.columns([2, 1])
                        
                        with col_update1:
                            current_status = detail_shipment.get('status', '')
                            status_options = STATUS_VALUES.copy()
                            suppliers_df = get_suppliers()
                            for _, supplier_row in suppliers_df.iterrows():
                                supplier_name = supplier_row['name']
                                send_status = f"Gửi {supplier_name}"
                                if send_status not in status_options:
                                    status_options.append(send_status)
                            
                            current_status_idx = 0
                            if current_status in status_options:
                                current_status_idx = status_options.index(current_status)
                            
                            new_status = st.selectbox(
                                "Trạng thái mới:",
                                status_options,
                                index=current_status_idx,
                                key=f"update_status_{selected_detail_id}"
                            )
                            
                            update_notes = st.text_area(
                                "Ghi chú cập nhật:",
                                value="",
                                key=f"update_notes_{selected_detail_id}",
                                height=100
                            )
                            
                            uploaded_image_detail = st.file_uploader(
                                "Upload ảnh (tùy chọn)",
                                type=["png", "jpg", "jpeg"],
                                accept_multiple_files=True,
                                key=f"upload_image_detail_{selected_detail_id}"
                            )
                            
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button("💾 Cập nhật", key=f"update_btn_{selected_detail_id}", type="primary", use_container_width=True):
                                    current_user = get_current_user()
                                    
                                    image_url = detail_shipment.get('image_url')
                                    if uploaded_image_detail:
                                        urls = []
                                        for idx, f in enumerate(uploaded_image_detail, start=1):
                                            file_bytes = f.getvalue()
                                            mime = f.type or "image/jpeg"
                                            orig_name = f.name or "image.jpg"
                                            ext = ""
                                            if "." in orig_name:
                                                ext = orig_name.split(".")[-1]
                                            if not ext:
                                                ext = "jpg"
                                            sanitized_qr = detail_shipment.get('qr_code', '').strip().replace(" ", "_").replace("/", "_") or "qr_image"
                                            sanitized_status = new_status.replace(" ", "_").replace("/", "_") if new_status else "unknown"
                                            drive_filename = f"{sanitized_qr}_{sanitized_status}_{idx}.{ext}"
                                            upload_res = upload_file_to_drive(file_bytes, drive_filename, mime)
                                            if upload_res['success']:
                                                urls.append(upload_res['url'])
                                            else:
                                                st.error(f"❌ Upload ảnh {idx} thất bại: {upload_res['error']}")
                                                st.stop()
                                        if urls:
                                            if image_url:
                                                image_url = f"{image_url};{';'.join(urls)}"
                                            else:
                                                image_url = ";".join(urls)
                                    
                                    result = update_shipment(
                                        shipment_id=selected_detail_id,
                                        status=new_status,
                                        notes=update_notes.strip() if update_notes.strip() else detail_shipment.get('notes'),
                                        updated_by=current_user,
                                        image_url=image_url
                                    )
                                    
                                    if result['success']:
                                        st.success("✅ Đã cập nhật thành công!")
                                        updated = get_shipment_by_id(selected_detail_id)
                                        if updated and updated.get('status') in ['Đã nhận', 'Chuyển kho', 'Gửi NCC sửa', 'Chuyển cửa hàng']:
                                            res = notify_shipment_if_received(
                                                selected_detail_id,
                                                force=not detail_shipment.get('telegram_message_id'),
                                                is_update_image=(uploaded_image_detail is not None)
                                            )
                                            if res and not res.get('success'):
                                                st.warning(f"Không gửi được Telegram: {res.get('error')}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {result['error']}")
                            
                            with col_btn2:
                                if st.button("❌ Đóng", key=f"close_detail_{selected_detail_id}", use_container_width=True):
                                    st.session_state['dashboard_detail_id'] = None
                                    st.rerun()
                        
                        with col_update2:
                            # Hiển thị ảnh nếu có
                            if detail_shipment.get('image_url'):
                                st.write("**Ảnh đính kèm:**")
                                urls = str(detail_shipment.get('image_url', '')).split(';')
                                urls = [u for u in urls if u.strip()]
                                for i, u in enumerate(urls):
                                    display_drive_image(u, width=200, caption=f"Ảnh {i+1}")


def show_settings_screen():
    """Show settings screen for admin to manage suppliers"""
    if not is_admin():
        st.error("❌ Chỉ có quyền admin mới có thể truy cập trang này!")
        return
        
    st.header("⚙️ Cài Đặt")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📋 Danh Sách NCC", "➕ Thêm NCC Mới", "☁️ Google Sheets", "🔑 Tài Khoản", "🖨️ In tem", "🗑️ Database"])
    
    with tab1:
        show_suppliers_list()
    
    with tab2:
        show_add_supplier_form()
    
    with tab3:
        show_google_sheets_settings()

    with tab4:
        show_user_management()

    with tab5:
        show_label_settings()
    
    with tab6:
        show_database_management()


def show_suppliers_list():
    """Show list of all suppliers with edit/delete options"""
    st.subheader("📋 Danh Sách Nhà Cung Cấp")
    
    # Get all suppliers
    df = get_all_suppliers()
    
    if df.empty:
        st.info("📭 Chưa có nhà cung cấp nào trong hệ thống")
        return
    
    # Display suppliers
    for idx, row in df.iterrows():
        col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
        
        with col1:
            status_icon = "✅" if row['is_active'] else "❌"
            st.write(f"**{status_icon} {row['name']}**")
        
        with col2:
            st.write(f"📞 {row['contact'] or 'N/A'}")
        
        with col3:
            st.write(f"📍 {row['address'] or 'N/A'}")
        
        with col4:
            if st.button("✏️ Sửa", key=f"edit_{row['id']}"):
                st.session_state[f'edit_supplier_{row["id"]}'] = True
                st.rerun()
        
        with col5:
            if row['is_active']:
                if st.button("🗑️ Xóa", key=f"delete_{row['id']}"):
                    result = delete_supplier(row['id'])
                    if result['success']:
                        st.success(f"✅ Đã xóa nhà cung cấp: {row['name']}")
                        st.rerun()
                    else:
                        st.error(f"❌ {result['error']}")
            else:
                if st.button("♻️ Khôi phục", key=f"restore_{row['id']}"):
                    result = update_supplier(row['id'], is_active=True)
                    if result['success']:
                        st.success(f"✅ Đã khôi phục nhà cung cấp: {row['name']}")
                        st.rerun()
                    else:
                        st.error(f"❌ {result['error']}")
        
        # Edit form (if edit button clicked)
        if st.session_state.get(f'edit_supplier_{row["id"]}', False):
            with st.expander(f"✏️ Sửa thông tin: {row['name']}", expanded=True):
                with st.form(f"edit_form_{row['id']}"):
                    new_name = st.text_input("Tên nhà cung cấp:", value=row['name'], key=f"edit_name_{row['id']}")
                    new_contact = st.text_input("Liên hệ:", value=row['contact'] or '', key=f"edit_contact_{row['id']}")
                    new_address = st.text_input("Địa chỉ:", value=row['address'] or '', key=f"edit_address_{row['id']}")
                    new_active = st.checkbox("Đang hoạt động", value=bool(row['is_active']), key=f"edit_active_{row['id']}")
                    
                    col_submit1, col_submit2 = st.columns(2)
                    with col_submit1:
                        if st.form_submit_button("💾 Lưu thay đổi", type="primary"):
                            result = update_supplier(
                                row['id'],
                                name=new_name.strip() if new_name.strip() else None,
                                contact=new_contact.strip() if new_contact.strip() else None,
                                address=new_address.strip() if new_address.strip() else None,
                                is_active=new_active
                            )
                            if result['success']:
                                st.success("✅ Đã cập nhật thành công!")
                                st.session_state[f'edit_supplier_{row["id"]}'] = False
                                st.rerun()
                            else:
                                st.error(f"❌ {result['error']}")
                    
                    with col_submit2:
                        if st.form_submit_button("❌ Hủy"):
                            st.session_state[f'edit_supplier_{row["id"]}'] = False
            st.rerun()
        
        st.divider()


def show_add_supplier_form():
    """Show form to add new supplier"""
    st.subheader("➕ Thêm Nhà Cung Cấp Mới")
    
    with st.form("add_supplier_form"):
        name = st.text_input("Tên nhà cung cấp *", help="Tên nhà cung cấp (bắt buộc)")
        contact = st.text_input("Liên hệ", help="Số điện thoại hoặc email")
        address = st.text_input("Địa chỉ", help="Địa chỉ nhà cung cấp")
        
        if st.form_submit_button("➕ Thêm Nhà Cung Cấp", type="primary"):
            if not name.strip():
                st.error("❌ Vui lòng nhập tên nhà cung cấp!")
            else:
                result = add_supplier(
                    name=name.strip(),
                    contact=contact.strip() if contact.strip() else None,
                    address=address.strip() if address.strip() else None
                )
                
                if result['success']:
                    st.success(f"✅ Đã thêm nhà cung cấp: {name} (ID: {result['id']})")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")


def show_user_management():
    """Allow admin to create/update user passwords"""
    st.subheader("🔑 Quản Lý Tài Khoản")

    # --- Store management ---
    with st.expander("🏪 Tạo / xem danh sách Cửa hàng", expanded=False):
        store_tab1, store_tab2 = st.columns([1, 1])
        with store_tab1:
            with st.form("add_store_form"):
                store_name = st.text_input("Tên cửa hàng *", help="Ví dụ: Kho Chính, Xô Viết, Quận 1")
                store_address = st.text_input("Địa chỉ (tuỳ chọn)")
                store_note = st.text_area("Ghi chú (tuỳ chọn)", height=80)
                if st.form_submit_button("➕ Tạo cửa hàng", type="primary"):
                    if not store_name.strip():
                        st.error("❌ Vui lòng nhập tên cửa hàng")
                    else:
                        res = create_store(store_name.strip(), store_address.strip() if store_address else None, store_note.strip() if store_note else None)
                        if res['success']:
                            st.success(f"✅ Đã tạo cửa hàng: {store_name}")
                            st.rerun()
                        else:
                            st.error(f"❌ {res['error']}")
        with store_tab2:
            stores_df = get_all_stores()
            if stores_df.empty:
                st.info("Chưa có cửa hàng nào.")
            else:
                st.dataframe(
                    stores_df[['name', 'address', 'note', 'created_at']],
                    use_container_width=True,
                    hide_index=True,
                    height=220
                )

    with st.form("user_form"):
        username = st.text_input("Tên đăng nhập *", help="Ví dụ: admin, user, staff, cuahang1")
        password = st.text_input("Mật khẩu mới *", type="password")
        confirm = st.text_input("Nhập lại mật khẩu *", type="password")
        
        stores_df = get_all_stores()
        store_names = ["Không gán"] + stores_df['name'].tolist() if not stores_df.empty else ["Không gán"]
        store_choice = st.selectbox("Gán vào cửa hàng", store_names)
        
        col_check1, col_check2 = st.columns(2)
        with col_check1:
            is_admin_flag = st.checkbox("Cấp quyền admin", value=False)
        with col_check2:
            # Nếu chọn cửa hàng thì tự động coi là tài khoản cửa hàng
            is_store_flag = st.checkbox("Cấp quyền cửa hàng", value=(store_choice != "Không gán"), help="Tài khoản này sẽ có quyền cửa hàng")
            if store_choice != "Không gán" and not is_store_flag:
                st.warning("Đã chọn cửa hàng, tài khoản sẽ được coi là cửa hàng.")
                is_store_flag = True

        submitted = st.form_submit_button("💾 Lưu tài khoản", type="primary")
        if submitted:
            if not username.strip():
                st.error("❌ Vui lòng nhập tên đăng nhập")
            elif not password:
                st.error("❌ Vui lòng nhập mật khẩu")
            elif password != confirm:
                st.error("❌ Mật khẩu nhập lại không khớp")
            else:
                assigned_store = None if store_choice == "Không gán" else store_choice
                result = set_user_password(username.strip(), password, is_admin_flag, is_store_flag, assigned_store)
                if result['success']:
                    store_msg = f" (Cửa hàng: {assigned_store})" if assigned_store else ""
                    admin_msg = " (Admin)" if is_admin_flag else ""
                    st.success(f"✅ Đã lưu tài khoản thành công{admin_msg}{store_msg}")
                else:
                    st.error(f"❌ {result['error']}")

    st.divider()
    st.subheader("📋 Danh sách tài khoản")
    users_df = get_all_users()
    if users_df.empty:
        st.info("📭 Chưa có tài khoản nào")
        return

    # Hide real password, show masked
    users_df = users_df.copy()
    users_df['password'] = users_df['password'].apply(lambda x: '******' if x else '')
    users_df['is_admin'] = users_df['is_admin'].apply(lambda x: "Admin" if x else "User")
    
    # Format is_store column
    if 'is_store' in users_df.columns:
        users_df['is_store'] = users_df['is_store'].apply(lambda x: "Cửa hàng" if x else "Không")
    else:
        users_df['is_store'] = "Không"

    if 'store_name' in users_df.columns:
        users_df.rename(columns={'store_name': 'Cửa hàng'}, inplace=True)
    else:
        users_df['Cửa hàng'] = ""

    st.dataframe(
        users_df,
        use_container_width=True,
        hide_index=True
    )

    st.divider()
    st.subheader("✏️ Chỉnh sửa / 🗑️ Xóa tài khoản")
    if users_df.empty:
        st.info("📭 Chưa có tài khoản nào để chỉnh sửa")
        return

    selected_user = st.selectbox("Chọn tài khoản", users_df['username'].tolist(), key="edit_user_select")
    
    with st.expander("🗑️ Xóa tài khoản", expanded=False):
        if selected_user == 'admin':
            st.info("Không thể xoá tài khoản admin.")
        delete_confirm = st.checkbox("Tôi muốn xoá tài khoản này", key="delete_user_confirm")
        if st.button("🗑️ Xoá tài khoản", type="secondary", disabled=(selected_user == 'admin' or not delete_confirm)):
            res = delete_user(selected_user)
            if res['success']:
                st.success(f"Đã xoá tài khoản {selected_user}")
                st.rerun()
            else:
                st.error(f"❌ {res['error']}")

    user_info = get_user(selected_user)
    if not user_info:
        st.error("Không lấy được thông tin tài khoản.")
        return
        
    with st.expander(f"✏️ Chỉnh sửa tài khoản: **{selected_user}**", expanded=False):
        with st.form("edit_user_form"):
            st.write(f"Đang chỉnh sửa: **{selected_user}**")
            new_password = st.text_input("Mật khẩu mới (bỏ trống nếu không đổi)", type="password")

            stores_df = get_all_stores()
            store_names = ["Không gán"] + stores_df['name'].tolist() if not stores_df.empty else ["Không gán"]
            current_store = user_info.get('store_name') or "Không gán"
            if current_store not in store_names:
                store_names.append(current_store)
            store_choice_edit = st.selectbox("Gán vào cửa hàng", store_names, index=store_names.index(current_store))

            col_flags1, col_flags2 = st.columns(2)
            with col_flags1:
                is_admin_flag_edit = st.checkbox("Cấp quyền admin", value=bool(user_info.get('is_admin')))
            with col_flags2:
                is_store_flag_edit = st.checkbox("Cấp quyền cửa hàng", value=bool(user_info.get('is_store')) or store_choice_edit != "Không gán")
                if store_choice_edit != "Không gán" and not is_store_flag_edit:
                    st.warning("Đã chọn cửa hàng, tài khoản sẽ được coi là cửa hàng.")
                    is_store_flag_edit = True

            if st.form_submit_button("💾 Lưu thay đổi", type="primary"):
                pwd_to_save = new_password if new_password else user_info.get('password')
                assigned_store = None if store_choice_edit == "Không gán" else store_choice_edit
                res = set_user_password(
                    selected_user,
                    pwd_to_save,
                    is_admin=is_admin_flag_edit,
                    is_store=is_store_flag_edit,
                    store_name=assigned_store
                )
                if res['success']:
                    st.success("✅ Đã cập nhật tài khoản")
                    st.rerun()
                else:
                    st.error(f"❌ {res['error']}")


def show_database_management():
    """Database management - chỉ admin mới có quyền"""
    st.subheader("🗑️ Quản Lý Database")
    
    st.warning("⚠️ **CẢNH BÁO:** Chức năng này sẽ xóa TOÀN BỘ dữ liệu trong database!")
    
    # Hiển thị thống kê database hiện tại
    st.markdown("### Thống kê Database hiện tại")
    
    try:
        df_shipments = get_all_shipments()
        df_transfers = get_all_transfer_slips()
        df_suppliers = get_all_suppliers()
        df_users = get_all_users()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Số phiếu gửi hàng", len(df_shipments))
        with col2:
            st.metric("Số phiếu chuyển", len(df_transfers))
        with col3:
            st.metric("Số nhà cung cấp", len(df_suppliers))
        with col4:
            st.metric("Số tài khoản", len(df_users))
    except Exception as e:
        st.error(f"Lỗi khi lấy thống kê: {str(e)}")
    
    st.divider()
    
    # Form xóa database
    st.markdown("### Xóa toàn bộ dữ liệu")
    
    st.error("""
    **⚠️ CẢNH BÁO NGHIÊM TRỌNG:**
    - Hành động này sẽ xóa **TẤT CẢ** dữ liệu trong database
    - Bao gồm: tất cả phiếu gửi hàng, phiếu chuyển, lịch sử thay đổi
    - Dữ liệu đã xóa **KHÔNG THỂ KHÔI PHỤC**
    - Chỉ giữ lại cấu trúc bảng và dữ liệu mặc định (users, suppliers)
    """)
    
    # Xác nhận kép
    confirm_text = st.text_input(
        "Nhập 'XÓA TẤT CẢ' để xác nhận:",
        key="confirm_delete_db",
        help="Phải nhập chính xác 'XÓA TẤT CẢ' (chữ hoa) để xác nhận"
    )
    
    if confirm_text == "XÓA TẤT CẢ":
        st.error("⚠️ Bạn đã xác nhận muốn xóa toàn bộ dữ liệu!")
        
        if st.button("🗑️ XÓA TOÀN BỘ DATABASE", type="primary", key="delete_db_btn"):
            with st.spinner("Đang xóa dữ liệu..."):
                result = clear_all_data()
                
                if result['success']:
                    st.success("✅ Đã xóa toàn bộ dữ liệu thành công!")
                    st.info("Database đã được khôi phục về trạng thái ban đầu với dữ liệu mặc định.")
                    st.balloons()
                    # Clear session state để reload
                    for key in list(st.session_state.keys()):
                        if key != 'username':  # Giữ lại thông tin đăng nhập
                            del st.session_state[key]
                    st.rerun()
                else:
                    st.error(f"❌ Lỗi khi xóa database: {result['error']}")
    else:
        if confirm_text:
            st.warning("Vui lòng nhập chính xác 'XÓA TẤT CẢ' (chữ hoa) để xác nhận")


def show_google_sheets_settings():
    """Show Google Sheets settings and test connection"""
    st.subheader("☁️ Cài Đặt Google Sheets")
    
    st.info("""
    **Hướng dẫn:**
    1. Đảm bảo file `service_account.json` đã được cấu hình đúng
    2. Google Sheet đã được chia sẻ với service account email
    3. Click nút "Kiểm tra kết nối" để test
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Kiểm tra kết nối", type="primary", key="test_gs_connection"):
            with st.spinner("Đang kiểm tra kết nối Google Sheets..."):
                result = test_connection()
                if result['success']:
                    st.success(f"✅ {result['message']}")
                    if 'worksheet' in result:
                        st.info(f"📋 Worksheet: {result['worksheet']}")
                else:
                    st.error(f"❌ {result['message']}")
    
    with col2:
        st.write("")  # Spacing
    
    st.divider()
    
    # Push all data option
    st.subheader("📤 Push dữ liệu")
    
    col_push1, col_push2 = st.columns(2)
    
    with col_push1:
        push_mode = st.radio(
            "Chế độ push:",
            ["Thêm mới (Append)", "Thay thế toàn bộ (Replace)"],
            key="push_mode"
        )
    
    with col_push2:
        st.write("")  # Spacing
    
    if st.button("📤 Push tất cả dữ liệu lên Google Sheets", type="primary", key="push_all_data"):
        with st.spinner("Đang push tất cả dữ liệu lên Google Sheets..."):
            df = get_all_shipments()
            if df.empty:
                st.warning("⚠️ Không có dữ liệu để push")
            else:
                append_mode = (push_mode == "Thêm mới (Append)")
                result = push_shipments_to_sheets(df, append_mode=append_mode)
                if result['success']:
                    st.success(f"✅ {result['message']}")
                    st.balloons()
                else:
                    st.error(f"❌ {result['message']}")


def show_transfer_slip_screen():
    """Screen for scanning QR codes and adding to transfer slip"""
    current_user = get_current_user()
    st.header("Phiếu Chuyển")
    
    tab1, tab2 = st.tabs(["Quét & Thêm Máy", "Quản Lý Phiếu Chuyển"])
    
    with tab1:
        show_transfer_slip_scan(current_user)
    
    with tab2:
        show_manage_transfer_slips()


def show_transfer_slip_scan(current_user):
    """Screen for scanning QR codes and adding to transfer slip"""
    # Get or create active transfer slip
    active_slip = get_active_transfer_slip(current_user)
    
    if not active_slip:
        if st.button("Tạo Phiếu Chuyển Mới", type="primary"):
            result = create_transfer_slip(current_user)
            if result['success']:
                st.success(f"Đã tạo phiếu chuyển: {result['transfer_code']}")
                st.rerun()
            else:
                st.error(f"Lỗi: {result['error']}")
        return
    
    transfer_slip_id = active_slip['id']
    transfer_code = active_slip['transfer_code']
    
    st.info(f"**Phiếu chuyển đang hoạt động:** {transfer_code}")
    
    # Get items in transfer slip
    items_df = get_transfer_slip_items(transfer_slip_id)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Quét QR để thêm máy vào phiếu")
        
        # Camera for scanning
        if 'show_camera_transfer' not in st.session_state:
            st.session_state['show_camera_transfer'] = False
        
        if st.button("Bắt đầu quét", type="primary", key="start_scan_transfer"):
            st.session_state['show_camera_transfer'] = True
            st.rerun()
        
        if st.session_state['show_camera_transfer']:
            if st.button("Dừng quét", key="stop_scan_transfer"):
                st.session_state['show_camera_transfer'] = False
                st.rerun()
            
            picture = st.camera_input("Quét mã QR", key="transfer_camera")
            
            if picture is not None:
                with st.spinner("Đang xử lý..."):
                    try:
                        image = Image.open(picture)
                        qr_text = decode_qr_from_image(image)
                        
                        if qr_text:
                            # Chỉ lấy mã QR (toàn bộ chuỗi quét được)
                            qr_code = qr_text.strip()
                            
                            if qr_code:
                                # Find shipment
                                shipment = get_shipment_by_qr_code(qr_code)
                                if shipment:
                                    # Add to transfer slip
                                    result = add_shipment_to_transfer_slip(transfer_slip_id, shipment['id'])
                                    if result['success']:
                                        st.success(f"Đã thêm máy {qr_code} vào phiếu chuyển")
                                        st.rerun()
                                    else:
                                        st.error(f"Lỗi: {result['error']}")
                                else:
                                    st.warning(f"Không tìm thấy phiếu với mã QR: {qr_code}")
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")
    
    with col2:
        st.subheader(f"Danh sách máy ({len(items_df)} máy)")
        
        if not items_df.empty:
            for idx, row in items_df.iterrows():
                st.write(f"• {row['qr_code']} - {row['device_name']}")
        
        # Show image if transfer slip has one
        # Chỉ tải ảnh khi đang xem phiếu chuyển này
        if active_slip.get('image_url'):
            st.divider()
            st.subheader("Ảnh phiếu chuyển")
            display_drive_image(active_slip['image_url'], width=250, caption="Ảnh phiếu chuyển")
        
        st.divider()
        
        # Batch update status for all items in transfer slip
        if len(items_df) > 0:
            st.subheader("Cập nhật trạng thái hàng loạt")
            
            batch_status = st.selectbox(
                "Trạng thái mới cho tất cả máy trong phiếu:",
                STATUS_VALUES,
                index=STATUS_VALUES.index('Đã nhận') if 'Đã nhận' in STATUS_VALUES else 0,
                key="batch_status"
            )
            
            if st.button("✅ Cập nhật tất cả thành 'Đã nhận'", type="primary", key="batch_receive"):
                current_user = get_current_user()
                success_count = 0
                error_count = 0
                
                for idx, row in items_df.iterrows():
                    result = update_shipment_status(
                        qr_code=row['qr_code'],
                        new_status='Đã nhận',
                        updated_by=current_user,
                        notes=f"Cập nhật từ phiếu chuyển {transfer_code}"
                    )
                    if result['success']:
                        success_count += 1
                    else:
                        error_count += 1
                
                if success_count > 0:
                    st.success(f"✅ Đã cập nhật {success_count} phiếu thành 'Đã nhận'")
                    if error_count > 0:
                        st.warning(f"⚠️ {error_count} phiếu cập nhật thất bại")
                    st.rerun()
                else:
                    st.error(f"❌ Không thể cập nhật phiếu nào")

    st.divider()
    st.subheader("Hoàn thành phiếu chuyển")
    
    new_status = st.selectbox(
        "Trạng thái mới cho các máy khi hoàn thành:",
        STATUS_VALUES,
        index=STATUS_VALUES.index('Chuyển kho') if 'Chuyển kho' in STATUS_VALUES else 0,
        key="transfer_status"
    )
    
    uploaded_image = st.file_uploader("Upload ảnh phiếu chuyển", type=["png", "jpg", "jpeg"], key="transfer_image")
    
    notes = st.text_area("Ghi chú", key="transfer_notes")
    
    if st.button("Hoàn thành phiếu chuyển", type="primary", key="complete_transfer"):
                image_url = None
                
                if uploaded_image is not None:
                    with st.spinner("Đang upload ảnh..."):
                        # Handle multiple images
                        if isinstance(uploaded_image, list):
                            image_files = uploaded_image
                        else:
                            image_files = [uploaded_image]
                        
                        urls = []
                        for idx, img in enumerate(image_files, start=1):
                            file_bytes = img.getvalue()
                            mime = img.type or "image/jpeg"
                            ext = img.name.split(".")[-1] if "." in img.name else "jpg"
                            # Tên file: tên phiếu chuyển + trạng thái + stt
                            sanitized_code = transfer_code.replace(" ", "_").replace("/", "_")
                            sanitized_status = new_status.replace(" ", "_").replace("/", "_")
                            drive_filename = f"{sanitized_code}_{sanitized_status}_{idx}.{ext}"
                            upload_res = upload_file_to_transfer_folder(file_bytes, drive_filename, mime)
                            if upload_res['success']:
                                urls.append(upload_res['url'])
                            else:
                                st.error(f"Upload ảnh {idx} thất bại: {upload_res['error']}")
                                st.stop()
                        
                        if urls:
                            image_url = ";".join(urls)
                        else:
                            image_url = None
                
                # Update transfer slip
                update_result = update_transfer_slip(
                    transfer_slip_id,
                    status='Đã hoàn thành',
                    image_url=image_url,
                    completed_by=current_user,
                    notes=notes if notes else None
                )
                
                if update_result['success']:
                    # Update all shipments status
                    status_result = update_transfer_slip_shipments_status(transfer_slip_id, new_status)
                    
                    if status_result['success']:
                        # Send Telegram notification
                        from telegram_helpers import send_transfer_slip_notification
                        telegram_result = send_transfer_slip_notification(transfer_slip_id)
                        
                        if telegram_result.get('success'):
                            st.success("Đã hoàn thành phiếu chuyển và gửi thông báo Telegram!")
                        else:
                            st.warning(f"Đã hoàn thành nhưng không gửi được Telegram: {telegram_result.get('error')}")
                        
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"Lỗi cập nhật trạng thái: {status_result['error']}")
                else:
                    st.error(f"Lỗi: {update_result['error']}")


def show_manage_transfer_slips():
    """Show all transfer slips for management"""
    st.header("Quản Lý Phiếu Chuyển")
    
    df = get_all_transfer_slips()
    
    if df.empty:
        st.info("Chưa có phiếu chuyển nào")
        return
    
    st.dataframe(
        df,
            use_container_width=True,
        hide_index=True,
        height=400
    )
    
    # View details
    selected_id = st.selectbox(
        "Chọn phiếu chuyển để xem chi tiết:",
        df['id'].tolist(),
        format_func=lambda x: f"{df[df['id']==x]['transfer_code'].iloc[0]} - {df[df['id']==x]['item_count'].iloc[0]} máy"
    )
    
    if selected_id:
        slip = get_transfer_slip(selected_id)
        items_df = get_transfer_slip_items(selected_id)
        
        st.subheader(f"Chi tiết phiếu: {slip['transfer_code']}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Trạng thái:** {slip['status']}")
            st.write(f"**Người tạo:** {slip['created_by']}")
            st.write(f"**Thời gian tạo:** {slip['created_at']}")
        with col2:
            if slip['completed_by']:
                st.write(f"**Người hoàn thành:** {slip['completed_by']}")
                st.write(f"**Thời gian hoàn thành:** {slip['completed_at']}")
            if slip['image_url']:
                # Tải ảnh ngay khi xem chi tiết phiếu chuyển (không lazy load)
                display_drive_image(slip['image_url'], width=300, caption="Ảnh phiếu chuyển")
        
        st.subheader(f"Danh sách máy ({len(items_df)} máy)")
        st.dataframe(items_df[['qr_code', 'imei', 'device_name', 'capacity', 'status']], use_container_width=True, hide_index=True)


def show_label_settings():
    """Cài đặt kích thước tem QR (lưu trong session hiện tại)"""
    ensure_label_defaults()
    st.subheader("🖨️ Cài đặt tem QR")
    st.info("Chọn kích thước tem (mm). Khi bấm In, trình duyệt sẽ mở hộp thoại chọn máy in/khổ giấy.")

    width_val = st.number_input(
        "Chiều rộng tem (mm)",
        min_value=20.0,
        max_value=120.0,
        value=float(st.session_state.get('label_width_mm', LABEL_DEFAULT_WIDTH_MM)),
        step=1.0,
        key="label_width_mm_input"
    )
    height_val = st.number_input(
        "Chiều cao tem (mm)",
        min_value=15.0,
        max_value=120.0,
        value=float(st.session_state.get('label_height_mm', LABEL_DEFAULT_HEIGHT_MM)),
        step=1.0,
        key="label_height_mm_input"
    )

    st.session_state['label_width_mm'] = width_val
    st.session_state['label_height_mm'] = height_val
    st.caption("Thiết lập này lưu trong phiên làm việc hiện tại. Khi in, bạn có thể chỉnh thêm trong hộp thoại in của trình duyệt.")


# Page configuration
st.set_page_config(
    page_title="Quản Lý Giao Nhận",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply styles
inject_sidebar_styles()
inject_main_styles()

# Ensure service account file exists (for Streamlit Cloud)
ensure_service_account_file()

# Initialize database on startup
if 'db_initialized' not in st.session_state:
    init_database()
    st.session_state['db_initialized'] = True

# Authentication check
if not require_login():
    st.stop()

# Auto-update status after 1 hour (run on every page load)
try:
    auto_result = auto_update_status_after_1hour()
    if auto_result['success'] and auto_result['updated_count'] > 0:
        # Store in session state to show notification once
        if 'auto_update_count' not in st.session_state or st.session_state['auto_update_count'] != auto_result['updated_count']:
            st.session_state['auto_update_count'] = auto_result['updated_count']
            st.session_state['show_auto_update_notification'] = True
except Exception as e:
    print(f"Error auto-updating status: {e}")

# Add loading animation CSS and optimize performance
st.markdown("""
<style>
    /* Loading overlay animation */
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    @keyframes fadeIn {
        from { 
            opacity: 0; 
            transform: translateY(10px); 
        }
        to { 
            opacity: 1; 
            transform: translateY(0); 
        }
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateX(-20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    .page-content {
        animation: fadeIn 0.4s ease-out;
        will-change: opacity, transform;
    }
    
    .loading-spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #3498db;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
        margin: 20px auto;
    }
    
    /* Smooth transition for navigation buttons */
    .stButton > button {
        transition: all 0.2s ease-in-out;
        will-change: transform, box-shadow;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    .stButton > button:active {
        transform: translateY(0);
    }
    
    /* Optimize rendering */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Smooth transitions for expanders */
    .streamlit-expanderHeader {
        transition: background-color 0.2s ease;
    }
    
    /* Loading state */
    .page-loading {
        opacity: 0.6;
        pointer-events: none;
    }
    
    /* Prevent layout shift */
    [data-testid="stAppViewContainer"] {
        min-height: 100vh;
    }
</style>
""", unsafe_allow_html=True)

# Main layout
st.sidebar.markdown('<div class="sidebar-title">Quản Lý Giao Nhận</div>', unsafe_allow_html=True)

# User info and logout
current_user = get_current_user()
st.sidebar.markdown(f'<div class="sidebar-user">Người dùng: <strong>{current_user}</strong></div>', unsafe_allow_html=True)
if st.sidebar.button("Đăng xuất", key="logout_btn"):
    logout()
    st.rerun()

# Navigation - only show Settings for admin
nav_options = ["Quét QR", "Dashboard", "Phiếu Chuyển", "Quản Lý Phiếu", "Lịch Sử"]
if is_admin():
    nav_options.append("Cài Đặt")

# Box-style navigation buttons (no dropdown, no radio)
# Quét QR is the default homepage
if 'nav' not in st.session_state:
    st.session_state['nav'] = "Quét QR"

st.sidebar.markdown("**Chọn chức năng:**")
for opt in nav_options:
    is_current = st.session_state['nav'] == opt
    btn = st.sidebar.button(
        opt,
        type="primary" if is_current else "secondary",
        use_container_width=True,
        key=f"nav_btn_{opt}"
    )
    if btn and not is_current:
        # Set navigation without immediate rerun - let Streamlit handle it naturally
        st.session_state['nav'] = opt
        st.session_state['nav_changed'] = True
        st.rerun()

selected = st.session_state['nav']

# Clear nav_changed flag after use
if st.session_state.get('nav_changed', False):
    st.session_state['nav_changed'] = False

# Show auto-update notification if any
if st.session_state.get('show_auto_update_notification', False):
    st.info(f"🔄 Đã tự động cập nhật {st.session_state.get('auto_update_count', 0)} phiếu quá 1 giờ")
    st.session_state['show_auto_update_notification'] = False

# Main content area with loading animation wrapper
content_container = st.container()
with content_container:
    # Add fade-in animation wrapper
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    
    # Use try-except to handle any errors gracefully
    try:
        if selected == "Quét QR":
            scan_qr_screen()
        
        elif selected == "Dashboard":
            show_dashboard()
        
        elif selected == "Phiếu Chuyển":
            show_transfer_slip_screen()
        
        elif selected == "Quản Lý Phiếu":
            show_manage_shipments()
        
        elif selected == "Lịch Sử":
            show_audit_log()
        
        elif selected == "Cài Đặt":
            show_settings_screen()
        else:
            st.warning(f"Trang '{selected}' không tồn tại. Chuyển về Quét QR...")
            st.session_state['nav'] = "Quét QR"
            st.rerun()
    except Exception as e:
        st.error(f"Lỗi khi tải trang: {str(e)}")
        st.info("Vui lòng thử lại hoặc làm mới trang.")
        import traceback
        with st.expander("Chi tiết lỗi", expanded=False):
            st.code(traceback.format_exc())
    
    st.markdown('</div>', unsafe_allow_html=True)
