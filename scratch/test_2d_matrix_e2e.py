import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def run_2d_matrix_test():
    print("==================================================")
    # E2E Test: 2D Safety Matrix and Phrase Extraction
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다.\n\n"
        "관련해서 담당자에게 정확한 입장을 원합니다."
    )
    
    print("\n--- TEST 1: 2D Document-Level Classification ---")
    danger_cat, danger_score = classifier.classify_danger(text)
    print(f" -> Danger Axis: '{danger_cat}' (Score: {danger_score:.4f})")
    assert danger_cat == "이물질 상품", f"FAIL: Expected '이물질 상품', got '{danger_cat}'"
    
    external_cat, external_score = classifier.classify_external(text)
    print(f" -> External Axis: '{external_cat}' (Score: {external_score:.4f})")
    assert external_cat == "법적조치", f"FAIL: Expected '법적조치', got '{external_cat}'"
    print("PASS: 2D Document-Level Classification verified successfully!")

    print("\n--- TEST 2: Contextual Phrase Extraction (Candidate verification) ---")
    candidates = extractor._extract_candidates(text, (1, 3))
    print(f"Total Candidate Phrases: {len(candidates)}")
    
    expected_candidates = ["잘린 쥐머리", "병원 응급실 이송됨", "소송 준비", "어제 도시락 구매"]
    for ec in expected_candidates:
        assert ec in candidates, f"FAIL: Expected candidate '{ec}' was NOT extracted!"
    print("PASS: Contextual phrase candidate extraction verified successfully!")

    print("\n--- TEST 3: Dynamic Threshold Phrase Classification ---")
    test_phrases = [
        ("잘린 쥐머리", "이물질 상품"),
        ("병원 응급실 이송됨", "안전사고"),
        ("소송 준비", "법적조치"),
        ("도시락", "정상"),
        ("음식", "정상")
    ]
    
    for phrase, expected_cat in test_phrases:
        mapped_cat, score = classifier.classify_phrase(
            phrase,
            doc_risk_level=danger_cat,
            doc_external_level=external_cat
        )
        print(f"Phrase: '{phrase:<15}' -> Classify: '{mapped_cat:<10}' (Score: {score:.4f})")
        assert mapped_cat == expected_cat, f"FAIL: Expected '{expected_cat}' for '{phrase}', got '{mapped_cat}'"
    print("PASS: Dynamic threshold phrase classification verified successfully!")

    print("\n--- TEST 4: E2E extraction rankings with guided weight ---")
    results = extractor.extract_keywords(
        text=text,
        keyphrase_ngram_range=(1, 3),
        top_n=8,
        doc_risk_level=danger_cat,
        doc_external_level=external_cat,
        classifier=classifier,
        weight_coeff=0.35
    )
    
    print("\nRanked Keywords:")
    for rank, (word, score) in enumerate(results, 1):
        mapped_cat, r_score = classifier.classify_phrase(word, doc_risk_level=danger_cat, doc_external_level=external_cat)
        print(f" {rank}. '{word:<18}' | ExtrScore: {score:.4f} | Mapped: {mapped_cat} ({r_score:.4f})")
        
    # Check that danger and external phrases are in the top 8 cloud
    top_words = [r[0] for r in results]
    assert any("쥐" in w for w in top_words), "FAIL: Severity words like '쥐' should float to the top!"
    assert any("이송" in w or "응급실" in w for w in top_words), "FAIL: Severity words like '이송'/'응급실' should float to the top!"
    assert any("소송" in w for w in top_words), "FAIL: Pressure words like '소송' should float to the top!"
    print("PASS: E2E keyword rankings successfully verified!")

    print("\n==================================================")
    print("ALL 2D SAFETY MATRIX MATRIX E2E TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_2d_matrix_test()
