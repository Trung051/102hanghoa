# -*- coding: utf-8 -*-
"""
Migration script to create TransferSlips and TransferSlipItems tables
Run this once to add the new tables to existing database
"""
import sqlite3
import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Database path (same as config.py)
DB_PATH = 'shipments.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check and create TransferSlips table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TransferSlips'")
        if not cursor.fetchone():
            print("Creating TransferSlips table...")
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
            print("✓ TransferSlips table created")
        else:
            print("✓ TransferSlips table already exists")
        
        # Check and create TransferSlipItems table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TransferSlipItems'")
        if not cursor.fetchone():
            print("Creating TransferSlipItems table...")
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
            print("✓ TransferSlipItems table created")
        else:
            print("✓ TransferSlipItems table already exists")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        return True
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

