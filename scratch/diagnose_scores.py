import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def run_diagnose_scores():
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다.\n\n"
        "관련해서 담당자에게 정확한 입장을 원합니다."
    )
    
    classifier._ensure_cached()
    
    # 1. Document Embeddings & similarities
    doc_emb = extractor._get_embedding(text)
    print("=== Document Similarity Scores ===")
    for category, desc_emb in classifier.cached_embeddings.items():
        score = extractor._cosine_similarity(doc_emb, desc_emb)
        print(f" -> Category '{category}': {score:.4f}")
        
    # 2. Key phrases
    phrases = ["도시락", "어제 도시락", "음식", "쥐 머리", "쥐머리", "병원 응급실", "병원", "응급실", "구토", "소송준비"]
    print("\n=== Phrase Similarity Scores ===")
    for phrase in phrases:
        phrase_emb = extractor._get_embedding(phrase)
        print(f"\nPhrase: '{phrase}'")
        for category, desc_emb in classifier.cached_embeddings.items():
            score = extractor._cosine_similarity(phrase_emb, desc_emb)
            print(f"  -> Category '{category}': {score:.4f}")

if __name__ == "__main__":
    run_diagnose_scores()
