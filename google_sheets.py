"""
Google Sheets Integration Module
Handles pushing shipment data to Google Sheets
"""

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import os

# Google Sheets configuration
SERVICE_ACCOUNT_FILE = 'service_account.json'
SHEET_ID = '1ROAsNg_7UsoW3qTr4_4mC0BRGmospktYidJM0ZNJAOo'
WORKSHEET_NAME = 'Sheet1'  # Default worksheet name, can be changed

# Scope for Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def get_google_sheets_client():
    """Get authenticated Google Sheets client"""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            return None, f"File {SERVICE_ACCOUNT_FILE} không tồn tại"
        
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
        client = gspread.authorize(creds)
        return client, None
    except Exception as e:
        return None, f"Lỗi xác thực Google Sheets: {str(e)}"


def get_or_create_worksheet(spreadsheet, worksheet_name):
    """Get existing worksheet or create new one"""
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet, None
    except gspread.exceptions.WorksheetNotFound:
        try:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name,
                rows=1000,
                cols=20
            )
            return worksheet, None
        except Exception as e:
            return None, f"Lỗi tạo worksheet: {str(e)}"
    except Exception as e:
        return None, f"Lỗi truy cập worksheet: {str(e)}"


def setup_headers(worksheet):
    """Setup headers in the worksheet if not exists"""
    try:
        # Check if headers exist
        existing_headers = worksheet.row_values(1)
        
        # Define headers
        headers = [
            'ID',
            'Mã QR Code',
            'IMEI',
            'Tên Thiết Bị',
            'Dung Lượng',
            'Nhà Cung Cấp',
            'Trạng Thái',
            'Thời Gian Gửi',
            'Thời Gian Nhận',
            'Người Tạo',
            'Người Cập Nhật',
            'Ghi Chú',
            'Thời Gian Đồng Bộ'
        ]
        
        # If headers don't exist or are different, set them
        if not existing_headers or existing_headers != headers:
            worksheet.clear()  # Clear existing data
            worksheet.append_row(headers)
            worksheet.format('A1:M1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            return True
        return False
    except Exception as e:
        return False


def push_shipments_to_sheets(shipments_df, append_mode=True):
    """
    Push shipment data to Google Sheets
    
    Args:
        shipments_df: DataFrame containing shipment data
        append_mode: If True, append to existing data. If False, replace all data.
    
    Returns:
        dict: {'success': bool, 'message': str, 'rows_added': int}
    """
    if shipments_df.empty:
        return {
            'success': False,
            'message': 'Không có dữ liệu để push lên Google Sheets',
            'rows_added': 0
        }
    
    try:
        # Get Google Sheets client
        client, error = get_google_sheets_client()
        if error:
            return {'success': False, 'message': error, 'rows_added': 0}
        
        # Open spreadsheet
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Get or create worksheet
        worksheet, error = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)
        if error:
            return {'success': False, 'message': error, 'rows_added': 0}
        
        # Setup headers
        setup_headers(worksheet)
        
        # Prepare data for upload
        sync_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        rows_to_add = []
        for _, row in shipments_df.iterrows():
            row_data = [
                str(row.get('id', '')),
                str(row.get('qr_code', '')),
                str(row.get('imei', '')),
                str(row.get('device_name', '')),
                str(row.get('capacity', '')),
                str(row.get('supplier', '')),
                str(row.get('status', '')),
                str(row.get('sent_time', '')),
                str(row.get('received_time', '') or ''),
                str(row.get('created_by', '')),
                str(row.get('updated_by', '') or ''),
                str(row.get('notes', '') or ''),
                sync_time
            ]
            rows_to_add.append(row_data)
        
        if not append_mode:
            # Clear existing data (except headers)
            worksheet.batch_clear(['A2:Z10000'])
        else:
            # In append mode, check for duplicates based on ID
            # Get existing IDs from column A (skip header row 1)
            try:
                existing_ids = worksheet.col_values(1)[1:]  # Skip header
                existing_ids = [str(id_val).strip() for id_val in existing_ids if id_val]
                # Filter out rows that already exist
                rows_to_add = [row for row in rows_to_add if str(row[0]).strip() not in existing_ids]
            except:
                pass  # If error reading existing data, proceed with all rows
        
        # Append data
        if rows_to_add:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        elif append_mode:
            return {
                'success': True,
                'message': 'Tất cả dữ liệu đã tồn tại trong Google Sheets. Không có dữ liệu mới để thêm.',
                'rows_added': 0
            }
        
        return {
            'success': True,
            'message': f'Đã push {len(rows_to_add)} dòng dữ liệu lên Google Sheets thành công!',
            'rows_added': len(rows_to_add)
        }
    
    except gspread.exceptions.APIError as e:
        return {
            'success': False,
            'message': f'Lỗi API Google Sheets: {str(e)}',
            'rows_added': 0
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Lỗi không xác định: {str(e)}',
            'rows_added': 0
        }


def find_row_by_id(worksheet, shipment_id):
    """Find row number in worksheet by shipment ID (column A)"""
    try:
        # Get all IDs from column A (skip header row 1)
        all_ids = worksheet.col_values(1)[1:]  # Skip header
        # Find the row index (1-indexed, +1 for header, +1 for 0-index to 1-index)
        for idx, id_val in enumerate(all_ids, start=2):  # Start from row 2 (after header)
            if str(id_val).strip() == str(shipment_id).strip():
                return idx
        return None
    except Exception as e:
        return None


