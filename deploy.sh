#!/bin/bash

# 에러 발생 시 스크립트 중단
set -e

echo "========================================="
echo "  🚀 서비스 외부 배포 및 재기동 스크립트"
echo "========================================="

# 1. 최신 소스코드 다운로드
echo "👉 [1/5] Git 최신 소스코드 반영..."
if [ -d ".git" ]; then
    # git pull (disabled for local testing)
    echo "Skipping git pull for local testing..."
else
    echo "⚠️ 현재 디렉토리가 Git 저장소가 아닙니다. 로컬 배포 모드로 진행합니다."
fi

# 2. 기존 컨테이너 중지 및 볼륨 유지 상태로 재빌드
echo "👉 [2/5] 컨테이너 중지 및 빌드/재기동..."
docker compose down
docker compose up --build -d

# 3. 데이터베이스 상태 대기 및 초기 스키마 적용
echo "👉 [3/5] PostgreSQL 데이터베이스 연결 대기..."
# PostgreSQL이 완전히 켜질 때까지 2초 간격으로 확인
until docker compose exec -T db pg_isready -U ledger_user -d ledger_db > /dev/null 2>&1; do
    echo "⏳ DB가 시작되는 중입니다. 대기 중..."
    sleep 2
done

echo "✅ DB 연결 성공. schema.sql 스키마 적용 (테이블이 없을 때만 생성)..."
docker compose exec -T db psql -U ledger_user -d ledger_db < schema.sql

# 4. 신규 2D 안전 매트릭스 기준 DB 벌크 재분석 및 마이그레이션 실행
echo "👉 [4/5] 기존 DB 데이터 신규 2D 안전 매트릭스 벌크 재분석 실행..."
# llama.cpp 서버 구동 속도에 따라 API가 즉각 호출되지 않을 수 있으므로 실패해도 배포가 중단되지 않도록 우회 설정 적용
docker compose exec -T web-app python scratch/reanalyze_db.py || echo "⚠️ 벌크 재분석 알림: 임베딩 서버 미준비 등으로 인해 재분석 실행을 우회합니다. 서버 가동 완료 후 웹 UI에서 수동 실행(🔄 전체 재분석)할 수 있습니다."

# 5. 최종 프로세스 구동 상태 확인
echo "👉 [5/5] 서비스 가동 상태 확인..."
echo "========================================="
docker compose ps
echo "========================================="
echo "🎉 모든 서비스가 성공적으로 재기동되었습니다!"
echo "👉 웹 프로토타입 주소: http://localhost:8000"
echo "Celery 로그를 확인하려면 아래 명령어를 입력하세요:"
echo "👉 docker compose logs -f celery-worker"
echo "========================================="
