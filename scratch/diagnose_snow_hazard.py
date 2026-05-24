import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import classifier

text = (
    "상계점 점포 앞 눈이 많이 쌓여있는데, 전혀 처리를 안해주고 계시네요. "
    "저대로 두면 길이 굉장히 미끄러워 질것 같습니다. "
    "통행하시는 분들 낙상사고도 우려가 됩니다."
)

def diagnose():
    print("==================================================")
    print("Diagnosing Snow Hazard Classification (BGE-M3)")
    print("==================================================")
    print(f"Input Text: {text}\n")
    
    # 캐시 확인
    classifier._ensure_cached()
    
    doc_emb = classifier.extractor._get_embedding(text)
    
    scores = {}
    for category, desc_emb in classifier.cached_embeddings.items():
        score = classifier.extractor._cosine_similarity(doc_emb, desc_emb)
        scores[category] = score
        thresh = classifier.thresholds.get(category, classifier.threshold)
        print(f" -> {category}: Score = {score:.4f} (Threshold = {thresh})")
        
    print("\n--------------------------------------------------")
    best_category = max(scores, key=scores.get)
    print(f"Best Category: '{best_category}' (Score: {scores[best_category]:.4f})")
    
    # 실제 판별 결과
    res_cat, res_score = classifier.classify(text)
    print(f"Classifier Final Output: '{res_cat}' (Score: {res_score:.4f})")
    print("==================================================")

if __name__ == "__main__":
    diagnose()
