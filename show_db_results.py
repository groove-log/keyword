"""
PostgreSQL 데이터베이스의 counseling_data 테이블 상태를 조회하여 출력하는 모니터링 스크립트입니다.
"""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_NAME     = os.getenv("DB_NAME", "ledger_db")
DB_USER     = os.getenv("DB_USER", "ledger_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "ledger_pass")
DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT     = os.getenv("DB_PORT", "5432")

def main():
    try:
        conn = psycopg.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        cur = conn.cursor()
        cur.execute("SELECT id, text, keywords, status, updated_at FROM counseling_data ORDER BY id ASC;")
        rows = cur.fetchall()
        
        print("\n" + "="*80)
        print(f" DB 테이블 상태 조회 (데이터베이스: {DB_NAME})")
        print("="*80)
        
        for row in rows:
            c_id, text, keywords, status, updated_at = row
            print(f"ID: {c_id} | 상태: {status:10} | 최종 수정: {updated_at}")
            print(f"내용: {text}")
            print(f"추출된 키워드: {keywords if keywords else '(없음)'}")
            print("-"*80)
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == "__main__":
    main()
