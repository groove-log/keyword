import sys
import os

# 현재 디렉토리를 sys.path에 추가하여 worker.py를 임포트할 수 있도록 함
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def test_nominalized_verb_extraction():
    print("\n--- TEST 1: Nominalized Verb Extraction (TDD) ---")
    text = "상자를 치우려다가 넘어지거나 차도로 침범해서 다치면 큰일납니다."
    
    # 후보군 추출 내부 메서드 직접 호출
    candidates = extractor._extract_candidates(text, (1, 2))
    print(f"Extracted Candidates: {candidates}")
    
    # 동사 '넘어지다' -> '넘어짐', '다치다' -> '다침'이 포함되어 있어야 합니다.
    assert "넘어짐" in candidates, "FAIL: '넘어짐' should be extracted from '넘어지거나'"
    assert "다침" in candidates, "FAIL: '다침' should be extracted from '다치면'"
    print("PASS: Nominalized verbs extracted successfully!")

def test_category_guided_weighting():
    print("\n--- TEST 2: Category-Guided Keyword Weighting (TDD) ---")
    text = (
        "강남점 앞에 박스들 보행에 너무 불편함을 주고있어요. "
        "골목길도 좁고 학생들 자전거 타고 마주오는 상황도 많은데, 왜 보행에 지장을 주고 있으신지요. "
        "상자 박스 치우려다가 넘어지거나 차도를 침범해서 걷다가 교통사고 위험도 있는데 너무 위험합니다. "
        "개선 부탁드립니다."
    )
    
    # 1. 가중치 없이 일반 추출 시 (Top 3)
    normal_keywords = [kw[0] for kw in extractor.extract_keywords(text, (1, 2), top_n=3)]
    print(f"Normal Keywords (No Weighting): {normal_keywords}")
    
    # 2. 안전사고(doc_risk_level) 가중치 적용 추출 시
    weighted_keywords = [
        kw[0] for kw in extractor.extract_keywords(
            text, 
            (1, 2), 
            top_n=3, 
            doc_risk_level="안전사고", 
            classifier=classifier, 
            weight_coeff=0.35
        )
    ]
    print(f"Weighted Keywords ('안전사고' Guided): {weighted_keywords}")
    
    # 가중치를 주면 위험 식별 단어인 '교통사고'나 '넘어짐' 혹은 복합명사 '교통사고 위험' 등이 Top 3에 포함되어 있어야 합니다.
    has_match = any("교통사고" in kw or "넘어짐" in kw for kw in weighted_keywords)
    assert has_match, f"FAIL: Expected danger keywords like '교통사고' or '넘어짐' in weighted output: {weighted_keywords}"
    print("PASS: Category-guided weighting pulled up danger keywords successfully!")

if __name__ == "__main__":
    failed = False
    try:
        test_nominalized_verb_extraction()
    except AssertionError as e:
        print(f"Test 1 Failed: {e}")
        failed = True
        
    try:
        test_category_guided_weighting()
    except Exception as e:
        print(f"Test 2 Failed: {e}")
        failed = True
        
    if failed:
        sys.exit(1)
    else:
        print("\nALL TDD TESTS PASSED!")
        sys.exit(0)
