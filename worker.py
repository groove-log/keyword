import os
import re
import requests
import numpy as np
import psycopg
from celery import Celery
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

LLAMA_API_URL = os.getenv("LLAMA_API_URL", "http://localhost:8081")
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY", "")

# 사용할 엔드포인트 선택 (환경변수로 전환 가능)
# "v1"     → POST /v1/embeddings  (OpenAI 호환)
#              응답: {"data":[{"embedding":[...]}]}
# "legacy" → POST /embedding
#              응답: [{"index":0,"embedding":[[...]]}]  ← 이중 배열
EMBED_MODE = os.getenv("LLAMA_EMBED_MODE", "v1")

DB_NAME     = os.getenv("DB_NAME", "postgres")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")

# 1. Celery 애플리케이션 및 Redis 브로커 설정
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app = Celery('counseling_tasks', broker=REDIS_URL)


class KeywordExtractor:
    """
    KeyBERT를 대체하는 순수 HTTP 기반 키워드 추출기.
    torch / sentence-transformers 의존성 없이 llama.cpp 서버만 사용합니다.

    동작 원리:
      1. 텍스트에서 n-gram 후보 추출
      2. 문서 전체 임베딩 획득 (llama.cpp HTTP)
      3. 후보별 임베딩 획득 (llama.cpp HTTP)
      4. 코사인 유사도로 상위 n개 선정

    KeyBERT 호환 인터페이스:
      extract_keywords(text, keyphrase_ngram_range, top_n)
      → [(키워드, 점수), ...] 반환
    """

    def __init__(self, api_url: str, api_key: str, mode: str = "v1"):
        self.mode = mode
        self.endpoint = (
            f"{api_url}/v1/embeddings" if mode == "v1" else f"{api_url}/embedding"
        )
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def _get_embedding(self, text: str) -> list[float]:
        """단일 텍스트의 임베딩 벡터를 llama.cpp 서버에서 획득"""
        payload = (
            {"input": text, "model": "bge-m3"}
            if self.mode == "v1"
            else {"content": text}
        )
        resp = requests.post(
            self.endpoint,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if self.mode == "v1":
            # {"data": [{"embedding": [0.1, 0.2, ...]}]}
            return data["data"][0]["embedding"]
        # [{"index": 0, "embedding": [[0.1, 0.2, ...]]}]  ← 이중 배열
        raw = data[0]["embedding"]
        return raw[0] if isinstance(raw[0], list) else raw

    @staticmethod
    def _extract_candidates(
        text: str, ngram_range: tuple[int, int]
    ) -> list[str]:
        """
        텍스트에서 n-gram 후보 목록 추출.
        특수문자 제거 → 토크나이즈 → n-gram 생성 → 중복 제거
        """
        clean = re.sub(r'[^\w\s]', ' ', text)
        words = [w for w in clean.split() if len(w) > 1]

        candidates: set[str] = set()
        min_n, max_n = ngram_range
        for n in range(min_n, max_n + 1):
            for i in range(len(words) - n + 1):
                candidates.add(' '.join(words[i:i + n]))
        return list(candidates)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """두 벡터의 코사인 유사도 반환 (범위: -1 ~ 1, 높을수록 유사)"""
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / denom) if denom > 0 else 0.0

    def extract_keywords(
        self,
        text: str,
        keyphrase_ngram_range: tuple[int, int] = (1, 2),
        top_n: int = 3,
    ) -> list[tuple[str, float]]:
        """
        KeyBERT의 extract_keywords()와 동일한 인터페이스.

        Args:
            text: 분석할 텍스트
            keyphrase_ngram_range: (최소 단어 수, 최대 단어 수)
            top_n: 반환할 키워드 개수

        Returns:
            [(키워드, 유사도 점수), ...] 유사도 내림차순 정렬
        """
        candidates = self._extract_candidates(text, keyphrase_ngram_range)
        if not candidates:
            return []

        # 문서 전체 임베딩
        doc_emb = self._get_embedding(text)

        # 후보별 임베딩 획득 + 유사도 계산
        scored: list[tuple[str, float]] = []
        for candidate in candidates:
            cand_emb = self._get_embedding(candidate)
            score = self._cosine_similarity(doc_emb, cand_emb)
            scored.append((candidate, score))

        # 유사도 내림차순 정렬 후 상위 n개 반환
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]


# 2. 워커 시작 시 단 한 번만 초기화 (HTTP 클라이언트만 생성, 모델 로드 없음)
print(f"Connecting to llama.cpp BGE-m3 server at {LLAMA_API_URL} (mode={EMBED_MODE}) ...")
extractor = KeywordExtractor(api_url=LLAMA_API_URL, api_key=LLAMA_API_KEY, mode=EMBED_MODE)
print("KeywordExtractor ready! (torch-free / llama.cpp HTTP only)")


# DB 연결 헬퍼 함수
def get_db_connection():
    return psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


@app.task
def process_keyword_extraction(counseling_id: int, text: str) -> str:
    """
    Redis 큐에서 메시지를 받아 실행되는 비동기 작업.
    llama.cpp에 올라간 BGE-m3 모델로 키워드를 추출합니다.
    """
    try:
        # 3. 키워드 추출 (llama.cpp 임베딩 호출)
        keywords_with_scores = extractor.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 2),  # 1단어 ~ 2단어 조합 도출
            top_n=3,
        )

        # 키워드만 정제하여 콤마 스트링으로 변환
        extracted_words = [kw[0] for kw in keywords_with_scores]
        keyword_str = ", ".join(extracted_words)

        # 4. PostgreSQL DB 업데이트
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE counseling_data SET keywords = %s, status = 'COMPLETED' WHERE id = %s",
            (keyword_str, counseling_id),
        )
        conn.commit()
        cur.close()
        conn.close()

        # 5. 긴급 안건(룰베이스) 탐지
        danger_words = ['소비자원', '식중독', '소송', '언론']
        if any(danger in text for danger in danger_words):
            print(f"[긴급 알림 발송 대상] ID: {counseling_id} - 긴급 키워드 감지됨!")
            # 향후 여기에 Mpush API 호출 로직 추가

        return f"Success: ID {counseling_id} -> {keyword_str}"

    except Exception as e:
        return f"Fail: ID {counseling_id} -> Error: {str(e)}"
