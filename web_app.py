import os
import time
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psycopg
from dotenv import load_dotenv

# worker 모듈에서 기존에 구성된 DB 연결 및 키워드 추출기 불러오기
from worker import extractor, process_keyword_extraction, get_db_connection, classifier

load_dotenv()

app = FastAPI(title="Keyword Extraction Web Prototype")

# 템플릿 설정 (index.html 렌더링용)
templates = Jinja2Templates(directory="templates")

# 요청 데이터 스키마 정의
class SyncExtractRequest(BaseModel):
    text: str
    ngram_min: int = 1
    ngram_max: int = 3
    top_n: int = 8
    thresholds: dict[str, float] = None  # UI에서 조정하여 전달하는 커스텀 임계값
    linked_threshold: float = None      # UI에서 조정하는 커스텀 연관 키워드 임계값
    min_safeguard_score: float = None   # UI에서 조정하는 커스텀 안전 제한 임계값

class AsyncExtractRequest(BaseModel):
    text: str
    thresholds: dict[str, float] = None
    linked_threshold: float = None
    min_safeguard_score: float = None

# 1. 메인 UI 페이지 서빙
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 1.5. 서버 임계값 설정 정보 전달 API
@app.get("/api/settings")
async def get_settings():
    # 위험 가이드라인 및 외부 가이드라인 통합 제공
    combined_guidelines = {**classifier.danger_guidelines, **classifier.external_guidelines}
    return {
        "guidelines": combined_guidelines,
        "default_thresholds": classifier.thresholds,
        "fallback_threshold": classifier.threshold,
        "default_linked_threshold": classifier.linked_threshold,
        "default_min_safeguard_score": classifier.min_safeguard_score
    }

# 2. 동기식 (Sync) 실시간 추출 API
@app.post("/api/extract/sync")
async def extract_sync(req: SyncExtractRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="텍스트가 비어있습니다.")
    
    start_time = time.time()
    try:
        # 1. 2D 위험 매트릭스 판별 진행
        risk_level, sim_score = classifier.classify_danger(req.text, req.thresholds)
        external_issue, ext_score = classifier.classify_external(req.text, req.thresholds)

        # 2. BGE-m3 임베딩 서버 호출 및 유사도 계산 진행 (듀얼 가이드 결합 적용)
        weight_coeff = float(os.getenv("DANGER_KEYWORD_GUIDE_WEIGHT", "0.35"))
        results = extractor.extract_keywords(
            text=req.text,
            keyphrase_ngram_range=(req.ngram_min, req.ngram_max),
            top_n=req.top_n,
            doc_risk_level=risk_level,
            doc_external_level=external_issue,
            classifier=classifier,
            weight_coeff=weight_coeff
        )
        elapsed_time = round((time.time() - start_time) * 1000, 2) # 밀리초(ms) 단위 변환
        
        # 3. 키워드별 세부 카테고리 매핑 진행 (2D 분류 데이터 연계)
        keywords = []
        for item in results:
            word = item[0]
            score = item[1]
            risk_cat, risk_score = classifier.classify_phrase(
                word, 
                req.thresholds, 
                doc_risk_level=risk_level, 
                doc_external_level=external_issue,
                custom_linked_threshold=req.linked_threshold,
                custom_min_safeguard=req.min_safeguard_score
            )
            keywords.append({
                "word": word,
                "score": round(score, 4),
                "risk_category": risk_cat,
                "risk_score": round(risk_score, 4)
            })
        
        return {
            "status": "success",
            "keywords": keywords,
            "elapsed_ms": elapsed_time,
            "model": "BAAI/bge-m3",
            "risk_level": risk_level,
            "risk_score": round(sim_score, 4),
            "external_issue": external_issue,
            "external_score": round(ext_score, 4)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 서버 통신 실패: {str(e)}")

# 3. 비동기식 (Async) Celery 워커 기반 추출 API
@app.post("/api/extract/async")
async def extract_async(req: AsyncExtractRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="텍스트가 비어있습니다.")
    
    conn = None
    try:
        # DB에 먼저 PENDING 상태로 신규 상담 기록을 등록
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO counseling_data (text, status) VALUES (%s, 'PENDING') RETURNING id;",
            (req.text,)
        )
        counseling_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        
        # Celery 태스크 백그라운드 큐에 등록 (커스텀 임계치 연계)
        task = process_keyword_extraction.delay(
            counseling_id, 
            req.text, 
            req.thresholds, 
            req.linked_threshold, 
            req.min_safeguard_score
        )
        
        return {
            "status": "success",
            "counseling_id": counseling_id,
            "task_id": task.id,
            "message": "태스크가 Celery 워커 대기열에 등록되었습니다."
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"비동기 작업 등록 실패: {str(e)}")
    finally:
        if conn:
            conn.close()

