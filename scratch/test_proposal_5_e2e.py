import sys
import os

# 현재 디렉토리를 sys.path에 추가하여 worker.py를 임포트할 수 있도록 함
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import classifier

test_cases = [
    {
        "name": "Scenario 1: Preventative Safety Hazard Warning",
        "text": (
            "강남점 앞에 박스들 보행에 너무 불편함을 주고있어요. "
            "골목길도 좁고 학생들 자전거 타고 마주오는 상황도 많은데, 왜 보행에 지장을 주고 있으신지요. "
            "상자 박스 치우려다가 넘어지거나 차도를 침범해서 걷다가 교통사고 위험도 있는데 너무 위험합니다. "
            "개선 부탁드립니다."
        ),
        "expected_category": "안전사고",
        "min_score": 0.55
    },
    {
        "name": "Scenario 2: Administrative Blocker Complaint",
        "text": (
            "강남점 앞에 박스들 보행에 너무 불편함을 주고있어요. "
            "골목길도 좁고 학생들 자전거 타고 마주오는 상황도 많은데, 왜 보행에 지장을 주고 있으신지요. "
            "지켜지지 않으면 구청에 정식 신고하도록 하겠습니다."
        ),
        "expected_category": "법적 이슈",
        "min_score": 0.55
    },
    {
        "name": "Scenario 3: Normal Inquiry Immunity",
        "text": "강남점 영업 시간이 언제인가요?",
        "expected_category": "정상 문의",
        "max_score": 0.55
    },
    {
        "name": "Scenario 4: Harassment & Grooming Separation",
        "text": "점장님이 자꾸 저를 조용한곳으로 유인하시는것 같아요. 불안해서 매장 밖에 있는데 안쪽으로 계속 불러들이고...",
        "expected_category": "성폭력",
        "min_score": 0.53
    }
]

def run_tests():
    print("==================================================")
    print("E2E Validation for Proposal 5 & Thresholds Tuning")
    print("==================================================")
    
    passed_all = True
    for case in test_cases:
        print(f"\n[Test Case] {case['name']}")
        print(f"Input Text: {case['text']}")
        
        category, score = classifier.classify(case['text'])
        print(f"Result Category: '{category}' (Score: {score:.4f})")
        
        expected = case['expected_category']
        
        # 기대하는 카테고리와 일치하는지 체크
        if category != expected:
            print(f" -> FAIL: Expected category '{expected}', but got '{category}'")
            passed_all = False
            continue
            
        # 임계값 조건 체크
        if expected == "정상 문의":
            if 'max_score' in case and score >= case['max_score']:
                print(f" -> FAIL: Normal inquiry triggered safety with high score {score:.4f} (max allowed: {case['max_score']})")
                passed_all = False
            else:
                print(f" -> PASS: Properly classified as normal inquiry with low risk score ({score:.4f})")
        else:
            if score < case['min_score']:
                print(f" -> FAIL: Classified as '{expected}', but score {score:.4f} is below min required {case['min_score']}")
                passed_all = False
            else:
                print(f" -> PASS: Successfully classified as '{expected}' with score {score:.4f} (>= {case['min_score']})")
                
    print("\n==================================================")
    if passed_all:
        print("ALL TESTS PASSED SUCCESSFULLY! PROPOSAL 5 VERIFIED.")
    else:
        print("SOME TESTS FAILED. PLEASE DEBUG.")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
