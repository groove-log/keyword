import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def run_deduplication_test():
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다.\n\n"
        "관련해서 담당자에게 정확한 입장을 원합니다."
    )
    
    classifier._ensure_cached()
    
    # 1. Extract raw candidates using new morphological extractor
    candidates = extractor._extract_candidates(text, (1, 3))
    doc_emb = extractor._get_embedding(text)
    
    # Cache guides
    guide_embs = [classifier.cached_danger_embeddings["이물질 상품"], classifier.cached_external_embeddings["법적조치"]]
    weight_coeff = 0.35
    
    scored = []
    for candidate in candidates:
        cand_emb = extractor._get_embedding(candidate)
        base_score = extractor._cosine_similarity(doc_emb, cand_emb)
        
        is_protected_cand = classifier.is_protected(candidate)
        if guide_embs and not is_protected_cand:
            guide_score = max(extractor._cosine_similarity(g_emb, cand_emb) for g_emb in guide_embs)
            is_danger_cand = False
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
    
    print("=== Raw Ranked Keywords (Top 12) ===")
    for rank, (word, score) in enumerate(scored[:12], 1):
        print(f" {rank}. '{word:<18}' | Score: {score:.4f}")
        
    # 2. Apply Spacing Normalization & Substring Suppression Deduplication
    filtered_scored = []
    seen_spaceless = set()
    
    for candidate, final_score in scored:
        spaceless_cand = candidate.replace(" ", "")
        if spaceless_cand in seen_spaceless:
            continue
            
        is_redundant = False
        for existing in filtered_scored:
            existing_spaceless = existing[0].replace(" ", "")
            if spaceless_cand in existing_spaceless or existing_spaceless in spaceless_cand:
                is_redundant = True
                break
                
        if is_redundant:
            continue
            
        filtered_scored.append((candidate, final_score))
        seen_spaceless.add(spaceless_cand)
        
    print("\n=== Deduplicated Ranked Keywords (Top 8) ===")
    for rank, (word, score) in enumerate(filtered_scored[:8], 1):
        risk_cat, risk_score = classifier.classify_phrase(word, doc_risk_level="이물질 상품", doc_external_level="법적조치")
        print(f" {rank}. '{word:<18}' | Score: {score:.4f} | Mapped: {risk_cat:<12} (Sim: {risk_score:.4f})")

if __name__ == "__main__":
    run_deduplication_test()
