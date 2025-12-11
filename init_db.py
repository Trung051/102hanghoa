"""
Script to initialize database
Run this script to create all tables and seed default data
"""

import sys
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import init_database

if __name__ == "__main__":
    print("Initializing database...")
    result = init_database()
    if result:
        print("SUCCESS: Database initialized!")
    else:
        print("ERROR: Failed to initialize database!")

