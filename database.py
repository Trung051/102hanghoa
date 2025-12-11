"""
Database Operations Module
Handles all SQLite database operations for shipment management
"""

import sqlite3
import os
import sys
from datetime import datetime
import pandas as pd

# Ensure local config.py is preferred over any site-packages/config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_PATH, DEFAULT_STATUS, DEFAULT_SUPPLIERS, USERS


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
            sent_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            received_time TIMESTAMP,
            created_by TEXT NOT NULL,
            updated_by TEXT,
            notes TEXT,
            image_url TEXT,
            telegram_message_id INTEGER
        )
        ''')

        # Ensure column image_url exists (migration safety)
        cursor.execute("PRAGMA table_info(ShipmentDetails)")
        cols = [row[1] for row in cursor.fetchall()]
        if "image_url" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN image_url TEXT")
        if "telegram_message_id" not in cols:
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN telegram_message_id INTEGER")
        
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
            is_admin BOOLEAN DEFAULT 0
        )
        ''')
        
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
            cursor.execute('''
            INSERT OR IGNORE INTO Users (username, password, is_admin)
            VALUES (?, ?, ?)
            ''', (username, password, is_admin))
        
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


def save_shipment(qr_code, imei, device_name, capacity, supplier, created_by, notes=None, image_url=None, status=None):
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
        
    Returns:
        dict: {'success': bool, 'id': int or None, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO ShipmentDetails 
        (qr_code, imei, device_name, capacity, supplier, status, created_by, notes, image_url, telegram_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            qr_code,
            imei,
            device_name,
            capacity,
            supplier,
            status if status else DEFAULT_STATUS,
            created_by,
            notes,
            image_url,
            None
        ))
        
        conn.commit()
        shipment_id = cursor.lastrowid
        
        # Log audit
        log_audit(shipment_id, 'CREATED', None, f"Created shipment: {qr_code}", created_by)
        
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
                   telegram_message_id=None):
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
        
        # Log audit
        log_audit(shipment_id, 'UPDATED', None, 'Shipment information updated', updated_by or 'system')
        
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


def update_shipment_status(qr_code, new_status, updated_by, notes=None):
    """
    Update shipment status
    
    Args:
        qr_code: QR code to find shipment
        new_status: New status value
        updated_by: Username who updated
        notes: Optional notes
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get current shipment data
        cursor.execute('''
        SELECT id, status FROM ShipmentDetails WHERE qr_code = ?
        ''', (qr_code,))
        result = cursor.fetchone()
        
        if not result:
            return {'success': False, 'error': 'Phiếu không tồn tại'}
        
        shipment_id, old_status = result
        
        # Update status
        update_fields = {
            'status': new_status,
            'updated_by': updated_by
        }
        
        # Set received_time if status is "Đã nhận"
        if new_status == 'Đã nhận':
            update_fields['received_time'] = datetime.now().isoformat()
        
        # Update notes if provided
        if notes:
            update_fields['notes'] = notes
        
        set_clause = ', '.join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values()) + [qr_code]
        
        cursor.execute(f'''
        UPDATE ShipmentDetails
        SET {set_clause}
        WHERE qr_code = ?
        ''', values)
        
        conn.commit()
        
        # Log audit
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
               status, sent_time, received_time, created_by, updated_by, notes, image_url, telegram_message_id
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
               status, sent_time, received_time, created_by, updated_by, notes, image_url, telegram_message_id
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
        SELECT username, password, is_admin
        FROM Users
        WHERE username = ?
        ''', (username,))
        result = cursor.fetchone()
        if result:
            return {
                'username': result[0],
                'password': result[1],
                'is_admin': bool(result[2])
            }
        return None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None
    finally:
        conn.close()


def set_user_password(username, password, is_admin=False):
    """
    Create or update user password.
    Uses UPSERT to avoid duplicates.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO Users (username, password, is_admin)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password = excluded.password,
            is_admin = excluded.is_admin
        ''', (username, password, 1 if is_admin else 0))
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
        SELECT username, password, is_admin
        FROM Users
        ORDER BY username
        ''', conn)
        return df
    except Exception as e:
        print(f"Error getting users: {e}")
        return pd.DataFrame(columns=['username', 'password', 'is_admin'])
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
               status, sent_time, received_time, created_by, updated_by, notes, image_url, telegram_message_id
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
               status, sent_time, received_time, created_by, updated_by, notes, image_url, telegram_message_id
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

