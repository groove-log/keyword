import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import get_db_connection, classifier, extractor

def reanalyze_all():
    print("==================================================")
    print("Starting Bulk DB Re-analysis under Current 2D Matrix")
    print("==================================================")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Fetch all existing records
        cur.execute("SELECT id, text FROM counseling_data ORDER BY id ASC;")
        rows = cur.fetchall()
        print(f"Found {len(rows)} records to re-analyze.")
        
        for c_id, text in rows:
            print(f"\n[Processing ID {c_id}]")
            print(f" Text snippet: {text[:40].replace(chr(10), ' ')}...")
            
            # 1. Run 2D classification
            risk_level, sim_score = classifier.classify_danger(text)
            external_issue, ext_score = classifier.classify_external(text)
            
            # 2. Extract keywords with dual guides (top 8, 1-3 gram)
            weight_coeff = 0.35
            keywords_with_scores = extractor.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 3),
                top_n=8,
                doc_risk_level=risk_level,
                doc_external_level=external_issue,
                classifier=classifier,
                weight_coeff=weight_coeff
            )
            
            # 3. Classify each keyword
            structured_keywords = []
            for word, score in keywords_with_scores:
                risk_cat, risk_score = classifier.classify_phrase(
                    word,
                    doc_risk_level=risk_level,
                    doc_external_level=external_issue
                )
                structured_keywords.append({
                    "word": word,
                    "score": round(score, 4),
                    "risk_category": risk_cat,
                    "risk_score": round(risk_score, 4)
                })
                
            keywords_json_str = json.dumps(structured_keywords, ensure_ascii=False)
            
            # 4. Update the DB row
            cur.execute("""
                UPDATE counseling_data 
                SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s, updated_at = NOW() 
                WHERE id = %s;
            """, (keywords_json_str, risk_level, external_issue, c_id))
            print(f" -> Updated! Danger: '{risk_level}', External: '{external_issue}'")
            
        conn.commit()
        print("\n==================================================")
        print("BULK DB RE-ANALYSIS COMPLETED SUCCESSFULLY!")
        print("==================================================")
        
    except Exception as e:
        print(f"Error during bulk re-analysis: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    reanalyze_all()