# 4. DB 히스토리 최신 10건 조회 API (2D 매트릭스 필드 추가)
@app.get("/api/history")
async def get_history():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, text, keywords, status, updated_at, risk_level, external_issue 
            FROM counseling_data 
            ORDER BY id DESC 
            LIMIT 10;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                "id": row[0],
                "text": row[1],
                "keywords": row[2] if row[2] else "",
                "status": row[3],
                "updated_at": row[4].strftime("%Y-%m-%d %H:%M:%S") if row[4] else "",
                "risk_level": row[5] if row[5] else "정상 문의",
                "external_issue": row[6] if row[6] else "정상 문의"
              })
            
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 실패: {str(e)}")

# 5. 건별 재분석 API
@app.post("/api/reanalyze/{counseling_id}")
async def reanalyze_case(counseling_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 기존 데이터 조회
        cur.execute("SELECT text FROM counseling_data WHERE id = %s;", (counseling_id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="해당 상담 기록을 찾을 수 없습니다.")
            
        text = row[0]
        cur.close()
        conn.close()
        
        # 2. 실시간 판별 및 키워드 추출 진행 (구문 추출 + 듀얼가이드 + 중복제거 적용)
        risk_level, sim_score = classifier.classify_danger(text)
        external_issue, ext_score = classifier.classify_external(text)
        
        weight_coeff = 0.35
        results = extractor.extract_keywords(
            text=text,
            keyphrase_ngram_range=(1, 3),
            top_n=8,
            doc_risk_level=risk_level,
            doc_external_level=external_issue,
            classifier=classifier,
            weight_coeff=weight_coeff
        )
        
        keywords = []
        for word, score in results:
            risk_cat, risk_score = classifier.classify_phrase(
                word, 
                doc_risk_level=risk_level, 
                doc_external_level=external_issue
            )
            keywords.append({
                "word": word,
                "score": round(score, 4),
                "risk_category": risk_cat,
                "risk_score": round(risk_score, 4)
            })
            
        keywords_json_str = json.dumps(keywords, ensure_ascii=False)
        
        # 3. DB 업데이트
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE counseling_data 
            SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s, updated_at = NOW() 
            WHERE id = %s;
        """, (keywords_json_str, risk_level, external_issue, counseling_id))
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "counseling_id": counseling_id,
            "risk_level": risk_level,
            "external_issue": external_issue,
            "keywords": keywords
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재분석 처리 실패: {str(e)}")

# 6. 전체 재분석 API
@app.post("/api/reanalyze-all")
async def reanalyze_all_cases():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 기존 전체 데이터 조회
        cur.execute("SELECT id, text FROM counseling_data ORDER BY id ASC;")
        rows = cur.fetchall()
        
        reanalyzed_count = 0
        for counseling_id, text in rows:
            # 실시간 판별 및 키워드 추출 진행 (구문 추출 + 듀얼가이드 + 중복제거 적용)
            risk_level, sim_score = classifier.classify_danger(text)
            external_issue, ext_score = classifier.classify_external(text)
            
            weight_coeff = 0.35
            results = extractor.extract_keywords(
                text=text,
                keyphrase_ngram_range=(1, 3),
                top_n=8,
                doc_risk_level=risk_level,
                doc_external_level=external_issue,
                classifier=classifier,
                weight_coeff=weight_coeff
            )
            
            keywords = []
            for word, score in results:
                risk_cat, risk_score = classifier.classify_phrase(
                    word, 
                    doc_risk_level=risk_level, 
                    doc_external_level=external_issue
                )
                keywords.append({
                    "word": word,
                    "score": round(score, 4),
                    "risk_category": risk_cat,
                    "risk_score": round(risk_score, 4)
                })
                
            keywords_json_str = json.dumps(keywords, ensure_ascii=False)
            
            # DB 업데이트
            cur.execute("""
                UPDATE counseling_data 
                SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s, updated_at = NOW() 
                WHERE id = %s;
            """, (keywords_json_str, risk_level, external_issue, counseling_id))
            reanalyzed_count += 1
            
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "reanalyzed_count": reanalyzed_count,
            "message": f"총 {reanalyzed_count}건의 상담 내역이 성공적으로 재분석되었습니다."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전체 재분석 처리 실패: {str(e)}")

