import os
import time
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psycopg
from dotenv import load_dotenv

logger = logging.getLogger("keyword_webapp")

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
    top_n: int = 5
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

# 1.2. 프로젝트 가이드 및 기술 백서 페이지 서빙
@app.get("/guide.html", response_class=HTMLResponse)
@app.get("/guide", response_class=HTMLResponse)
async def read_guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

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
        # 1. 3D 위험 매트릭스 및 시급성 판별 진행
        dangers = classifier.classify_danger(req.text, req.thresholds)
        externals = classifier.classify_external(req.text, req.thresholds)
        urgency_level = classifier.classify_urgency(req.text)
        
        # 대표 단일값 및 최고 점수 지정
        risk_level = dangers[0][0]
        sim_score = dangers[0][1]
        
        external_issue = externals[0][0]
        ext_score = externals[0][1]
        
        # 심각도 판정
        all_risk_cats = [cat for cat, _ in dangers]
        severity = classifier.classify_severity(req.text, all_risk_cats, urgency_level)

        # 다중 매핑 스키마 메타데이터 구조화
        detected_json = {
            "danger": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(dangers)],
            "external": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(externals)],
            "severity": severity
        }

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
            "external_score": round(ext_score, 4),
            "urgency_level": urgency_level,
            "severity": severity,
            "detected_categories": detected_json
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

# 4. DB 히스토리 최신 10건 조회 API (3D 입체 필드 추가)
@app.get("/api/history")
async def get_history():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, text, keywords, status, updated_at, risk_level, external_issue, urgency_level, detected_categories 
            FROM counseling_data 
            ORDER BY id DESC 
            LIMIT 100;
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
                "external_issue": row[6] if row[6] else "정상 문의",
                "urgency_level": row[7] if row[7] else "MONITOR",
                "detected_categories": row[8] if row[8] else ""
              })
            
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 실패: {str(e)}")

# 5. 건별 재분석 API
class ReanalyzeRequest(BaseModel):
    thresholds: dict[str, float] = None
    linked_threshold: float = None
    min_safeguard_score: float = None

@app.post("/api/reanalyze/{counseling_id}")
async def reanalyze_case(counseling_id: int, req: ReanalyzeRequest = None):
    req = req or ReanalyzeRequest()
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
        dangers = classifier.classify_danger(text, req.thresholds)
        externals = classifier.classify_external(text, req.thresholds)
        urgency_level = classifier.classify_urgency(text)
        
        risk_level = dangers[0][0]
        sim_score = dangers[0][1]
        
        external_issue = externals[0][0]
        ext_score = externals[0][1]
        
        all_risk_cats = [cat for cat, _ in dangers]
        severity = classifier.classify_severity(text, all_risk_cats, urgency_level)

        detected_json = {
            "danger": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(dangers)],
            "external": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(externals)],
            "severity": severity
        }
        detected_categories_str = json.dumps(detected_json, ensure_ascii=False)

        weight_coeff = float(os.getenv("DANGER_KEYWORD_GUIDE_WEIGHT", "0.35"))
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

        keywords_json_str = json.dumps(keywords, ensure_ascii=False)

        # 3. DB 업데이트
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE counseling_data
            SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s,
                urgency_level = %s, detected_categories = %s, updated_at = NOW()
            WHERE id = %s;
        """, (keywords_json_str, risk_level, external_issue, urgency_level, detected_categories_str, counseling_id))
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "counseling_id": counseling_id,
            "risk_level": risk_level,
            "external_issue": external_issue,
            "urgency_level": urgency_level,
            "severity": severity,
            "detected_categories": detected_json,
            "keywords": keywords
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재분석 처리 실패: {str(e)}")

# 6. 전체 재분석 API
class ReanalyzeAllRequest(BaseModel):
    thresholds: dict[str, float] = None
    linked_threshold: float = None
    min_safeguard_score: float = None

@app.post("/api/reanalyze-all")
async def reanalyze_all_cases(req: ReanalyzeAllRequest = None):
    req = req or ReanalyzeAllRequest()
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. 기존 전체 데이터 조회
        cur.execute("SELECT id, text FROM counseling_data ORDER BY id ASC;")
        rows = cur.fetchall()

        reanalyzed_count = 0
        for counseling_id, text in rows:
            dangers = classifier.classify_danger(text, req.thresholds)
            externals = classifier.classify_external(text, req.thresholds)
            urgency_level = classifier.classify_urgency(text)

            risk_level = dangers[0][0]
            external_issue = externals[0][0]

            all_risk_cats = [cat for cat, _ in dangers]
            severity = classifier.classify_severity(text, all_risk_cats, urgency_level)

            detected_json = {
                "danger": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(dangers)],
                "external": [{"category": cat, "score": round(score, 4), "primary": (idx == 0)} for idx, (cat, score) in enumerate(externals)],
                "severity": severity
            }
            detected_categories_str = json.dumps(detected_json, ensure_ascii=False)

            weight_coeff = float(os.getenv("DANGER_KEYWORD_GUIDE_WEIGHT", "0.35"))
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
                
            keywords_json_str = json.dumps(keywords, ensure_ascii=False)
            
            # DB 업데이트
            cur.execute("""
                UPDATE counseling_data 
                SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s, urgency_level = %s, detected_categories = %s, updated_at = NOW() 
                WHERE id = %s;
            """, (keywords_json_str, risk_level, external_issue, urgency_level, detected_categories_str, counseling_id))
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


# 7. 오분류 피드백 API
class FeedbackRequest(BaseModel):
    is_correct: bool
    actual_danger: str = None       # 실제 위험 카테고리 (오분류 시)
    actual_external: str = None     # 실제 외부 카테고리 (오분류 시)
    actual_urgency: str = None      # 실제 시급성 (오분류 시)
    note: str = None                # 상담원 메모

@app.post("/api/feedback/{counseling_id}")
async def submit_feedback(counseling_id: int, req: FeedbackRequest):
    """상담원이 오분류를 신고하거나 올바른 분류를 확인하는 피드백 수집"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # feedback 테이블이 없으면 생성 (마이그레이션 없이 자동 처리)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS counseling_feedback (
                id          SERIAL PRIMARY KEY,
                counseling_id INT NOT NULL,
                is_correct  BOOLEAN NOT NULL,
                actual_danger VARCHAR(100),
                actual_external VARCHAR(100),
                actual_urgency VARCHAR(50),
                note        TEXT,
                created_at  TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            INSERT INTO counseling_feedback
                (counseling_id, is_correct, actual_danger, actual_external, actual_urgency, note)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (counseling_id, req.is_correct, req.actual_danger, req.actual_external, req.actual_urgency, req.note))

        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "피드백이 기록되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 저장 실패: {str(e)}")


