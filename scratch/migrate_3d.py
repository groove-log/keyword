import sys
import os
import json
import psycopg

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import get_db_connection

def run_ddl():
    print("==================================================")
    print("Executing Database DDL Migration for 3D Triage")
    print("==================================================")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Add Z-axis column
        cur.execute("ALTER TABLE counseling_data ADD COLUMN IF NOT EXISTS urgency_level VARCHAR(50) NOT NULL DEFAULT 'MONITOR';")
        # 2. Add detected_categories metadata column
        cur.execute("ALTER TABLE counseling_data ADD COLUMN IF NOT EXISTS detected_categories TEXT;")
        conn.commit()
        print(" -> DDL migration completed successfully!")
    except Exception as e:
        print(f" -> ERROR during DDL migration: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def migrate_data():
    print("\n==================================================")
    print("Running Retroactive Data Migration to 3D Triage")
    print("==================================================")
    
    # Import worker elements dynamically to allow updates to worker.py first
    from worker import classifier, get_db_connection
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, text FROM counseling_data ORDER BY id ASC;")
        rows = cur.fetchall()
        print(f"Found {len(rows)} records to migrate.")
        
        for c_id, text in rows:
            print(f"\n[Migrating ID {c_id}]")
            
            # Z-axis Urgency
            urgency = classifier.classify_urgency(text)
            
            # Danger multi-label list
            dangers = classifier.classify_danger(text)
            primary_danger = dangers[0][0] if dangers else "정상 문의"
            
            # External multi-label list
            externals = classifier.classify_external(text)
            primary_external = externals[0][0] if externals else "정상 문의"
            
            # Construct serialized JSON metadata
            detected_json = {
                "danger": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(dangers)],
                "external": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(externals)]
            }
            detected_str = json.dumps(detected_json, ensure_ascii=False)
            
            # Update columns
            cur.execute("""
                UPDATE counseling_data
                SET risk_level = %s, external_issue = %s, urgency_level = %s, detected_categories = %s, updated_at = NOW()
                WHERE id = %s;
            """, (primary_danger, primary_external, urgency, detected_str, c_id))
            print(f" -> Migrated! Primary Danger: '{primary_danger}', Primary External: '{primary_external}', Urgency: '{urgency}'")
            
        conn.commit()
        print("\n==================================================")
        print("DATA MIGRATION COMPLETED SUCCESSFULLY!")
        print("==================================================")
    except Exception as e:
        print(f" -> ERROR during data migration: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_ddl()
    if len(sys.argv) > 1 and sys.argv[1] == "--data":
        migrate_data()
