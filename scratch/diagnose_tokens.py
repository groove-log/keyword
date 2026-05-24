import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import classifier, extractor

text = (
    "당장 해결책을 내놓으세요. 어제 매장 앞 빙판길에서 미끄러져 넘어지는 낙상 사고를 당했습니다! "
    "머리를 세게 부딪혀 뼈가 부러졌고, 구토 증상 때문에 119 구급차로 병원 응급실에 즉시 이송되었습니다. "
    "또한 구매했던 도시락에서도 잘린 쥐머리가 발견되어 위생 상태도 엉망입니다. "
    "언론사에 제보하고 즉각적인 법적 소송도 함께 개시할 테니 각오하십시오."
)

classifier._ensure_cached()

tokens = extractor.kiwi.tokenize(text)
words = {t.form for t in tokens}
print("Words extracted by Kiwi:")
print(sorted(list(words)))

print("\nLexicon check:")
for cat, lex in classifier.lexicons.items():
    matches = words.intersection(set(lex))
    print(f"Category: {cat} | Lexicon match: {matches}")

emb_scores = {}
doc_emb = extractor._get_embedding(text)
for category, desc_emb in classifier.cached_danger_embeddings.items():
    score = extractor._cosine_similarity(doc_emb, desc_emb)
    emb_scores[category] = score
    print(f"Similarity with '{category}': {score:.4f}")