@app.get("/api/feedback/summary")
async def get_feedback_summary():
    """피드백 집계 — 오분류율, 카테고리별 정확도"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM counseling_feedback")
        if cur.fetchone()[0] == 0:
            cur.close(); conn.close()
            return {"total": 0, "message": "아직 피드백이 없습니다."}

        cur.execute("SELECT is_correct, COUNT(*) FROM counseling_feedback GROUP BY is_correct")
        rows = {row[0]: row[1] for row in cur.fetchall()}
        total = sum(rows.values())
        correct = rows.get(True, 0)

        cur.execute("""
            SELECT actual_danger, COUNT(*) FROM counseling_feedback
            WHERE is_correct = false AND actual_danger IS NOT NULL
            GROUP BY actual_danger ORDER BY COUNT(*) DESC LIMIT 10
        """)
        top_corrections = [{"category": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()
        return {
            "total": total,
            "correct": correct,
            "incorrect": total - correct,
            "accuracy_pct": round(correct / total * 100, 1),
            "top_corrections": top_corrections
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 조회 실패: {str(e)}")


# 8. 피드백 기반 임계값 자동 보정 제안 API
@app.get("/api/threshold-calibrate")
async def calibrate_thresholds():
    """
    피드백 데이터를 분석하여 각 카테고리별 임계값 조정 방향을 제안.
    - 오분류가 많은 카테고리: 임계값 상향 (false positive 감소)
    - 누락이 많은 카테고리: 임계값 하향 (false negative 감소)
    실제 .env 파일을 수정하지 않으며, 제안(suggestion)만 반환합니다.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 피드백 테이블 존재 확인
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'counseling_feedback'
            )
        """)
        if not cur.fetchone()[0]:
            cur.close(); conn.close()
            return {"suggestions": [], "message": "피드백 데이터가 아직 없습니다. 상담원 피드백이 누적되면 자동 보정이 가능합니다."}

        # 오분류된 케이스에서 실제 카테고리와 분류 결과의 불일치 집계
        cur.execute("""
            SELECT f.actual_danger, c.risk_level, COUNT(*) as cnt
            FROM counseling_feedback f
            JOIN counseling_data c ON c.id = f.counseling_id
            WHERE f.is_correct = false AND f.actual_danger IS NOT NULL
            GROUP BY f.actual_danger, c.risk_level
            ORDER BY cnt DESC
        """)
        mismatch_rows = cur.fetchall()

        # 카테고리별 정확도 계산
        cur.execute("""
            SELECT c.risk_level,
                   SUM(CASE WHEN f.is_correct THEN 1 ELSE 0 END) as correct_cnt,
                   COUNT(*) as total_cnt
            FROM counseling_feedback f
            JOIN counseling_data c ON c.id = f.counseling_id
            GROUP BY c.risk_level
        """)
        accuracy_rows = cur.fetchall()

        cur.close()
        conn.close()

        # 현재 임계값
        current_thresholds = {**classifier.thresholds}

        suggestions = []
        for risk_level, correct_cnt, total_cnt in accuracy_rows:
            if total_cnt < 5:
                continue  # 샘플 부족 시 제안 없음
            accuracy = correct_cnt / total_cnt
            current = current_thresholds.get(risk_level, classifier.threshold)

            if accuracy < 0.6 and risk_level != "정상 문의":
                # 오분류율 40% 이상 → 임계값 상향 (더 엄격하게)
                suggested = round(min(0.95, current + 0.03), 3)
                suggestions.append({
                    "category": risk_level,
                    "current_threshold": current,
                    "suggested_threshold": suggested,
                    "direction": "up",
                    "reason": f"오분류율 {round((1-accuracy)*100)}% (샘플 {total_cnt}건) — 임계값 상향으로 false positive 감소",
                    "accuracy_pct": round(accuracy * 100, 1)
                })
            elif accuracy > 0.9 and risk_level != "정상 문의":
                # 정확도 90% 이상 → 임계값 소폭 하향도 고려 (더 민감하게)
                suggested = round(max(0.10, current - 0.02), 3)
                suggestions.append({
                    "category": risk_level,
                    "current_threshold": current,
                    "suggested_threshold": suggested,
                    "direction": "down",
                    "reason": f"정확도 {round(accuracy*100)}% (샘플 {total_cnt}건) — 안전 범위 내 임계값 소폭 하향 고려",
                    "accuracy_pct": round(accuracy * 100, 1)
                })

        return {
            "suggestions": suggestions,
            "total_feedback_analyzed": sum(r[2] for r in accuracy_rows),
            "note": "제안 수치는 참고용이며, .env 파일 수동 수정 후 서버 재시작이 필요합니다."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임계값 보정 분석 실패: {str(e)}")


# 10. 시스템 헬스 체크 API
@app.get("/api/health")
async def health_check():
    """임베딩 서버 및 DB 연결 상태 확인"""
    results = {"status": "ok", "embedding_server": "unknown", "database": "unknown"}

    # 임베딩 서버 확인
    try:
        test_emb = extractor._get_embedding("헬스체크")
        results["embedding_server"] = "ok" if test_emb else "error"
    except Exception as e:
        results["embedding_server"] = f"error: {str(e)}"
        results["status"] = "degraded"

    # DB 연결 확인
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        results["database"] = "ok"
    except Exception as e:
        results["database"] = f"error: {str(e)}"
        results["status"] = "degraded"

    return results


# 11. PENDING 타임아웃 정리 API (1시간 이상 PENDING 기록을 TIMEOUT으로 처리)
@app.post("/api/cleanup-pending")
async def cleanup_pending():
    """1시간 이상 PENDING 상태인 고아 기록을 TIMEOUT으로 정리"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE counseling_data
            SET status = 'TIMEOUT', updated_at = NOW()
            WHERE status = 'PENDING'
              AND created_at < NOW() - INTERVAL '1 hour'
        """)
        affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "cleaned_up": affected, "message": f"{affected}건의 타임아웃 기록을 정리했습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PENDING 정리 실패: {str(e)}")


# 12. DB 통계 API
@app.get("/api/stats")
async def get_stats():
    """상태별 기록 수, 위험 카테고리 분포, 시급성 분포 등 집계"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT status, COUNT(*) FROM counseling_data GROUP BY status")
        status_counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("""
            SELECT risk_level, COUNT(*) FROM counseling_data
            WHERE status = 'COMPLETED' GROUP BY risk_level ORDER BY COUNT(*) DESC
        """)
        risk_counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("""
            SELECT urgency_level, COUNT(*) FROM counseling_data
            WHERE status = 'COMPLETED' GROUP BY urgency_level
        """)
        urgency_counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) FROM counseling_data")
        total = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "total": total,
            "by_status": status_counts,
            "by_risk_level": risk_counts,
            "by_urgency": urgency_counts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")

