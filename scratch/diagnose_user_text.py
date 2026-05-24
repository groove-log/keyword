import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def run_diagnosis():
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다.\n\n"
        "관련해서 담당자에게 정확한 입장을 원합니다."
    )
    
    # 1. 문서 분류
    risk_level, sim_score = classifier.classify(text)
    print(f"Document Classification: '{risk_level}' (Score: {sim_score:.4f})")
    
    # 2. 키워드 추출 (top 8)
    keywords_with_scores = extractor.extract_keywords(
        text,
        keyphrase_ngram_range=(2, 3), # UI is using 2~3단어 위주 (2-3) or 1~2? In screen it says: N-gram: 2~3단어 위주 (2-3), Top N: 상위 8개 키워드
        top_n=8,
        doc_risk_level=risk_level,
        classifier=classifier,
        weight_coeff=0.35
    )
    
    print("\n--- Extracted Keywords & Their Classification ---")
    custom_thresholds = {
        "폭력 및 폭행": 0.58,
        "성폭력": 0.53,
        "이물질 상품": 0.60,
        "안전사고": 0.55,
        "법적 이슈": 0.55
    }
    # UI might have lowered the thresholds as user said:
    # "이물질 상품 임계치를 낮추었고 위험 키워드 임계치를 낮추어서 겨우 이런 결과가 나온건데..."
    # Let's say user set thresholds to: 이물질 상품 = 0.50, linked_threshold = 0.40, min_safeguard_score = 0.45
    custom_thresholds["이물질 상품"] = 0.50
    linked_threshold = 0.40
    min_safeguard = 0.45
    
    print(f"Using Custom Settings: thresholds={custom_thresholds}, linked_threshold={linked_threshold}, min_safeguard={min_safeguard}")
    
    for word, score in keywords_with_scores:
        risk_cat, risk_score = classifier.classify_phrase(
            word,
            custom_thresholds=custom_thresholds,
            doc_risk_level=risk_level,
            custom_linked_threshold=linked_threshold,
            custom_min_safeguard=min_safeguard
        )
        print(f"Keyword: '{word}' | ExtrScore: {score:.4f} | Classify: '{risk_cat}' (SimScore: {risk_score:.4f})")

if __name__ == "__main__":
    run_diagnosis()
