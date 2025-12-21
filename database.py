"""
Database Operations Module
Handles all SQLite database operations for shipment management
"""

import sqlite3
import os
import sys
from datetime import datetime
import pandas as pd

# Ensure local modules are preferred
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Import settings with fallback to config (for deployments missing settings.py)
try:
    from settings import DB_PATH, DEFAULT_STATUS, DEFAULT_SUPPLIERS, USERS  # type: ignore
except ModuleNotFoundError:
    from config import DB_PATH, DEFAULT_STATUS, DEFAULT_SUPPLIERS, USERS  # type: ignore


def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)


def init_database():
    """
    Initialize database with tables and seed default data
    Creates tables if they don't exist and seeds default suppliers
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Create ShipmentDetails table
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS ShipmentDetails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_code TEXT UNIQUE NOT NULL,
            imei TEXT NOT NULL,
            device_name TEXT NOT NULL,
            capacity TEXT NOT NULL,
            supplier TEXT NOT NULL,
            status TEXT DEFAULT '{DEFAULT_STATUS}',
            request_type TEXT NOT NULL,
            sent_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            received_time TIMESTAMP,
            completed_time TIMESTAMP,
            created_by TEXT NOT NULL,
            updated_by TEXT,
            notes TEXT,
            image_url TEXT,
            telegram_message_id INTEGER,
            store_name TEXT
        )
        ''')

        # Ensure columns exist (migration safety)
        cursor.execute("PRAGMA table_info(ShipmentDetails)")
        cols = [row[1] for row in cursor.fetchall()]
        if "image_url" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN image_url TEXT")
        if "telegram_message_id" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN telegram_message_id INTEGER")
        if "store_name" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN store_name TEXT")
        if "reception_location" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN reception_location TEXT")
        if "request_type" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN request_type TEXT DEFAULT 'Sửa chữa dịch vụ'")
        if "completed_time" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN completed_time TIMESTAMP")
        if "last_updated" not in cols:
            # SQLite doesn't support DEFAULT CURRENT_TIMESTAMP in ALTER TABLE
            # So we add the column first, then update existing rows
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN last_updated TIMESTAMP")
            # Update existing rows with sent_time or current timestamp
            cursor.execute("""
                UPDATE ShipmentDetails 
                SET last_updated = COALESCE(sent_time, CURRENT_TIMESTAMP)
                WHERE last_updated IS NULL
            """)
        
        # Thêm các trường mới theo sơ đồ hệ thống
        if "device_status_on_reception" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN device_status_on_reception TEXT")
        if "repairer" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN repairer TEXT")
        if "repair_start_date" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN repair_start_date TIMESTAMP")
        if "repair_completion_date" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN repair_completion_date TIMESTAMP")
        if "ycsc_completion_date" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN ycsc_completion_date TIMESTAMP")
        if "repair_notes" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN repair_notes TEXT")
        if "quality_check_notes" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN quality_check_notes TEXT")
        if "repair_image_url" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN repair_image_url TEXT")
        if "quotation_notes" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN quotation_notes TEXT")
        
        # Create Suppliers table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Suppliers (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            contact TEXT,
            address TEXT,
            is_active BOOLEAN DEFAULT 1
        )
        ''')
        
        # Create AuditLog table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS AuditLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (shipment_id) REFERENCES ShipmentDetails(id)
        )
        ''')

        # Create Users table for authentication
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0,
            is_store BOOLEAN DEFAULT 0,
            is_kt_sr BOOLEAN DEFAULT 0,
            is_kt_kho BOOLEAN DEFAULT 0,
            store_name TEXT
        )
        ''')
        
        # Migration: Add columns if they don't exist
        cursor.execute("PRAGMA table_info(Users)")
        cols = [row[1] for row in cursor.fetchall()]
        if "is_store" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN is_store BOOLEAN DEFAULT 0")
        if "store_name" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN store_name TEXT")
        if "is_kt_sr" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN is_kt_sr BOOLEAN DEFAULT 0")
        if "is_kt_kho" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN is_kt_kho BOOLEAN DEFAULT 0")
        
        # Create TransferSlips table (Phiếu chuyển)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS TransferSlips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Đang chuyển',
            image_url TEXT,
            created_by TEXT NOT NULL,
            completed_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            notes TEXT
        )
        ''')
        
        # Create TransferSlipItems table (Chi tiết máy trong phiếu chuyển)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS TransferSlipItems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_slip_id INTEGER NOT NULL,
            shipment_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transfer_slip_id) REFERENCES TransferSlips(id),
            FOREIGN KEY (shipment_id) REFERENCES ShipmentDetails(id),
            UNIQUE(transfer_slip_id, shipment_id)
        )
        ''')

        # Seed default users from config
        for username, password in USERS.items():
            is_admin = 1 if username == 'admin' else 0
            is_store = 1 if username.startswith('cuahang') else 0
            cursor.execute('''
            INSERT OR IGNORE INTO Users (username, password, is_admin, is_store, store_name)
            VALUES (?, ?, ?, ?, ?)
            ''', (username, password, is_admin, is_store, None))
        
        # Create Stores table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            address TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Seed default suppliers
        for supplier in DEFAULT_SUPPLIERS:
            cursor.execute('''
            INSERT OR IGNORE INTO Suppliers (id, name, contact, address, is_active)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                supplier['id'],
                supplier['name'],
                supplier['contact'],
                supplier['address'],
                1 if supplier['is_active'] else 0
            ))
        
        # Migration: Check and create TransferSlips table if it doesn't exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TransferSlips'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE TransferSlips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transfer_code TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'Đang chuyển',
                image_url TEXT,
                created_by TEXT NOT NULL,
                completed_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT
            )
            ''')
        
        # Migration: Check and create TransferSlipItems table if it doesn't exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TransferSlipItems'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE TransferSlipItems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transfer_slip_id INTEGER NOT NULL,
                shipment_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transfer_slip_id) REFERENCES TransferSlips(id),
                FOREIGN KEY (shipment_id) REFERENCES ShipmentDetails(id),
                UNIQUE(transfer_slip_id, shipment_id)
            )
            ''')
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def save_shipment(qr_code, imei, device_name, capacity, supplier, created_by, notes=None, image_url=None, status=None, store_name=None, request_type=None, reception_location=None, device_status_on_reception=None, quotation_notes=None):
    """
    Save new shipment to database
    
    Args:
        qr_code: QR code string
        imei: IMEI of device
        device_name: Name of device
        capacity: Storage capacity
        supplier: Supplier name
        created_by: Username who created
        notes: Optional notes
        image_url: Optional image URL
        status: Optional status (defaults to DEFAULT_STATUS)
        store_name: Optional store name (for store users)
        
    Returns:
        dict: {'success': bool, 'id': int or None, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        if not request_type:
            request_type = 'Sửa chữa dịch vụ'  # Default
        cursor.execute('''
        INSERT INTO ShipmentDetails 
        (qr_code, imei, device_name, capacity, supplier, status, request_type, created_by, notes, image_url, telegram_message_id, store_name, reception_location, device_status_on_reception, quotation_notes, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            qr_code,
            imei,
            device_name,
            capacity,
            supplier,
            status if status else DEFAULT_STATUS,
            request_type,
            created_by,
            notes,
            image_url,
            None,
            store_name,
            reception_location,
            device_status_on_reception,
            quotation_notes
        ))
        
        conn.commit()
        shipment_id = cursor.lastrowid
        
        # Log audit
        log_audit(shipment_id, 'CREATED', None, f"Đã tạo phiếu: {qr_code} - {device_name} (IMEI: {imei})", created_by)
        
        # Auto-sync to Google Sheets
        try:
            from google_sheets import sync_shipment_to_sheets
            sync_shipment_to_sheets(shipment_id, is_new=True)
        except Exception as e:
            # Don't fail the save operation if Google Sheets sync fails
            print(f"Warning: Failed to sync to Google Sheets: {e}")
        
        return {'success': True, 'id': shipment_id, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'id': None, 'error': 'Mã QR đã tồn tại'}
    except Exception as e:
        return {'success': False, 'id': None, 'error': str(e)}
    finally:
        conn.close()


def update_shipment(shipment_id, qr_code=None, imei=None, device_name=None, capacity=None, 
                   supplier=None, status=None, notes=None, updated_by=None, image_url=None,
                   telegram_message_id=None, store_name=None, request_type=None, completed_time=None, reception_location=None,
                   device_status_on_reception=None, repairer=None, repair_start_date=None, repair_completion_date=None,
                   ycsc_completion_date=None, repair_notes=None, quality_check_notes=None, repair_image_url=None, quotation_notes=None):
    """
    Update shipment information
    
    Args:
        shipment_id: Shipment ID
        qr_code: New QR code (optional)
        imei: New IMEI (optional)
        device_name: New device name (optional)
        capacity: New capacity (optional)
        supplier: New supplier (optional)
        status: New status (optional)
        notes: New notes (optional)
        updated_by: Username who updated
        image_url: New image URL (optional)
        telegram_message_id: Telegram message ID (optional)
        store_name: Store name (optional)
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        updates = []
        values = []
        
        if qr_code is not None:
            updates.append('qr_code = ?')
            values.append(qr_code)
        if imei is not None:
            updates.append('imei = ?')
            values.append(imei)
        if device_name is not None:
            updates.append('device_name = ?')
            values.append(device_name)
        if capacity is not None:
            updates.append('capacity = ?')
            values.append(capacity)
        if supplier is not None:
            updates.append('supplier = ?')
            values.append(supplier)
        if status is not None:
            updates.append('status = ?')
            values.append(status)
            # Set received_time if status is "Đã nhận"
            if status == 'Đã nhận':
                updates.append('received_time = CURRENT_TIMESTAMP')
        if notes is not None:
            updates.append('notes = ?')
            values.append(notes)
        if updated_by is not None:
            updates.append('updated_by = ?')
            values.append(updated_by)
        if image_url is not None:
            updates.append('image_url = ?')
            values.append(image_url)
        if telegram_message_id is not None:
            updates.append('telegram_message_id = ?')
            values.append(telegram_message_id)
        if store_name is not None:
            updates.append('store_name = ?')
            values.append(store_name)
        if request_type is not None:
            updates.append('request_type = ?')
            values.append(request_type)
        if reception_location is not None:
            updates.append('reception_location = ?')
            values.append(reception_location)
        if completed_time is not None:
            updates.append('completed_time = ?')
            values.append(completed_time)
        elif status == 'Hoàn thành YCSC':
            # Auto-set completed_time when status becomes "Hoàn thành YCSC"
            updates.append('completed_time = CURRENT_TIMESTAMP')
        
        # Các trường mới theo sơ đồ
        if device_status_on_reception is not None:
            updates.append('device_status_on_reception = ?')
            values.append(device_status_on_reception)
        if repairer is not None:
            updates.append('repairer = ?')
            values.append(repairer)
        if repair_start_date is not None:
            updates.append('repair_start_date = ?')
            values.append(repair_start_date)
        if repair_completion_date is not None:
            updates.append('repair_completion_date = ?')
            values.append(repair_completion_date)
        if ycsc_completion_date is not None:
            updates.append('ycsc_completion_date = ?')
            values.append(ycsc_completion_date)
        if repair_notes is not None:
            updates.append('repair_notes = ?')
            values.append(repair_notes)
        if quality_check_notes is not None:
            updates.append('quality_check_notes = ?')
            values.append(quality_check_notes)
        if repair_image_url is not None:
            updates.append('repair_image_url = ?')
            values.append(repair_image_url)
        if quotation_notes is not None:
            updates.append('quotation_notes = ?')
            values.append(quotation_notes)
        
        # Luôn cập nhật last_updated khi có thay đổi
        if updates:
            updates.append('last_updated = CURRENT_TIMESTAMP')
        
        if not updates:
            return {'success': False, 'error': 'Không có thông tin để cập nhật'}
        
        values.append(shipment_id)
        set_clause = ', '.join(updates)
        
        cursor.execute(f'''
        UPDATE ShipmentDetails
        SET {set_clause}
        WHERE id = ?
        ''', values)
        
        conn.commit()
        
        # Log audit - Tạo thông báo chi tiết về những gì đã thay đổi
        changed_fields = []
        if qr_code is not None:
            changed_fields.append(f"Mã yêu cầu: {qr_code}")
        if imei is not None:
            changed_fields.append(f"IMEI: {imei}")
        if device_name is not None:
            changed_fields.append(f"Tên thiết bị: {device_name}")
        if capacity is not None:
            changed_fields.append(f"Dung lượng: {capacity}")
        if supplier is not None:
            changed_fields.append(f"Nhà cung cấp: {supplier}")
        if status is not None:
            changed_fields.append(f"Trạng thái: {status}")
        if notes is not None:
            note_preview = notes[:50] + ('...' if len(notes) > 50 else '')
            changed_fields.append(f"Ghi chú: {note_preview}")
        if request_type is not None:
            changed_fields.append(f"Loại yêu cầu: {request_type}")
        if store_name is not None:
            changed_fields.append(f"Cửa hàng: {store_name}")
        if reception_location is not None:
            changed_fields.append(f"Nơi tiếp nhận: {reception_location}")
        if device_status_on_reception is not None:
            changed_fields.append(f"Tình trạng thiết bị: {device_status_on_reception}")
        if repairer is not None:
            changed_fields.append(f"Người sửa: {repairer}")
        if repair_notes is not None:
            repair_note_preview = repair_notes[:50] + ('...' if len(repair_notes) > 50 else '')
            changed_fields.append(f"Ghi chú sửa máy: {repair_note_preview}")
        if quality_check_notes is not None:
            quality_note_preview = quality_check_notes[:50] + ('...' if len(quality_check_notes) > 50 else '')
            changed_fields.append(f"Ghi chú kiểm tra: {quality_note_preview}")
        if quotation_notes is not None:
            quote_note_preview = quotation_notes[:50] + ('...' if len(quotation_notes) > 50 else '')
            changed_fields.append(f"Ghi chú báo giá: {quote_note_preview}")
        if image_url is not None:
            changed_fields.append("Hình ảnh đã được cập nhật")
        if repair_image_url is not None:
            changed_fields.append("Hình ảnh sửa máy đã được cập nhật")
        
        if changed_fields:
            change_detail = " | ".join(changed_fields)
            log_audit(shipment_id, 'UPDATED', None, f"Đã cập nhật: {change_detail}", updated_by or 'system')
        else:
            log_audit(shipment_id, 'UPDATED', None, 'Đã cập nhật thông tin phiếu', updated_by or 'system')
        
        # Auto-sync to Google Sheets
        try:
            from google_sheets import sync_shipment_to_sheets
            sync_shipment_to_sheets(shipment_id, is_new=False)
        except Exception as e:
            # Don't fail the update operation if Google Sheets sync fails
            print(f"Warning: Failed to sync to Google Sheets: {e}")
        
        return {'success': True, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'error': 'Mã QR đã tồn tại'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def update_shipment_status(qr_code, new_status, updated_by, notes=None, image_url=None):
    """
    Update shipment status
    
    Args:
        qr_code: QR code to find shipment
        new_status: New status value
        updated_by: Username who updated
        notes: Optional notes
        image_url: Optional image URL (can append to existing images)
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get current shipment data
        cursor.execute('''
        SELECT id, status, image_url FROM ShipmentDetails WHERE qr_code = ?
        ''', (qr_code,))
        result = cursor.fetchone()
        
        if not result:
            return {'success': False, 'error': 'Phiếu không tồn tại'}
        
        shipment_id, old_status, current_image_url = result
        
        # Update status
        update_fields = {
            'status': new_status,
            'updated_by': updated_by,
            'last_updated': 'CURRENT_TIMESTAMP'  # Always update last_updated when status changes
        }
        
        # Set received_time if status is "Đã nhận"
        if new_status == 'Đã nhận':
            update_fields['received_time'] = datetime.now().isoformat()
        
        # Logic tự động cập nhật ngày khi đổi trạng thái theo sơ đồ
        if new_status == 'Đang sửa chữa':
            update_fields['repair_start_date'] = datetime.now().isoformat()
        elif new_status == 'Hoàn thành sửa chữa':
            update_fields['repair_completion_date'] = datetime.now().isoformat()
        elif new_status == 'Hoàn thành YCSC':
            update_fields['ycsc_completion_date'] = datetime.now().isoformat()
            update_fields['completed_time'] = datetime.now().isoformat()
        
        # Update notes if provided
        if notes:
            update_fields['notes'] = notes
        
        # Handle image_url: append to existing if both exist, otherwise use new or keep existing
        if image_url:
            if current_image_url:
                # Append new images to existing ones
                update_fields['image_url'] = f"{current_image_url};{image_url}"
            else:
                # Set new image URL
                update_fields['image_url'] = image_url
        
        # Handle last_updated separately (SQL function)
        fields_without_timestamp = {k: v for k, v in update_fields.items() if k != 'last_updated'}
        set_clause = ', '.join([f"{k} = ?" for k in fields_without_timestamp.keys()])
        set_clause += ', last_updated = CURRENT_TIMESTAMP'
        values = list(fields_without_timestamp.values()) + [qr_code]
        
        cursor.execute(f'''
        UPDATE ShipmentDetails
        SET {set_clause}
        WHERE qr_code = ?
        ''', values)
        
        conn.commit()
        
        # Log audit - Thay đổi trạng thái
        log_audit(shipment_id, 'STATUS_CHANGED', old_status, new_status, updated_by)
        
        # Auto-sync to Google Sheets
        try:
            from google_sheets import sync_shipment_to_sheets
            sync_shipment_to_sheets(shipment_id, is_new=False)
        except Exception as e:
            # Don't fail the update operation if Google Sheets sync fails
            print(f"Warning: Failed to sync to Google Sheets: {e}")
        
        return {'success': True, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def get_shipment_by_id(shipment_id):
    """
    Get shipment by ID
    
    Args:
        shipment_id: Shipment ID to search
        
    Returns:
        dict: Shipment data or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT id, qr_code, imei, device_name, capacity, supplier, 
               status, request_type, sent_time, received_time, completed_time, created_by, updated_by, notes, image_url, telegram_message_id, store_name, reception_location, last_updated,
               device_status_on_reception, repairer, repair_start_date, repair_completion_date, ycsc_completion_date, repair_notes, quality_check_notes, repair_image_url, quotation_notes
        FROM ShipmentDetails
        WHERE id = ?
        ''', (shipment_id,))
        
        result = cursor.fetchone()
        
        if result:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, result))
        return None
    except Exception as e:
        print(f"Error getting shipment by ID: {e}")
        return None
    finally:
        conn.close()


