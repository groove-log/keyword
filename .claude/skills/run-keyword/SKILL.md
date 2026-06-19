---
name: run-keyword
description: run, start, launch, test, screenshot, smoke-test the IRDA keyword risk detection service — FastAPI web app, Celery worker, PostgreSQL, Redis, llama.cpp embedding server
---

# IRDA — run & smoke test

FastAPI 웹 앱(port 8000) + Celery 워커 + Redis + PostgreSQL 로 구성된 한국어 위험 탐지 서비스.
외부 의존: llama.cpp 임베딩 서버(port 8081, Docker 외부에서 별도 구동).

드라이버: `.claude/skills/run-keyword/smoke.sh` — curl 기반 5단계 smoke test.

---

## Prerequisites

```bash
# Python 의존성 (로컬 실행 시)
pip install -r requirements.txt

# Docker Compose (컨테이너 실행 시)
docker compose version   # v2 필요
```

`.env` 파일이 프로젝트 루트에 있어야 함. 최소 필수값:
```
LLAMA_API_URL=http://localhost:8081
LLAMA_API_KEY=embed-secure-key-1122
DB_NAME=ledger_db  DB_USER=ledger_user  DB_PASSWORD=ledger_pass
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## Build & Launch

```bash
# 전체 스택 (Redis + DB + Celery + web-app)
bash deploy.sh
# → DB 기동 대기(최대 60s) → schema.sql 적용 → 헬스체크 → 선택적 전체 재분석

# 또는 수동
docker compose up --build -d
```

llama.cpp 임베딩 서버는 Docker 외부에서 별도 구동 필요:
```bash
# 예시 (모델 경로는 환경에 따라 다름)
./llama-server --model bge-m3.gguf --port 8081 --embedding
```

---

## Run (agent path) — smoke test

```bash
bash .claude/skills/run-keyword/smoke.sh [base_url]
# 기본값: http://localhost:8000
```

**5단계 검증:**
1. `/api/health` — embedding_server=ok, database=ok 확인
2. `/api/settings` — 임계값 로드 확인
3. `/api/extract/sync` — 이물질+IMMEDIATE 케이스 탐지 확인
4. `/api/extract/async` → Celery → COMPLETED 확인 (최대 20초 대기)
5. `/api/stats` — DB 기록 건수 확인

모두 통과하면 `=== 모든 테스트 통과 (5/5) ===` 출력. 실패 시 즉시 종료 + 원인 출력.

---

## Run (agent path) — 개별 API 호출

```bash
BASE=http://localhost:8000

# 헬스체크
curl -s $BASE/api/health

# 동기 분석 (즉시 결과, DB 저장 없음)
curl -s -X POST $BASE/api/extract/sync \
  -H "Content-Type: application/json" \
  -d '{"text":"분석할 텍스트","top_n":5}'

# 비동기 등록 (Celery 처리, DB 저장)
curl -s -X POST $BASE/api/extract/async \
  -H "Content-Type: application/json" \
  -d '{"text":"분석할 텍스트","top_n":5}'

# 결과 조회 (최신 100건)
curl -s $BASE/api/history

# 통계
curl -s $BASE/api/stats

# 피드백 제출 (id는 history에서 확인)
curl -s -X POST $BASE/api/feedback/123 \
  -H "Content-Type: application/json" \
  -d '{"is_correct":false,"actual_danger":"식품위생","note":"오분류"}'

# 임계값 보정 제안
curl -s $BASE/api/threshold-calibrate
```

---

## Run (human path)

```bash
# 로컬 개발 서버 (hot-reload)
uvicorn web_app:app --reload --port 8000
# → http://localhost:8000 브라우저 열기

# Celery 워커 별도 실행
celery -A worker.app worker --loglevel=info
```

---

## Gotchas

- **임베딩 서버 없으면 전부 "정상 문의"**: llama.cpp가 8081에서 응답 안 하면 베이스라인 캐시 초기화 실패 → 모든 분류가 기본값("정상 문의") 반환. `health.embedding_server`가 `"ok"`인지 먼저 확인.

- **DB 포트 5433**: 로컬에서 직접 접속 시 `localhost:5433` (컨테이너 내부는 5432). `psql -p 5433`으로 확인.

- **베이스라인 캐시는 메모리**: 프로세스(또는 컨테이너) 재시작 시 초기화. 첫 분석 요청 때 llama.cpp에 84회 임베딩 요청 → 약 2~10초 지연 발생.

- **과거형 시급성**: "어제 응급실 다녀왔어요" → SHORT-TERM (IMMEDIATE 아님). Kiwi 형태소 분석으로 었/았/했/됐 감지. 이 동작이 예상과 다르면 Kiwi 설치 버전 확인.

- **async 처리 지연**: Celery 워커가 `docker compose logs celery-worker`에서 에러 없이 구동 중이어야 함. smoke.sh는 20초 대기 후 실패 처리.

---

## Troubleshooting

| 증상 | 원인 | 조치 |
|------|------|------|
| `health.embedding_server = "error"` | llama.cpp 미구동 | `./llama-server --model ... --port 8081 --embedding` |
| `health.database = "error"` | PostgreSQL 미시작 | `docker compose up db -d` |
| smoke step 4 실패 (async timeout) | Celery 워커 중단 | `docker compose logs celery-worker` → `docker compose restart celery-worker` |
| 모든 결과 "정상 문의" | 임베딩 서버 OR 임계값 너무 높음 | health 확인 후 UI에서 감도 "민감"으로 변경 테스트 |
| `psycopg.OperationalError` | DB 연결 실패 | `.env`의 DB_HOST/PORT 확인 (`127.0.0.1:5433`) |
