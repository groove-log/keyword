"""
성폭력 vs 폭력 및 폭행 카테고리 경계 오인 분석 테스트
- 명확한 성폭력 시나리오
- 명확한 폭력/폭행 시나리오
- 경계 혼동 시나리오 (물리적 접촉 + 성적 아닌 문맥)
- 언어폭력 시나리오
"""
import requests
import json

API = "http://localhost:8000/api/extract/sync"

test_cases = [
    # ── 명확한 성폭력 ──
    ("성폭력-1", "점장이 여직원에게 계속 음담패설을 하고 퇴근 후에 술자리를 강요합니다. 거절하면 불이익을 주겠다고 합니다."),
    ("성폭력-2", "매장 관리자가 밀폐된 사무실로 자꾸 불러들여서 단둘이 있으면서 신체적 접촉을 시도합니다. 너무 무섭습니다."),
    ("성폭력-3", "점장님이 자꾸 허리랑 어깨를 만지고 몸에 손을 대는데 성추행이 아닌가요?"),
    
    # ── 명확한 폭력/폭행 ──
    ("폭행-1", "경영주가 갑자기 주먹으로 때리고 물건을 집어던졌습니다. 너무 무서웠습니다."),
    ("폭행-2", "화가 나서 죽여버리겠다고 소리치면서 멱살을 잡고 밀쳤습니다."),
    ("폭행-3", "손님이 직원에게 욕설을 퍼부으며 컵을 던지고 기물을 파손했습니다."),
    
    # ── 경계 혼동 가능 시나리오 ──
    ("경계-1", "점장이 늦게까지 일 시키면서 조용한 곳에서 심하게 다그치고 물건을 던졌습니다."),
    ("경계-2", "관리자가 단둘이 불러서 욕설을 하며 위협적으로 다가왔습니다. 너무 무서워서 떨었습니다."),
    ("경계-3", "사장이 사무실로 부르더니 고함을 지르면서 서류를 집어던지고 뺨을 때렸습니다."),
    ("경계-4", "경영주가 여직원을 자꾸 밀폐된 방에 가두고 소리를 지르며 협박합니다."),
    
    # ── 언어폭력 (물리적 접촉 없음) ──
    ("언어폭력-1", "경영주가 모든 직원 앞에서 저한테만 심하게 욕을 하고 인격모독을 합니다."),
    ("언어폭력-2", "점장이 매일 씩씩대면서 저를 무시하고 반말로 막대합니다. 화를 못 참고 기계를 던지기도 합니다."),
]

print("=" * 100)
print("   성폭력 vs 폭력/폭행 카테고리 경계 오인 분석")
print("=" * 100)

for label, text in test_cases:
    resp = requests.post(API, json={"text": text}, timeout=60)
    data = resp.json()
    
    danger_cats = data.get("detected_categories", {}).get("danger", [])
    risk_level = data.get("risk_level", "N/A")
    risk_score = data.get("risk_score", 0)
    
    # 성폭력과 폭력/폭행 점수 추출
    sex_score = None
    violence_score = None
    for cat in danger_cats:
        if cat["category"] == "성폭력":
            sex_score = cat["score"]
        if cat["category"] == "폭력 및 폭행":
            violence_score = cat["score"]
    
    print(f"\n{'─' * 100}")
    print(f"  [{label}]")
    print(f"  텍스트: {text[:60]}...")
    print(f"  ▸ 최종 판정: {risk_level} (score: {risk_score})")
    print("  ▸ 탐지된 카테고리:", [f"{c['category']}({c['score']:.4f})" for c in danger_cats])
    if sex_score is not None and violence_score is not None:
        gap = abs(sex_score - violence_score)
        print(f"  ⚠️ 양 카테고리 동시 탐지! 성폭력={sex_score:.4f} vs 폭력/폭행={violence_score:.4f} (차이: {gap:.4f})")
    elif sex_score is not None:
        print(f"  🔴 성폭력만 탐지: {sex_score:.4f}")
    elif violence_score is not None:
        print(f"  🟠 폭력/폭행만 탐지: {violence_score:.4f}")
    else:
        print(f"  🟢 두 카테고리 모두 미탐지")

print(f"\n{'=' * 100}")
print("   분석 완료")
print("=" * 100)
