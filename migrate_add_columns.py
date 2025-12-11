"""
Migration script to add is_store column to Users table and last_updated to ShipmentDetails
Run this script if you encounter "no such column" errors
"""
import sqlite3
import os
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Database path (same as config.py)
DB_PATH = 'shipments.db'

def migrate():
    """Add missing columns to existing database"""
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} not found. Creating new database...")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Checking Users table...")
        cursor.execute("PRAGMA table_info(Users)")
        users_cols = [row[1] for row in cursor.fetchall()]
        print(f"Current Users columns: {users_cols}")
        
        if "is_store" not in users_cols:
            print("Adding is_store column to Users table...")
            cursor.execute("ALTER TABLE Users ADD COLUMN is_store BOOLEAN DEFAULT 0")
            print("✓ Added is_store column to Users")
        else:
            print("✓ is_store column already exists in Users")
        
        print("\nChecking ShipmentDetails table...")
        cursor.execute("PRAGMA table_info(ShipmentDetails)")
        shipment_cols = [row[1] for row in cursor.fetchall()]
        print(f"Current ShipmentDetails columns: {shipment_cols}")
        
        if "store_name" not in shipment_cols:
            print("Adding store_name column to ShipmentDetails table...")
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN store_name TEXT")
            print("✓ Added store_name column to ShipmentDetails")
        else:
            print("✓ store_name column already exists in ShipmentDetails")
        
        if "last_updated" not in shipment_cols:
            print("Adding last_updated column to ShipmentDetails table...")
            # SQLite doesn't support DEFAULT CURRENT_TIMESTAMP in ALTER TABLE
            # So we add the column first, then update existing rows
            cursor.execute("ALTER TABLE ShipmentDetails ADD COLUMN last_updated TIMESTAMP")
            # Update existing rows with sent_time or current timestamp
            cursor.execute("""
                UPDATE ShipmentDetails 
                SET last_updated = COALESCE(sent_time, CURRENT_TIMESTAMP)
                WHERE last_updated IS NULL
            """)
            print("✓ Added last_updated column to ShipmentDetails and updated existing rows")
        else:
            print("✓ last_updated column already exists in ShipmentDetails")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Verify
        print("\nVerifying columns...")
        cursor.execute("PRAGMA table_info(Users)")
        users_cols_after = [row[1] for row in cursor.fetchall()]
        print(f"Users columns after migration: {users_cols_after}")
        
        cursor.execute("PRAGMA table_info(ShipmentDetails)")
        shipment_cols_after = [row[1] for row in cursor.fetchall()]
        print(f"ShipmentDetails columns after migration: {shipment_cols_after}")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

