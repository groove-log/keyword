import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import extractor, classifier

def debug_phrase():
    classifier._ensure_cached()
    phrase = "잘린 쥐머리"
    phrase_emb = extractor._get_embedding(phrase)
    print(f"=== Category Scores for '{phrase}' ===")
    for category, desc_emb in classifier.cached_embeddings.items():
        score = extractor._cosine_similarity(phrase_emb, desc_emb)
        print(f" -> '{category}': {score:.4f}")

if __name__ == "__main__":
    debug_phrase()
