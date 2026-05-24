import sys
import os
import time
import urllib.request
import json
import psycopg

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import get_db_connection

def test_async_custom_threshold():
    print("==================================================")
    print("TDD E2E Test: Async Custom Threshold Synchronization")
    print("==================================================")
    
    url = "http://web-app:8000/api/extract/async"
    headers = {"Content-Type": "application/json"}
    
    # 1. 도시락 쥐머리 문맥 (일반 디폴트 0.60 임계값 하에서는 감지되지 않는 텍스트)
    text = "도시락에서 쥐머리가 나왔습니다. 발견되는 순간 식사 중 모두 경악을 금치 못했습니다. 너무 혐오스럽습니다."
    
    # 2. 커스텀 임계값을 0.50으로 완화하여 주입
    payload = {
        "text": text,
        "thresholds": {"이물질 상품": 0.50},
        "linked_threshold": 0.45,
        "min_safeguard_score": 0.52
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    print("[1] Requesting Async task with custom thresholds...")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        counseling_id = data["counseling_id"]
        print(f" -> Async Task Queued! Counseling ID: {counseling_id}, Task ID: {data['task_id']}")
        
    print("[2] Waiting for Celery worker to complete analysis (max 10s)...")
    completed = False
    for _ in range(20):
        time.sleep(0.5)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, risk_level, keywords FROM counseling_data WHERE id = %s;", (counseling_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row and row[0] == "COMPLETED":
            completed = True
            risk_level = row[1]
            keywords = json.loads(row[2])
            print(f" -> Task Finished! DB Status: {row[0]}")
            print(f" -> Mapped Risk Level: '{risk_level}'")
            print(f" -> Keywords: {keywords}")
            break
            
    assert completed, "FAIL: Celery worker did not complete the task in time."
    # 3. 임계값을 0.50으로 낮췄으므로, Celery 백그라운드 분석에서도 '이물질 상품'이 완벽하게 분류되어야 합니다!
    assert risk_level == "이물질 상품", f"FAIL: Expected '이물질 상품' risk level in DB, but got '{risk_level}'"
    print("\n✅ SUCCESS: Async Celery worker successfully synchronized with UI custom thresholds!")
    print("==================================================")

if __name__ == "__main__":
    try:
        test_async_custom_threshold()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
