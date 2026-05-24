import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import get_db_connection

def update_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if external_issue column exists
        cur.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_NAME = 'counseling_data' AND COLUMN_NAME = 'external_issue';
        """)
        row = cur.fetchone()
        if not row:
            print("Adding 'external_issue' column to 'counseling_data' table...")
            cur.execute("""
                ALTER TABLE counseling_data 
                ADD COLUMN external_issue VARCHAR(50) NOT NULL DEFAULT '정상 문의';
            """)
            conn.commit()
            print("Successfully added 'external_issue' column!")
        else:
            print("'external_issue' column already exists in 'counseling_data' table.")
            
    except Exception as e:
        print(f"Error altering table: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    update_schema()
