import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import classifier, extractor

def run_3d_matrix_test():
    print("==================================================")
    print("      E2E Integration Test: 3D Triage Engine      ")
    print("==================================================")
    
    # Complex case with co-occurring threats and high urgency:
    # Danger co-occurrence: "이물질 상품" (잘린 쥐머리) + "안전사고" (구토 및 정신적 충격으로 병원 응급실 이송)
    # External co-occurrence: "법적조치" (소송준비) + "언론제보" (언론사 제보)
    # Z-axis Urgency: IMMEDIATE (당장, 즉시, 응급실)
    text_immediate = (
        "당장 해결책을 내놓으세요. 어제 매장 앞 빙판길에서 미끄러져 넘어지는 낙상 사고를 당했습니다! "
        "머리를 세게 부딪혀 뼈가 부러졌고, 구토 증상 때문에 119 구급차로 병원 응급실에 즉시 이송되었습니다. "
        "또한 구매했던 도시락에서도 잘린 쥐머리가 발견되어 위생 상태도 엉망입니다. "
        "언론사에 제보하고 즉각적인 법적 소송도 함께 개시할 테니 각오하십시오."
    )
    
    print("\n--- TEST 1: Z-Axis Urgency Classification ---")
    urgency_immediate = classifier.classify_urgency(text_immediate)
    print(f" -> Text Urgency: '{urgency_immediate}'")
    assert urgency_immediate == "IMMEDIATE", f"FAIL: Expected 'IMMEDIATE', got '{urgency_immediate}'"
    
    # Text with short-term SLA lexicon:
    text_shortterm = "이번주 안으로 기한 맞춰서 환불해주지 않으면 신고하겠습니다."
    urgency_shortterm = classifier.classify_urgency(text_shortterm)
    print(f" -> Text Urgency (Short-term): '{urgency_shortterm}'")
    assert urgency_shortterm == "SHORT-TERM", f"FAIL: Expected 'SHORT-TERM', got '{urgency_shortterm}'"
    
    # Text with standard monitor SLA:
    text_monitor = "일반 제품 사용법 문의드립니다. 혹시 충전은 어떻게 하나요?"
    urgency_monitor = classifier.classify_urgency(text_monitor)
    print(f" -> Text Urgency (Monitor): '{urgency_monitor}'")
    assert urgency_monitor == "MONITOR", f"FAIL: Expected 'MONITOR', got '{urgency_monitor}'"
    print("PASS: Z-Axis Urgency classification verified successfully!")
    
    print("\n--- TEST 2: Multi-Label Co-occurrence (Danger Axis) ---")
    danger_cats = classifier.classify_danger(text_immediate)
    print("Detected Danger Categories:")
    for cat, score in danger_cats:
        print(f"  * Category: '{cat:<12}' | Similarity: {score:.4f}")
        
    danger_names = [c[0] for c in danger_cats]
    assert "이물질 상품" in danger_names, "FAIL: Expected '이물질 상품' to be detected!"
    assert "안전사고" in danger_names, "FAIL: Expected '안전사고' to be detected!"
    assert "식품위생" in danger_names, "FAIL: Expected '식품위생' to be detected!"
    assert danger_names[0] in ["이물질 상품", "안전사고", "식품위생"], "FAIL: Primary (highest score) must be one of the severe categories!"
    print("PASS: Multi-label Danger Axis co-occurrence verified successfully!")

    print("\n--- TEST 3: Multi-Label Co-occurrence (External Axis) ---")
    external_cats = classifier.classify_external(text_immediate)
    print("Detected External Categories:")
    for cat, score in external_cats:
        print(f"  * Category: '{cat:<12}' | Similarity: {score:.4f}")
        
    external_names = [c[0] for c in external_cats]
    assert "법적조치" in external_names, "FAIL: Expected '법적조치' to be detected!"
    assert "언론제보" in external_names, "FAIL: Expected '언론제보' to be detected!"
    print("PASS: Multi-label External Axis co-occurrence verified successfully!")

    print("\n--- TEST 4: Baseline Backward Compatibility check ---")
    # Ensuring standard single-string mapping continues to function on the first (highest score) element:
    primary_danger = danger_cats[0][0]
    primary_external = external_cats[0][0]
    print(f"Primary Representative Danger: '{primary_danger}'")
    print(f"Primary Representative External: '{primary_external}'")
    
    assert primary_danger in ["이물질 상품", "안전사고", "식품위생"], "FAIL: Primary danger column mapping mismatch!"
    assert primary_external in ["법적조치", "언론제보"], "FAIL: Primary external column mapping mismatch!"
    print("PASS: Backward compatibility verified successfully!")
    
    print("\n==================================================")
    print("      ALL 3D ENGINE TDD INTEGRATION TESTS PASSED! ")
    print("==================================================")

if __name__ == "__main__":
    run_3d_matrix_test()
