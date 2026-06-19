#!/usr/bin/env bash
# IRDA smoke test — 실제 구동 중인 서비스에 대해 실행
# 사용: bash .claude/skills/run-keyword/smoke.sh [base_url]
set -euo pipefail

BASE="${1:-http://localhost:8000}"

pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; exit 1; }

echo "=== IRDA smoke test → $BASE ==="

# 1. health
echo "[1/5] health"
H=$(curl -sf "$BASE/api/health") || fail "health 엔드포인트 응답 없음"
EMB=$(echo "$H" | python3 -c "import sys,json; print(json.load(sys.stdin)['embedding_server'])")
DB=$(echo  "$H" | python3 -c "import sys,json; print(json.load(sys.stdin)['database'])")
[ "$EMB" = "ok" ] || fail "embedding_server=$EMB (llama.cpp 미구동)"
[ "$DB"  = "ok" ] || fail "database=$DB (PostgreSQL 미연결)"
pass "embedding_server=ok, database=ok"

# 2. settings (임계값 확인)
echo "[2/5] settings"
S=$(curl -sf "$BASE/api/settings")
THRESH=$(echo "$S" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['default_thresholds']['이물질 상품'])")
[ -n "$THRESH" ] || fail "default_thresholds 없음"
pass "이물질 상품 임계값=$THRESH"

# 3. sync 분석 — 이물질+법적+IMMEDIATE 케이스
echo "[3/5] extract/sync"
SYNC=$(curl -sf -X POST "$BASE/api/extract/sync" \
  -H "Content-Type: application/json" \
  -d '{"text":"도시락에서 바퀴벌레가 나왔습니다. 지금 당장 소비자원에 신고하겠습니다.","top_n":3}')
RISK=$(echo "$SYNC" | python3 -c "import sys,json; print(json.load(sys.stdin)['risk_level'])")
URG=$(echo  "$SYNC" | python3 -c "import sys,json; print(json.load(sys.stdin)['urgency_level'])")
SEV=$(echo  "$SYNC" | python3 -c "import sys,json; print(json.load(sys.stdin)['severity']['score'])")
[ "$RISK" != "정상 문의" ] || fail "위험 탐지 실패 (risk_level=정상 문의)"
[ "$URG"  = "IMMEDIATE"  ] || fail "시급성 판정 실패 (urgency=$URG, 예상 IMMEDIATE)"
pass "risk=$RISK  urgency=$URG  severity=$SEV/10"

# 4. async 파이프라인
echo "[4/5] extract/async → Celery → COMPLETED"
AR=$(curl -sf -X POST "$BASE/api/extract/async" \
  -H "Content-Type: application/json" \
  -d '{"text":"직원이 손님을 성추행했다는 신고가 들어왔습니다.","top_n":3}')
AID=$(echo "$AR" | python3 -c "import sys,json; print(json.load(sys.stdin)['counseling_id'])")
[ -n "$AID" ] || fail "async 등록 실패"

for i in $(seq 1 10); do
  sleep 2
  STATUS=$(curl -sf "$BASE/api/history" | python3 -c "
import sys,json
data=json.load(sys.stdin)
for r in data:
    if r['id']==$AID: print(r['status']); break
" 2>/dev/null || echo "PENDING")
  [ "$STATUS" = "COMPLETED" ] && break
done
[ "$STATUS" = "COMPLETED" ] || fail "async id=$AID 완료 안 됨 (status=$STATUS)"
pass "async id=$AID → COMPLETED"

# 5. stats
echo "[5/5] stats"
ST=$(curl -sf "$BASE/api/stats")
TOTAL=$(echo "$ST" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
[ "$TOTAL" -gt 0 ] || fail "DB 기록 0건"
pass "total=$TOTAL 건 확인"

echo ""
echo "=== 모든 테스트 통과 (5/5) ==="