def add_shipment_to_sheets(shipment_data):
    """
    Add a single shipment to Google Sheets
    
    Args:
        shipment_data: dict containing shipment data with keys: id, qr_code, imei, device_name, 
                      capacity, supplier, status, sent_time, received_time, created_by, updated_by, notes
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # Get Google Sheets client
        client, error = get_google_sheets_client()
        if error:
            return {'success': False, 'message': error}
        
        # Open spreadsheet
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Get or create worksheet
        worksheet, error = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)
        if error:
            return {'success': False, 'message': error}
        
        # Setup headers
        setup_headers(worksheet)
        
        # Prepare row data
        sync_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        row_data = [
            str(shipment_data.get('id', '')),
            str(shipment_data.get('qr_code', '')),
            str(shipment_data.get('imei', '')),
            str(shipment_data.get('device_name', '')),
            str(shipment_data.get('capacity', '')),
            str(shipment_data.get('supplier', '')),
            str(shipment_data.get('status', '')),
            str(shipment_data.get('sent_time', '')),
            str(shipment_data.get('received_time', '') or ''),
            str(shipment_data.get('created_by', '')),
            str(shipment_data.get('updated_by', '') or ''),
            str(shipment_data.get('notes', '') or ''),
            sync_time
        ]
        
        # Append row
        worksheet.append_row(row_data, value_input_option='USER_ENTERED')
        
        return {
            'success': True,
            'message': f'Đã thêm phiếu ID {shipment_data.get("id")} lên Google Sheets'
        }
    
    except Exception as e:
        return {'success': False, 'message': f'Lỗi thêm phiếu vào Google Sheets: {str(e)}'}


def update_shipment_in_sheets(shipment_data):
    """
    Update a single shipment in Google Sheets by ID
    
    Args:
        shipment_data: dict containing shipment data with keys: id, qr_code, imei, device_name, 
                      capacity, supplier, status, sent_time, received_time, created_by, updated_by, notes
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # Get Google Sheets client
        client, error = get_google_sheets_client()
        if error:
            return {'success': False, 'message': error}
        
        # Open spreadsheet
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Get or create worksheet
        worksheet, error = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)
        if error:
            return {'success': False, 'message': error}
        
        # Setup headers
        setup_headers(worksheet)
        
        shipment_id = shipment_data.get('id')
        if not shipment_id:
            return {'success': False, 'message': 'Không có ID phiếu'}
        
        # Find row by ID
        row_num = find_row_by_id(worksheet, shipment_id)
        
        if row_num is None:
            # If not found, add as new row
            return add_shipment_to_sheets(shipment_data)
        
        # Prepare row data
        sync_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        row_data = [
            str(shipment_data.get('id', '')),
            str(shipment_data.get('qr_code', '')),
            str(shipment_data.get('imei', '')),
            str(shipment_data.get('device_name', '')),
            str(shipment_data.get('capacity', '')),
            str(shipment_data.get('supplier', '')),
            str(shipment_data.get('status', '')),
            str(shipment_data.get('sent_time', '')),
            str(shipment_data.get('received_time', '') or ''),
            str(shipment_data.get('created_by', '')),
            str(shipment_data.get('updated_by', '') or ''),
            str(shipment_data.get('notes', '') or ''),
            sync_time
        ]
        
        # Update row (columns A to M)
        range_name = f'A{row_num}:M{row_num}'
        worksheet.update(range_name, [row_data], value_input_option='USER_ENTERED')
        
        return {
            'success': True,
            'message': f'Đã cập nhật phiếu ID {shipment_id} trong Google Sheets'
        }
    
    except Exception as e:
        return {'success': False, 'message': f'Lỗi cập nhật phiếu trong Google Sheets: {str(e)}'}


def sync_shipment_to_sheets(shipment_id, is_new=False):
    """
    Sync a single shipment to Google Sheets (auto-detect add or update)
    
    Args:
        shipment_id: Shipment ID
        is_new: If True, force add as new. If False, try to update existing or add if not found.
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # Import here to avoid circular import - query database directly
        import sqlite3
        from config import DB_PATH
        
        # Get shipment data directly from database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            SELECT id, qr_code, imei, device_name, capacity, supplier, 
                   status, sent_time, received_time, created_by, updated_by, notes
            FROM ShipmentDetails
            WHERE id = ?
            ''', (shipment_id,))
            
            result = cursor.fetchone()
            if not result:
                return {'success': False, 'message': f'Không tìm thấy phiếu ID {shipment_id}'}
            
            # Convert to dict format
            shipment_data = {
                'id': result[0],
                'qr_code': result[1],
                'imei': result[2],
                'device_name': result[3],
                'capacity': result[4],
                'supplier': result[5],
                'status': result[6],
                'sent_time': result[7],
                'received_time': result[8],
                'created_by': result[9],
                'updated_by': result[10],
                'notes': result[11]
            }
        finally:
            conn.close()
        
        if is_new:
            return add_shipment_to_sheets(shipment_data)
        else:
            return update_shipment_in_sheets(shipment_data)
    
    except Exception as e:
        return {'success': False, 'message': f'Lỗi đồng bộ phiếu: {str(e)}'}


def test_connection():
    """Test Google Sheets connection"""
    try:
        client, error = get_google_sheets_client()
        if error:
            return {'success': False, 'message': error}
        
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet, error = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)
        if error:
            return {'success': False, 'message': error}
        
        return {
            'success': True,
            'message': f'Kết nối thành công! Spreadsheet: {spreadsheet.title}',
            'worksheet': worksheet.title
        }
    except Exception as e:
        return {'success': False, 'message': f'Lỗi kết nối: {str(e)}'}

