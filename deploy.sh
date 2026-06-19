#!/bin/bash

# 에러 발생 시 스크립트 중단 (단, 재분석 등 선택적 단계는 별도 처리)
set -e

echo "========================================="
echo "  🚀 서비스 외부 배포 및 재기동 스크립트"
echo "========================================="

# 1. 최신 소스코드 다운로드
echo "👉 [1/6] Git 최신 소스코드 반영..."
if [ -d ".git" ]; then
    # git pull (disabled for local testing)
    echo "Skipping git pull for local testing..."
else
    echo "⚠️ 현재 디렉토리가 Git 저장소가 아닙니다. 로컬 배포 모드로 진행합니다."
fi

# 2. 기존 컨테이너 중지 및 볼륨 유지 상태로 재빌드
echo "👉 [2/6] 컨테이너 중지 및 빌드/재기동..."
docker compose down
docker compose up --build -d

# 3. 데이터베이스 상태 대기 및 초기 스키마 적용
echo "👉 [3/6] PostgreSQL 데이터베이스 연결 대기..."
MAX_WAIT=60
WAITED=0
until docker compose exec -T db pg_isready -U "${DB_USER:-ledger_user}" -d "${DB_NAME:-ledger_db}" > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ DB 연결 타임아웃 (${MAX_WAIT}초). 배포를 중단합니다."
        exit 1
    fi
    echo "⏳ DB가 시작되는 중입니다. 대기 중... (${WAITED}s/${MAX_WAIT}s)"
    sleep 2
    WAITED=$((WAITED + 2))
done

echo "✅ DB 연결 성공. schema.sql 스키마 적용 (테이블 없을 때만 생성)..."
docker compose exec -T db psql -U "${DB_USER:-ledger_user}" -d "${DB_NAME:-ledger_db}" < schema.sql

# 4. 웹 앱 기동 대기 (헬스체크)
echo "👉 [4/6] 웹 앱 기동 대기..."
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:8000/api/health > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️ 웹 앱 헬스체크 타임아웃. 계속 진행합니다..."
        break
    fi
    echo "⏳ 웹 앱 기동 중... (${WAITED}s/${MAX_WAIT}s)"
    sleep 2
    WAITED=$((WAITED + 2))
done

# 5. 기존 DB 데이터 벌크 재분석 (임베딩 서버 준비 여부 확인 후 실행)
echo "👉 [5/6] 기존 DB 데이터 벌크 재분석..."
HEALTH=$(curl -sf http://localhost:8000/api/health 2>/dev/null || echo '{"status":"down"}')
EMB_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('embedding_server','error'))" 2>/dev/null || echo "error")

if [ "$EMB_STATUS" = "ok" ]; then
    echo "✅ 임베딩 서버 준비 완료. 전체 재분석 시작..."
    curl -sf -X POST http://localhost:8000/api/reanalyze-all \
        -H "Content-Type: application/json" \
        -d '{}' \
        && echo "✅ 전체 재분석 완료" \
        || echo "⚠️ 재분석 중 오류 발생. UI에서 수동 실행(🔄 전체 재분석) 가능합니다."
else
    echo "⚠️ 임베딩 서버 미준비 상태. 재분석 건너뜀. 서버 가동 후 UI에서 수동 실행하세요."
fi

# 6. 최종 프로세스 구동 상태 확인
echo "👉 [6/6] 서비스 가동 상태 확인..."
echo "========================================="
docker compose ps
echo "========================================="
echo "🎉 모든 서비스가 성공적으로 재기동되었습니다!"
echo "👉 웹 프로토타입 주소: http://localhost:8000"
echo "👉 시스템 헬스:        http://localhost:8000/api/health"
echo "Celery 로그를 확인하려면: docker compose logs -f celery-worker"
echo "========================================="