def get_shipment_by_qr_code(qr_code):
    """
    Get shipment by QR code
    
    Args:
        qr_code: QR code to search
        
    Returns:
        dict: Shipment data or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT id, qr_code, imei, device_name, capacity, supplier, 
               status, request_type, sent_time, received_time, completed_time, created_by, updated_by, notes, image_url, telegram_message_id, store_name, reception_location, last_updated,
               device_status_on_reception, repairer, repair_start_date, repair_completion_date, ycsc_completion_date, repair_notes, quality_check_notes, repair_image_url, quotation_notes
        FROM ShipmentDetails
        WHERE qr_code = ?
        ''', (qr_code,))
        
        result = cursor.fetchone()
        if not result:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, result))
    except Exception as e:
        print(f"Error getting shipment: {e}")
        return None
    finally:
        conn.close()


# ----------------------- User Management ----------------------- #

def get_user(username):
    """Get user by username"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        SELECT username, password, is_admin, is_store, is_kt_sr, is_kt_kho, store_name
        FROM Users
        WHERE username = ?
        ''', (username,))
        result = cursor.fetchone()
        if result:
            return {
                'username': result[0],
                'password': result[1],
                'is_admin': bool(result[2]),
                'is_store': bool(result[3]) if len(result) > 3 else False,
                'is_kt_sr': bool(result[4]) if len(result) > 4 else False,
                'is_kt_kho': bool(result[5]) if len(result) > 5 else False,
                'store_name': result[6] if len(result) > 6 else None
            }
        return None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None
    finally:
        conn.close()


def set_user_password(username, password, is_admin=False, is_store=False, is_kt_sr=False, is_kt_kho=False, store_name=None):
    """
    Create or update user password.
    Uses UPSERT to avoid duplicates.
    
    Args:
        username: Username
        password: Password
        is_admin: Whether user is admin (default: False)
        is_store: Whether user is a store user (default: False)
        is_kt_sr: Whether user is KT SR (default: False)
        is_kt_kho: Whether user is KT kho (default: False)
        store_name: Store name (optional)
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO Users (username, password, is_admin, is_store, is_kt_sr, is_kt_kho, store_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password = excluded.password,
            is_admin = excluded.is_admin,
            is_store = excluded.is_store,
            is_kt_sr = excluded.is_kt_sr,
            is_kt_kho = excluded.is_kt_kho,
            store_name = excluded.store_name
        ''', (username, password, 1 if is_admin else 0, 1 if is_store else 0, 1 if is_kt_sr else 0, 1 if is_kt_kho else 0, store_name))
        conn.commit()
        return {'success': True, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def get_all_users():
    """Return list of all users"""
    conn = get_connection()
    try:
        df = pd.read_sql_query('''
        SELECT username, password, is_admin, is_store, is_kt_sr, is_kt_kho, store_name
        FROM Users
        ORDER BY username
        ''', conn)
        return df
    except Exception as e:
        print(f"Error getting users: {e}")
        return pd.DataFrame(columns=['username', 'password', 'is_admin', 'is_store'])
    finally:
        conn.close()


def create_store(name: str, address: str = None, note: str = None):
    """Create a new store."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO Stores (name, address, note)
        VALUES (?, ?, ?)
        ''', (name, address, note))
        conn.commit()
        return {'success': True, 'id': cursor.lastrowid, 'error': None}
    except sqlite3.IntegrityError:
        conn.rollback()
        return {'success': False, 'id': None, 'error': 'Tên cửa hàng đã tồn tại'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'id': None, 'error': str(e)}
    finally:
        conn.close()


def get_all_stores():
    """Get all stores."""
    conn = get_connection()
    try:
        df = pd.read_sql_query('''
        SELECT id, name, address, note, created_at
        FROM Stores
        ORDER BY name
        ''', conn)
        return df
    except Exception as e:
        print(f"Error getting stores: {e}")
        return pd.DataFrame(columns=['id', 'name', 'address', 'note', 'created_at'])
    finally:
        conn.close()


def assign_user_to_store(username: str, store_name: str):
    """
    Assign user to a store (and mark as store user).
    If store_name is empty/None, remove assignment and is_store flag.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        UPDATE Users
        SET store_name = ?, is_store = CASE WHEN ? IS NOT NULL THEN 1 ELSE 0 END
        WHERE username = ?
        ''', (store_name, store_name, username))
        if cursor.rowcount == 0:
            conn.rollback()
            return {'success': False, 'error': 'User không tồn tại'}
        conn.commit()
        return {'success': True, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def delete_user(username: str):
    """Delete a user by username (protect admin)."""
    if username == 'admin':
        return {'success': False, 'error': 'Không thể xóa tài khoản admin'}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Users WHERE username = ?', (username,))
        if cursor.rowcount == 0:
            conn.rollback()
            return {'success': False, 'error': 'User không tồn tại'}
        conn.commit()
        return {'success': True, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def get_all_shipments():
    """
    Get all shipments
    
    Returns:
        pandas.DataFrame: All shipments
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT id, qr_code, imei, device_name, capacity, supplier, 
               status, request_type, store_name, reception_location, sent_time, received_time, completed_time, 
               created_by, updated_by, notes, image_url, telegram_message_id, last_updated,
               device_status_on_reception, repairer, repair_start_date, repair_completion_date, ycsc_completion_date, repair_notes, quality_check_notes, repair_image_url, quotation_notes
        FROM ShipmentDetails
        ORDER BY sent_time DESC
        ''', conn)
        
        return df
    except Exception as e:
        print(f"Error getting shipments: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def update_telegram_message(shipment_id, message_id):
    """Update telegram_message_id for a shipment"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        UPDATE ShipmentDetails
        SET telegram_message_id = ?
        WHERE id = ?
        ''', (message_id, shipment_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating telegram_message_id: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_shipments_by_status(status):
    """
    Get shipments filtered by status
    
    Args:
        status: Status value to filter
        
    Returns:
        pandas.DataFrame: Filtered shipments
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT id, qr_code, imei, device_name, capacity, supplier, 
               status, request_type, store_name, reception_location, sent_time, received_time, completed_time,
               created_by, updated_by, notes, image_url, telegram_message_id, last_updated,
               device_status_on_reception, repairer, repair_start_date, repair_completion_date, ycsc_completion_date, repair_notes, quality_check_notes, repair_image_url, quotation_notes
        FROM ShipmentDetails
        WHERE status = ?
        ORDER BY sent_time DESC
        ''', conn, params=(status,))
        
        return df
    except Exception as e:
        print(f"Error getting shipments by status: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_suppliers():
    """
    Get all active suppliers
    
    Returns:
        pandas.DataFrame: Active suppliers
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT id, name, contact, address
        FROM Suppliers
        WHERE is_active = 1
        ORDER BY name
        ''', conn)
        
        return df
    except Exception as e:
        print(f"Error getting suppliers: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_all_suppliers():
    """
    Get all suppliers (including inactive)
    
    Returns:
        pandas.DataFrame: All suppliers
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT id, name, contact, address, is_active
        FROM Suppliers
        ORDER BY name
        ''', conn)
        
        return df
    except Exception as e:
        print(f"Error getting all suppliers: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def add_supplier(name, contact=None, address=None):
    """
    Add new supplier
    
    Args:
        name: Supplier name
        contact: Contact information
        address: Address
        
    Returns:
        dict: {'success': bool, 'id': int or None, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get next ID
        cursor.execute('SELECT MAX(id) FROM Suppliers')
        max_id = cursor.fetchone()[0]
        new_id = (max_id or 0) + 1
        
        cursor.execute('''
        INSERT INTO Suppliers (id, name, contact, address, is_active)
        VALUES (?, ?, ?, ?, 1)
        ''', (new_id, name, contact, address))
        
        conn.commit()
        return {'success': True, 'id': new_id, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'id': None, 'error': 'Tên nhà cung cấp đã tồn tại'}
    except Exception as e:
        return {'success': False, 'id': None, 'error': str(e)}
    finally:
        conn.close()


def update_supplier(supplier_id, name=None, contact=None, address=None, is_active=None):
    """
    Update supplier information
    
    Args:
        supplier_id: Supplier ID
        name: New name (optional)
        contact: New contact (optional)
        address: New address (optional)
        is_active: Active status (optional)
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        updates = []
        values = []
        
        if name is not None:
            updates.append('name = ?')
            values.append(name)
        if contact is not None:
            updates.append('contact = ?')
            values.append(contact)
        if address is not None:
            updates.append('address = ?')
            values.append(address)
        if is_active is not None:
            updates.append('is_active = ?')
            values.append(1 if is_active else 0)
        
        if not updates:
            return {'success': False, 'error': 'Không có thông tin để cập nhật'}
        
        values.append(supplier_id)
        set_clause = ', '.join(updates)
        
        cursor.execute(f'''
        UPDATE Suppliers
        SET {set_clause}
        WHERE id = ?
        ''', values)
        
        conn.commit()
        return {'success': True, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'error': 'Tên nhà cung cấp đã tồn tại'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def delete_supplier(supplier_id):
    """
    Delete supplier (soft delete - set is_active = 0)
    
    Args:
        supplier_id: Supplier ID
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        UPDATE Suppliers
        SET is_active = 0
        WHERE id = ?
        ''', (supplier_id,))
        
        conn.commit()
        return {'success': True, 'error': None}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def log_audit(shipment_id, action, old_value, new_value, changed_by):
    """
    Log audit trail
    
    Args:
        shipment_id: ID of shipment
        action: Action type (CREATED, STATUS_CHANGED, UPDATED)
        old_value: Old value
        new_value: New value
        changed_by: Username who made change
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO AuditLog (shipment_id, action, old_value, new_value, changed_by)
        VALUES (?, ?, ?, ?, ?)
        ''', (shipment_id, action, old_value, new_value, changed_by))
        
        conn.commit()
    except Exception as e:
        print(f"Error logging audit: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_audit_log(limit=100):
    """
    Get audit log entries
    
    Args:
        limit: Maximum number of entries to return
        
    Returns:
        pandas.DataFrame: Audit log entries
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT 
            al.id,
            al.shipment_id,
            sd.qr_code,
            al.action,
            al.old_value,
            al.new_value,
            al.changed_by,
            al.timestamp
        FROM AuditLog al
        LEFT JOIN ShipmentDetails sd ON al.shipment_id = sd.id
        ORDER BY al.timestamp DESC
        LIMIT ?
        ''', conn, params=(limit,))
        
        return df
    except Exception as e:
        print(f"Error getting audit log: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def cleanup_audit_log(max_rows=100):
    """
    Tự động xóa các bản ghi cũ trong AuditLog khi vượt quá max_rows
    Giữ lại max_rows bản ghi mới nhất
    
    Args:
        max_rows: Số lượng bản ghi tối đa được giữ lại (mặc định: 100)
        
    Returns:
        dict: {'success': bool, 'deleted_count': int, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Đếm tổng số bản ghi
        cursor.execute('SELECT COUNT(*) FROM AuditLog')
        total_count = cursor.fetchone()[0]
        
        if total_count <= max_rows:
            return {'success': True, 'deleted_count': 0, 'error': None}
        
        # Xóa các bản ghi cũ, giữ lại max_rows bản ghi mới nhất
        # Lấy ID của max_rows bản ghi mới nhất
        cursor.execute(f'''
        SELECT id FROM AuditLog
        ORDER BY timestamp DESC, id DESC
        LIMIT {max_rows}
        ''')
        keep_ids = [row[0] for row in cursor.fetchall()]
        
        if keep_ids:
            # Tạo placeholders cho IN clause
            placeholders = ','.join(['?' for _ in keep_ids])
            cursor.execute(f'''
            DELETE FROM AuditLog
            WHERE id NOT IN ({placeholders})
            ''', keep_ids)
            deleted_count = cursor.rowcount
        else:
            deleted_count = 0
        
        conn.commit()
        return {'success': True, 'deleted_count': deleted_count, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'deleted_count': 0, 'error': str(e)}
    finally:
        conn.close()


# ==================== Transfer Slips Functions ====================

def create_transfer_slip(created_by, transfer_code=None):
    """
    Create a new transfer slip
    
    Args:
        created_by: Username who created
        transfer_code: Optional transfer code (auto-generated if None)
        
    Returns:
        dict: {'success': bool, 'id': int or None, 'transfer_code': str or None, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        if not transfer_code:
            # Generate transfer code: TC + timestamp
            transfer_code = f"TC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        cursor.execute('''
        INSERT INTO TransferSlips (transfer_code, created_by, status)
        VALUES (?, ?, 'Đang chuyển')
        ''', (transfer_code, created_by))
        
        transfer_id = cursor.lastrowid
        conn.commit()
        
        return {'success': True, 'id': transfer_id, 'transfer_code': transfer_code, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'id': None, 'transfer_code': None, 'error': 'Mã phiếu chuyển đã tồn tại'}
    except Exception as e:
        return {'success': False, 'id': None, 'transfer_code': None, 'error': str(e)}
    finally:
        conn.close()


def add_shipment_to_transfer_slip(transfer_slip_id, shipment_id):
    """
    Add a shipment to a transfer slip
    
    Args:
        transfer_slip_id: ID of transfer slip
        shipment_id: ID of shipment
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO TransferSlipItems (transfer_slip_id, shipment_id)
        VALUES (?, ?)
        ''', (transfer_slip_id, shipment_id))
        
        conn.commit()
        return {'success': True, 'error': None}
    except sqlite3.IntegrityError:
        return {'success': False, 'error': 'Máy đã có trong phiếu chuyển'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def get_transfer_slip(transfer_slip_id):
    """
    Get transfer slip details
    
    Args:
        transfer_slip_id: ID of transfer slip
        
    Returns:
        dict: Transfer slip details or None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT * FROM TransferSlips WHERE id = ?
        ''', (transfer_slip_id,))
        
        row = cursor.fetchone()
        if row:
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        return None
    except Exception as e:
        print(f"Error getting transfer slip: {e}")
        return None
    finally:
        conn.close()


def get_transfer_slip_items(transfer_slip_id):
    """
    Get all shipments in a transfer slip
    
    Args:
        transfer_slip_id: ID of transfer slip
        
    Returns:
        pandas.DataFrame: Shipments in transfer slip
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT 
            tsi.id,
            tsi.shipment_id,
            sd.qr_code,
            sd.imei,
            sd.device_name,
            sd.capacity,
            sd.status,
            tsi.added_at
        FROM TransferSlipItems tsi
        JOIN ShipmentDetails sd ON tsi.shipment_id = sd.id
        WHERE tsi.transfer_slip_id = ?
        ORDER BY tsi.added_at ASC
        ''', conn, params=(transfer_slip_id,))
        
        return df
    except Exception as e:
        print(f"Error getting transfer slip items: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_active_transfer_slip(created_by):
    """
    Get active (incomplete) transfer slip for a user
    
    Args:
        created_by: Username
        
    Returns:
        dict: Transfer slip details or None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT * FROM TransferSlips 
        WHERE created_by = ? AND status = 'Đang chuyển'
        ORDER BY created_at DESC
        LIMIT 1
        ''', (created_by,))
        
        row = cursor.fetchone()
        if row:
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        return None
    except Exception as e:
        print(f"Error getting active transfer slip: {e}")
        return None
    finally:
        conn.close()


def get_all_transfer_slips():
    """
    Get all transfer slips
    
    Returns:
        pandas.DataFrame: All transfer slips
    """
    conn = get_connection()
    
    try:
        df = pd.read_sql_query('''
        SELECT 
            ts.id,
            ts.transfer_code,
            ts.status,
            ts.created_by,
            ts.completed_by,
            ts.created_at,
            ts.completed_at,
            ts.image_url,
            COUNT(tsi.id) as item_count
        FROM TransferSlips ts
        LEFT JOIN TransferSlipItems tsi ON ts.id = tsi.transfer_slip_id
        GROUP BY ts.id
        ORDER BY ts.created_at DESC
        ''', conn)
        
        return df
    except Exception as e:
        print(f"Error getting all transfer slips: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def update_transfer_slip(transfer_slip_id, status=None, image_url=None, completed_by=None, notes=None):
    """
    Update transfer slip
    
    Args:
        transfer_slip_id: ID of transfer slip
        status: New status
        image_url: Image URL
        completed_by: Username who completed
        notes: Notes
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        updates = []
        params = []
        
        if status:
            updates.append("status = ?")
            params.append(status)
        
        if image_url:
            updates.append("image_url = ?")
            params.append(image_url)
        
        if completed_by:
            updates.append("completed_by = ?")
            params.append(completed_by)
        
        if notes:
            updates.append("notes = ?")
            params.append(notes)
        
        if status and status != 'Đang chuyển':
            updates.append("completed_at = CURRENT_TIMESTAMP")
        
        if not updates:
            return {'success': False, 'error': 'Không có thay đổi nào'}
        
        params.append(transfer_slip_id)
        query = f"UPDATE TransferSlips SET {', '.join(updates)} WHERE id = ?"
        
        cursor.execute(query, params)
        conn.commit()
        
        return {'success': True, 'error': None}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def update_transfer_slip_shipments_status(transfer_slip_id, new_status):
    """
    Update status of all shipments in a transfer slip
    
    Args:
        transfer_slip_id: ID of transfer slip
        new_status: New status for shipments
        
    Returns:
        dict: {'success': bool, 'updated_count': int, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get all shipment IDs in this transfer slip
        cursor.execute('''
        SELECT shipment_id FROM TransferSlipItems WHERE transfer_slip_id = ?
        ''', (transfer_slip_id,))
        
        shipment_ids = [row[0] for row in cursor.fetchall()]
        
        if not shipment_ids:
            return {'success': False, 'updated_count': 0, 'error': 'Không có máy nào trong phiếu chuyển'}
        
        # Update status for all shipments
        updated_count = 0
        for shipment_id in shipment_ids:
            cursor.execute('''
            UPDATE ShipmentDetails 
            SET status = ?, updated_by = (SELECT created_by FROM TransferSlips WHERE id = ?)
            WHERE id = ?
            ''', (new_status, transfer_slip_id, shipment_id))
            updated_count += cursor.rowcount
        
        conn.commit()
        return {'success': True, 'updated_count': updated_count, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'updated_count': 0, 'error': str(e)}
    finally:
        conn.close()


def clear_all_data():
    """
    Xóa toàn bộ dữ liệu trong database (chỉ giữ lại cấu trúc bảng và dữ liệu mặc định)
    CẢNH BÁO: Hàm này sẽ xóa TẤT CẢ dữ liệu!
    
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Xóa tất cả dữ liệu từ các bảng (giữ lại cấu trúc)
        cursor.execute('DELETE FROM TransferSlipItems')
        cursor.execute('DELETE FROM TransferSlips')
        cursor.execute('DELETE FROM AuditLog')
        cursor.execute('DELETE FROM ShipmentDetails')
        
        # Xóa suppliers nhưng giữ lại cấu trúc
        cursor.execute('DELETE FROM Suppliers')
        
        # Xóa users nhưng giữ lại cấu trúc
        cursor.execute('DELETE FROM Users')
        
        # Seed lại dữ liệu mặc định
        # Seed default users
        for username, password in USERS.items():
            is_admin = 1 if username == 'admin' else 0
            is_store = 1 if username.startswith('cuahang') else 0
            cursor.execute('''
            INSERT INTO Users (username, password, is_admin, is_store)
            VALUES (?, ?, ?, ?)
            ''', (username, password, is_admin, is_store))
        
        # Seed default suppliers
        for supplier in DEFAULT_SUPPLIERS:
            cursor.execute('''
            INSERT INTO Suppliers (id, name, contact, address, is_active)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                supplier['id'],
                supplier['name'],
                supplier['contact'],
                supplier['address'],
                1 if supplier['is_active'] else 0
            ))
        
        conn.commit()
        return {'success': True, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def auto_update_status_after_1hour():
    """
    Tự động chuyển trạng thái sau 1 giờ:
    - "Đã nhận"      -> "Nhập kho xử lý"
    - "Nhập kho"     -> "Nhập kho xử lý"
    - "Chuyển kho"   -> "Đang xử lý" (giữ logic cũ)
    
    Returns:
        dict: {'success': bool, 'updated_count': int, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        updated_count = 0
        
        # Đã nhận -> Nhập kho xử lý sau 1 giờ
        cursor.execute('''
        UPDATE ShipmentDetails
        SET status = 'Nhập kho xử lý', last_updated = CURRENT_TIMESTAMP
        WHERE status = 'Đã nhận'
        AND datetime(last_updated) <= datetime('now', '-1 hour')
        ''')
        updated_count += cursor.rowcount
        
        # Nhập kho -> Nhập kho xử lý sau 1 giờ
        cursor.execute('''
        UPDATE ShipmentDetails
        SET status = 'Nhập kho xử lý', last_updated = CURRENT_TIMESTAMP
        WHERE status = 'Nhập kho'
        AND datetime(last_updated) <= datetime('now', '-1 hour')
        ''')
        updated_count += cursor.rowcount
        
        # Chuyển kho -> Đang xử lý sau 1 giờ (logic cũ)
        cursor.execute('''
        UPDATE ShipmentDetails
        SET status = 'Đang xử lý', last_updated = CURRENT_TIMESTAMP
        WHERE status = 'Chuyển kho'
        AND datetime(last_updated) <= datetime('now', '-1 hour')
        ''')
        updated_count += cursor.rowcount
        
        conn.commit()
        
        return {'success': True, 'updated_count': updated_count, 'error': None}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'updated_count': 0, 'error': str(e)}
    finally:
        conn.close()


def get_active_shipments():
    """
    Lấy danh sách phiếu đang hoạt động (chưa hoàn thành)
    
    Returns:
        pandas.DataFrame: DataFrame chứa các phiếu đang hoạt động
    """
    try:
        from settings import ACTIVE_STATUSES  # type: ignore
    except ModuleNotFoundError:
        from config import ACTIVE_STATUSES  # type: ignore
    conn = get_connection()
    
    try:
        # Tạo placeholders cho IN clause
        placeholders = ','.join(['?' for _ in ACTIVE_STATUSES])
        query = f'''
        SELECT * FROM ShipmentDetails
        WHERE status IN ({placeholders})
        ORDER BY last_updated DESC
        '''
        
        df = pd.read_sql_query(query, conn, params=ACTIVE_STATUSES)
        return df
    except Exception as e:
        print(f"Error getting active shipments: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

