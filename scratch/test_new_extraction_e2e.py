import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier
from scratch.test_phrase_extractor import DummyExtractor

def run_simulation():
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
    
    dummy = DummyExtractor()
    extractor._extract_candidates = dummy._extract_candidates
    
    classifier.protected_words = [
        "도시락", "음식", "매장", "점포", "강남점", "상계점", "어제", "해당", "식사", "순간", "보행", "불편", "자전거", "학생", "골목길", "상자", "박스", "쌓임", "구매",
        "발견", "오늘", "내일", "영업", "시간", "위치", "문의", "질문", "안내", "부탁", "요청", "확인", "치우려다가", "치우다", "앞에", "가운데", "때문에", "이것", "저것"
    ]
    
    classifier.lexicons = {
        "안전사고": ["낙상", "미끄러짐", "빙판", "눈길", "붕괴", "깔림", "끼임", "화상", "화재", "누수", "다침", "넘어짐", "부딪힘", "사고", "위험", "병원", "응급실", "구급차", "이송", "구토"],
        "법적 이슈": ["구청", "시청", "경찰", "고소", "고발", "소송", "신고", "과태료", "벌금", "처벌", "피해 보상", "내용증명", "제보", "언론사"],
        "성폭력": ["성추행", "성희롱", "유인", "그루밍", "추행", "접촉", "희롱"],
        "폭력 및 폭행": ["폭행", "구타", "협박", "살해", "때리다", "죽이다", "멱살", "흉기", "난동"],
        "이물질 상품": ["벌레", "초파리", "바퀴벌레", "식중독", "장염", "배탈", "곰팡이", "유해물", "혼입", "쥐", "쥐머리", "이물질", "머리카락", "손톱", "쇳조각", "유리"]
    }
    
    def is_protected(phrase: str) -> bool:
        if not phrase.strip():
            return False
        tokens = classifier.extractor.kiwi.tokenize(phrase)
        valid_tokens = [t.form for t in tokens if t.tag.startswith('N') or t.tag.startswith('V') or t.tag.startswith('M')]
        if not valid_tokens:
            return True
        return all(form in classifier.protected_words for form in valid_tokens)
    
    classifier.is_protected = is_protected
    
    # Threshold-First Selection logic in classify_phrase
    def new_classify_phrase(
        phrase: str,
        custom_thresholds: dict[str, float] = None,
        doc_risk_level: str = None,
        custom_linked_threshold: float = None,
        custom_min_safeguard: float = None
    ) -> tuple[str, float]:
        if not phrase.strip():
            return "정상", 0.0

        if classifier.is_protected(phrase):
            return "정상", 0.0

        try:
            classifier._ensure_cached()
            phrase_emb = classifier.extractor._get_embedding(phrase)
            
            active_thresholds = {**classifier.thresholds, **(custom_thresholds or {})}
            linked_thresh = custom_linked_threshold if custom_linked_threshold is not None else classifier.linked_threshold
            safeguard_thresh = custom_min_safeguard if custom_min_safeguard is not None else classifier.min_safeguard_score

            scores = {}
            for category, desc_emb in classifier.cached_embeddings.items():
                score = classifier.extractor._cosine_similarity(phrase_emb, desc_emb)
                scores[category] = score

            if not scores:
                return "정상", 0.0

            # 각 카테고리별 유효 임계값 계산 및 통과 여부 검사
            passed = {}
            for category, score in scores.items():
                has_lexicon_match = any(w in phrase for w in classifier.lexicons.get(category, []))
                
                # 위해 단어 직접 매칭 시 임계값을 0.28로 대폭 완화
                if has_lexicon_match:
                    thresh = 0.28
                elif doc_risk_level and doc_risk_level != "정상 문의" and category == doc_risk_level:
                    thresh = min(linked_thresh, safeguard_thresh)
                else:
                    thresh = active_thresholds.get(category, classifier.threshold)
                
                if score >= thresh:
                    passed[category] = score

            if passed:
                # 통과한 카테고리 중 점수가 가장 높은 것을 선택
                best_cat = max(passed, key=passed.get)
                return best_cat, passed[best_cat]

            # 통과한 카테고리가 없으면 전체 카테고리 중 최고 점수와 함께 정상으로 반환
            best_cat = max(scores, key=scores.get)
            return "정상", scores[best_cat]

        except Exception as e:
            print(f"Phrase classification failed: {e}")
            return "정상", 0.0

    classifier.classify_phrase = new_classify_phrase
    
    # Mocking extract_keywords to apply protection and elevation boosts
    def new_extract_keywords(
        text: str,
        keyphrase_ngram_range: tuple[int, int] = (1, 2),
        top_n: int = 3,
        doc_risk_level: str = None,
        classifier = None,
        weight_coeff: float = 0.35
    ) -> list[tuple[str, float]]:
        candidates = extractor._extract_candidates(text, keyphrase_ngram_range)
        if not candidates:
            return []

        doc_emb = extractor._get_embedding(text)

        guide_emb = None
        if doc_risk_level and doc_risk_level != "정상 문의" and classifier:
            classifier._ensure_cached()
            if doc_risk_level in classifier.cached_embeddings:
                guide_emb = classifier.cached_embeddings[doc_risk_level]

        scored: list[tuple[str, float]] = []
        for candidate in candidates:
            cand_emb = extractor._get_embedding(candidate)
            base_score = extractor._cosine_similarity(doc_emb, cand_emb)
            
            is_protected_cand = classifier and hasattr(classifier, 'is_protected') and classifier.is_protected(candidate)
            
            if guide_emb and not is_protected_cand:
                guide_score = extractor._cosine_similarity(guide_emb, cand_emb)
                
                is_danger_cand = False
                if classifier and hasattr(classifier, 'lexicons'):
                    for category, words in classifier.lexicons.items():
                        if any(w in candidate for w in words):
                            is_danger_cand = True
                            break
                
                if is_danger_cand:
                    final_score = base_score + (weight_coeff * guide_score * 1.5)
                else:
                    final_score = base_score + (weight_coeff * guide_score)
            else:
                final_score = base_score
                
            scored.append((candidate, final_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    extractor.extract_keywords = new_extract_keywords

    results = extractor.extract_keywords(
        text=text,
        keyphrase_ngram_range=(1, 3),
        top_n=8,
        doc_risk_level="이물질 상품",
        classifier=classifier,
        weight_coeff=0.35
    )
    
    print("\n=== E2E Keywords Classification Results ===")
    for word, score in results:
        risk_cat, risk_score = classifier.classify_phrase(
            word,
            doc_risk_level="이물질 상품"
        )
        print(f"Keyword: '{word:<18}' | ExtrScore: {score:.4f} | Category: '{risk_cat:<12}' | SimScore: {risk_score:.4f}")

if __name__ == "__main__":
    run_simulation()
