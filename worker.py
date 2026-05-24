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
        # Kiwi 형태소 분석기 지연 임포트 및 초기화
        from kiwipiepy import Kiwi
        self.kiwi = Kiwi()

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

    def _extract_candidates(
        self, text: str, ngram_range: tuple[int, int]
    ) -> list[str]:
        """
        Kiwi 형태소 분석기를 활용해 텍스트에서 명사형 단어 및 연속 명사구(n-gram) 후보군 추출.
        조사가 배제된 핵심 명사 및 합성명사 위주로 키워드 후보를 생성합니다.
        """
        if not text.strip():
            return []

        tokens = self.kiwi.tokenize(text)
        candidates: set[str] = set()
        min_n, max_n = ngram_range

        # 1. 단일 명사 후보군 추가 (2글자 이상 핵심 명사)
        for t in tokens:
            if t.tag in ('NNG', 'NNP'):
                if len(t.form) >= 2:
                    candidates.add(t.form)

        # 2. 인접한 명사들의 연속 구간을 결합하여 명사구 후보 생성 (슬라이딩 윈도우 + 띄어쓰기 유무 유연 대응)
        i = 0
        while i < len(tokens):
            if tokens[i].tag in ('NNG', 'NNP', 'XSN'):
                j = i + 1
                chunk = [tokens[i].form]
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        chunk[-1] = chunk[-1] + tokens[j].form
                    else:
                        chunk.append(tokens[j].form)
                    current_len = len(chunk)
                    if min_n <= current_len <= max_n:
                        candidates.add(' '.join(chunk))
                        candidates.add(''.join(chunk))
                    j += 1
                i += 1
            else:
                i += 1

        # 3. 실질 동사(VV) 및 형용사(VA) 어간을 명사화(ㅁ/음 결합)하여 후보군 추가
        for t in tokens:
            if t.tag in ('VV', 'VA'):
                stem = t.form
                if len(stem) >= 2:  # 최소 2글자 이상 어간 대상
                    last_char = stem[-1]
                    code = ord(last_char) - 0xAC00
                    if 0 <= code <= 11172:
                        jongseong = code % 28
                        if jongseong == 0:
                            # 받침이 없는 경우 'ㅁ' 종성 결합 (종성 인덱스 16 추가)
                            nominalized_char = chr(ord(last_char) + 16)
                            nominalized = stem[:-1] + nominalized_char
                        else:
                            # 받침이 있는 경우 단순히 '음' 문자열 결합 (예: 먹 -> 먹음)
                            nominalized = stem + "음"
                        candidates.add(nominalized)

        # 4. 관형어 + 명사구 결합 구문 (예: "잘린 쥐머리")
        i = 0
        while i < len(tokens) - 2:
            if tokens[i].tag in ('VV', 'VA') and tokens[i+1].tag == 'ETM':
                modifier = tokens[i].form
                etm = tokens[i+1].form
                
                if etm == 'ᆫ':
                    if modifier.endswith('리'):
                        modifier_str = modifier[:-1] + '린'
                    elif modifier.endswith('하'):
                        modifier_str = modifier[:-1] + '한'
                    elif modifier.endswith('되'):
                        modifier_str = modifier[:-1] + '된'
                    else:
                        modifier_str = modifier + 'ㄴ'
                elif etm == '는':
                    modifier_str = modifier + '는'
                elif etm == '은':
                    modifier_str = modifier + '은'
                elif etm == '을':
                    modifier_str = modifier + '을'
                else:
                    modifier_str = modifier + etm
                
                j = i + 2
                chunk = []
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        if chunk:
                            chunk[-1] = chunk[-1] + tokens[j].form
                    else:
                        chunk.append(tokens[j].form)
                    
                    if chunk:
                        phrase_spaced = modifier_str + ' ' + ' '.join(chunk)
                        phrase_unspaced = modifier_str + ' ' + ''.join(chunk)
                        candidates.add(phrase_spaced)
                        candidates.add(phrase_unspaced)
                    j += 1
                i = j
            else:
                i += 1

        # 5. 명사구 + 동사구 동작 결합 구문 (예: "쥐머리 발견", "응급실 이송")
        i = 0
        while i < len(tokens):
            if tokens[i].tag in ('NNG', 'NNP'):
                noun_chunk = [tokens[i].form]
                j = i + 1
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        noun_chunk[-1] = noun_chunk[-1] + tokens[j].form
                    else:
                        noun_chunk.append(tokens[j].form)
                    j += 1
                
                k = j
                if k < len(tokens) and tokens[k].tag in ('JKS', 'JKO', 'JKB', 'JX'):
                    k += 1
                
                if k < len(tokens) - 1:
                    if tokens[k].tag in ('NNG', 'NNP') and tokens[k+1].tag in ('XSV', 'XSA', 'VV'):
                        action_noun = tokens[k].form
                        
                        spaced_nouns = ' '.join(noun_chunk)
                        unspaced_nouns = ''.join(noun_chunk)
                        
                        candidates.add(spaced_nouns + ' ' + action_noun)
                        candidates.add(unspaced_nouns + ' ' + action_noun)
                        candidates.add(unspaced_nouns + action_noun)
                        
                        suffix = tokens[k+1].form
                        if suffix == '되':
                            candidates.add(spaced_nouns + ' ' + action_noun + '됨')
                            candidates.add(unspaced_nouns + ' ' + action_noun + '됨')
                            candidates.add(unspaced_nouns + action_noun + '됨')
                        elif suffix == '하':
                            candidates.add(spaced_nouns + ' ' + action_noun + '함')
                            candidates.add(unspaced_nouns + ' ' + action_noun + '함')
                            candidates.add(unspaced_nouns + action_noun + '함')
                i = max(i + 1, j)
            else:
                i += 1

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
        doc_risk_level: str = None,
        doc_external_level: str = None,
        classifier = None,
        weight_coeff: float = 0.35
    ) -> list[tuple[str, float]]:
        """
        KeyBERT의 extract_keywords()와 동일한 인터페이스.
        카테고리 유도형 가중치(Category-Guided Weighting) 연산을 지원하며, 2D 듀얼 가이드 결합을 지원합니다.
        """
        candidates = self._extract_candidates(text, keyphrase_ngram_range)
        if not candidates:
            return []

        # 문서 전체 임베딩
        doc_emb = self._get_embedding(text)

        # 2D 듀얼 가이드 임베딩 수집
        guide_embs = []
        if classifier:
            classifier._ensure_cached()
            if doc_risk_level and doc_risk_level != "정상 문의" and doc_risk_level in classifier.cached_danger_embeddings:
                guide_embs.append(classifier.cached_danger_embeddings[doc_risk_level])
            if doc_external_level and doc_external_level != "정상 문의" and doc_external_level in classifier.cached_external_embeddings:
                guide_embs.append(classifier.cached_external_embeddings[doc_external_level])

        # 후보별 임베딩 획득 + 유사도 계산
        scored: list[tuple[str, float]] = []
        for candidate in candidates:
            cand_emb = self._get_embedding(candidate)
            # 1. 문서 전체와의 유사도 (기본 KeyBERT 점수)
            base_score = self._cosine_similarity(doc_emb, cand_emb)
            
            # 2. 보호 단어 여부 확인 (보호 단어인 경우 가이드 버프에서 완전 제외)
            is_protected_cand = classifier and hasattr(classifier, 'is_protected') and classifier.is_protected(candidate)
            
            if guide_embs and not is_protected_cand:
                # 활성화된 모든 가이드와의 최대 유사도를 적용
                guide_score = max(self._cosine_similarity(g_emb, cand_emb) for g_emb in guide_embs)
                
                # 위해 사전 매칭 시 1.5배 가중치 가속화 진행 (위험 구문 상위 유도)
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

        # 유사도 내림차순 정렬
        scored.sort(key=lambda x: x[1], reverse=True)

        # 중복 단어 및 구문 제거 (띄어쓰기 정규화 및 부분 문자열 중복 제거)
        filtered_scored: list[tuple[str, float]] = []
        seen_spaceless: set[str] = set()
        
        for candidate, final_score in scored:
            spaceless_cand = candidate.replace(" ", "")
            
            # 1. 띄어쓰기 정규화 중복 체크
            if spaceless_cand in seen_spaceless:
                continue
                
            # 2. 부분 문자열 포함 체크 (더 큰/구체적인 맥락 단어가 이미 들어간 경우 제외)
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

        return filtered_scored[:top_n]


# 2. 워커 시작 시 단 한 번만 초기화
print(f"Connecting to llama.cpp BGE-m3 server at {LLAMA_API_URL} (mode={EMBED_MODE}) ...")
extractor = KeywordExtractor(api_url=LLAMA_API_URL, api_key=LLAMA_API_KEY, mode=EMBED_MODE)
print("KeywordExtractor ready! (torch-free / llama.cpp HTTP only)")

# 3. 2D 위험 매트릭스 세부지침 정의
DEFAULT_DANGER_GUIDELINES = {
    "폭력 및 폭행": "타인이나 직원에 대하여 신체적인 상해를 가하거나 직접 타격하고, 물리적으로 위해를 가하겠다고 위협하고 기물을 파손하며 난동 및 폭력 행패를 부리는 상황입니다. 주먹으로 때리겠다, 죽이겠다, 멱살을 잡겠다, 뺨을 때리겠다, 칼로 찌르겠다와 같은 직접적인 언어적 살해 협박 및 위해 경고, 그리고 실제로 물건을 던지거나 몸을 밀치고 흉기를 휘두르는 물리적 공격, 위협적 폭언 및 난폭한 욕설을 모두 포함합니다.",
    "성폭력": "매장의 점장, 관리자, 상사 또는 근무자가 타인을 대상으로 성적 수치심, 불쾌감을 유발하는 성희롱, 성추행 행위입니다. 음담패설 외에도 점장이나 상사가 우월적 지위를 이용하여 피해자가 거부하고 불안해함에도 불구하고 사적인 대화를 지속하거나, 조용한 곳, 단둘이 있는 밀폐된 방이나 사적 공간으로 자꾸 유인하고 계속 불러들이며 관계를 강요하는 비정상적인 접근, 가스라이팅, 그루밍(심리적 길들이기) 행위를 모두 포함합니다.",
    "이물질 상품": "고객이 구매한 상품(특히 도시락, 삼각김밥, 빵, 디저트, 음료 등 먹는 식품) 내부에서 제조, 포장, 또는 유통 과정 중에 혼입된 비정상적인 유해 이물질이 발견되어 항의하는 위생 클레임입니다. 식품 내부나 표면에서 발견된 벌레(초파리, 바퀴벌레, 애벌레 등), 머리카락, 먼지, 곰팡이, 손톱뿐만 아니라 쇳조각, 유리 파편, 플라스틱, 비닐, 스테이플러 심 등 날카롭고 위험한 물질을 지칭합니다. 또한 제품이 변질되어 쉰내나 상한 냄새가 나거나 부패한 상태, 그리고 이를 섭취하거나 삼켜서 발생한 배탈, 장염, 식중독, 구토, 치아 부러짐(파손) 등의 신체적 위해를 모두 포함합니다.",
    "안전사고": "매장 내부, 외부 부대시설, 주차장, 계단, 출입구 또는 인근 도로에서 고객이나 근무자의 생명과 신체 안전을 위협하는 실제 사고 상황이나 잠재적인 사고 위험 요인을 의미합니다. 미끄러짐, 넘어짐, 추락, 충돌, 엘리베이터/자동문 끼임, 화상, 화재, 누수 등 실제 다쳐서 신체적 피해(골절, 출혈, 부상, 찰과상)를 입고 119 구급차를 부르거나 응급실에 간 상황뿐만 아니라, 시설 결함이나 불법 적치물, 위험 방치물로 인해 넘어질 뻔한 상황, 차도나 도로 침범으로 인한 교통사고 발생 위험성 및 충돌 우려, 안전 위해 및 사고 경고 상황을 모두 포함합니다."
}

DEFAULT_EXTERNAL_GUIDELINES = {
    "법적조치": "자사나 매장, 직원을 대상으로 직접적인 법적 처벌이나 소송을 제기하겠다고 언급하거나 고소, 고발 진행 및 예정, 변호사 자문 및 소송 준비 등의 의지를 표현하는 상황입니다. 경찰 고소, 민사 소송 제기, 법적 처벌 요구, 내용증명 발송, 소송 준비를 하겠다, 고소하겠다는 발언을 포함합니다.",
    "언론제보": "외부 언론사(방송국, 뉴스 등) 및 미디어(유튜브, SNS, 커뮤니티 등)에 해당 사실을 제보하여 사회적 이슈로 공론화하겠다고 경고하거나 언급하는 상황입니다. 언론에 제보하겠다, 방송에 알리겠다, 인터넷이나 유튜브에 올리겠다는 발언을 포함합니다.",
    "이슈제기": "소비자원, 구청, 시청, 식약처, 소방서 등 관할 관공서나 공공기관에 공식 민원 제기, 불법 적치물 신고, 위생 단속 요구 등 법제상 문제를 제기하고 신고 및 고발하겠다고 언급하는 상황입니다. 소비자보호원 민원, 구청에 정식 신고하겠다, 과태료를 물게 하겠다, 식약처에 신고하겠다는 발언을 포함합니다."
}

DEFAULT_DANGER_THRESHOLDS = {
    "폭력 및 폭행": 0.58,
    "성폭력": 0.53,
    "이물질 상품": 0.60,
    "안전사고": 0.55,
    "법적조치": 0.52,
    "언론제보": 0.52,
    "이슈제기": 0.52
}

import json
danger_env = os.getenv("DANGER_GUIDELINES")
if danger_env:
    try:
        DANGER_GUIDELINES = json.loads(danger_env)
    except Exception as e:
        print(f"Failed to parse DANGER_GUIDELINES environment variable: {e}")
        DANGER_GUIDELINES = DEFAULT_DANGER_GUIDELINES
else:
    DANGER_GUIDELINES = DEFAULT_DANGER_GUIDELINES

danger_thresholds_env = os.getenv("DANGER_THRESHOLDS")
if danger_thresholds_env:
    try:
        DANGER_THRESHOLDS = json.loads(danger_thresholds_env)
    except Exception as e:
        print(f"Failed to parse DANGER_THRESHOLDS environment variable: {e}")
        DANGER_THRESHOLDS = DEFAULT_DANGER_THRESHOLDS
else:
    DANGER_THRESHOLDS = DEFAULT_DANGER_THRESHOLDS

DANGER_THRESHOLD = float(os.getenv("DANGER_THRESHOLD", "0.60"))
DANGER_KEYWORD_LINKED_THRESHOLD = float(os.getenv("DANGER_KEYWORD_LINKED_THRESHOLD", "0.45"))
DANGER_KEYWORD_MIN_SAFEGUARD_SCORE = float(os.getenv("DANGER_KEYWORD_MIN_SAFEGUARD_SCORE", "0.53"))

class SemanticClassifier:
    """
    BGE-M3 임베딩 모델을 이용한 2D 위험 매트릭스 기반 시나리오 분류기.
    """
    def __init__(self, extractor, danger_guidelines: dict[str, str], external_guidelines: dict[str, str], threshold: float = 0.60, thresholds: dict[str, float] = None, linked_threshold: float = 0.45, min_safeguard_score: float = 0.53):
        self.extractor = extractor
        self.danger_guidelines = danger_guidelines
        self.external_guidelines = external_guidelines
        self.threshold = threshold
        self.thresholds = thresholds or {}
        self.linked_threshold = linked_threshold
        self.min_safeguard_score = min_safeguard_score
        
        self.cached_danger_embeddings = {}
        self.cached_external_embeddings = {}
        
        self.protected_words = [
            "도시락", "음식", "매장", "점포", "강남점", "상계점", "어제", "해당", "식사", "순간", "보행", "불편", "자전거", "학생", "골목길", "상자", "박스", "쌓임", "구매",
            "발견", "오늘", "내일", "영업", "시간", "위치", "문의", "질문", "안내", "부탁", "요청", "확인", "치우려다가", "치우다", "앞에", "가운데", "때문에", "이것", "저것"
        ]
        
        self.lexicons = {
            # 위험 이슈
            "안전사고": ["낙상", "미끄러짐", "빙판", "눈길", "붕괴", "깔림", "끼임", "화상", "화재", "누수", "다침", "넘어짐", "부딪힘", "사고", "위험", "병원", "응급실", "구급차", "이송", "구토"],
            "성폭력": ["성추행", "성희롱", "유인", "그루밍", "추행", "접촉", "희롱"],
            "폭력 및 폭행": ["폭행", "구타", "협박", "살해", "때리다", "죽이다", "멱살", "흉기", "난동"],
            "이물질 상품": ["벌레", "초파리", "바퀴벌레", "식중독", "장염", "배탈", "곰팡이", "유해물", "혼입", "쥐", "쥐머리", "이물질", "머리카락", "손톱", "쇳조각", "유리"],
            # 외부 이슈
            "법적조치": ["고소", "고발", "소송", "신고", "과태료", "벌금", "처벌", "피해 보상", "내용증명", "소환", "고발장", "고소장"],
            "언론제보": ["제보", "언론사", "기자", "뉴스", "방송", "유튜브", "커뮤니티", "인터넷", "인스타", "보도"],
            "이슈제기": ["소비자원", "구청", "시청", "식약처", "소방서", "관공서", "공공기관", "민원"]
        }

    def _ensure_cached(self):
        """지침 임베딩이 캐싱되어 있는지 확인 (지연 로딩하여 컨테이너 기동 레이스 컨디션 방지)"""
        if not self.cached_danger_embeddings:
            print("Caching 2D Matrix guidelines embeddings (lazy initialization)...")
            for category, description in self.danger_guidelines.items():
                try:
                    self.cached_danger_embeddings[category] = self.extractor._get_embedding(description)
                    print(f" -> Cached danger guideline for '{category}' successfully.")
                except Exception as e:
                    print(f" -> ERROR caching danger guideline '{category}': {e}")
                    raise e
                    
            for category, description in self.external_guidelines.items():
                try:
                    self.cached_external_embeddings[category] = self.extractor._get_embedding(description)
                    print(f" -> Cached external guideline for '{category}' successfully.")
                except Exception as e:
                    print(f" -> ERROR caching external guideline '{category}': {e}")
                    raise e

    def classify_danger(self, text: str, custom_thresholds: dict[str, float] = None) -> tuple[str, float]:
        if not text.strip():
            return "정상 문의", 0.0
        
        try:
            self._ensure_cached()
            doc_emb = self.extractor._get_embedding(text)
            active_thresholds = {**self.thresholds, **(custom_thresholds or {})}
            
            # 형태소 토큰 분석을 통한 위해 렉시콘 매칭 진행
            tokens = self.extractor.kiwi.tokenize(text)
            words = {t.form for t in tokens}
            
            scores = {}
            for category, desc_emb in self.cached_danger_embeddings.items():
                score = self.extractor._cosine_similarity(doc_emb, desc_emb)
                scores[category] = score
                
            passed_category = None
            max_passed_score = -1.0
            
            for category, score in scores.items():
                # 위해 사전 단어가 검출된 경우 임계값을 0.48로 동적 완화
                has_lexicon_trigger = any(lex in words for lex in self.lexicons.get(category, []))
                
                if has_lexicon_trigger:
                    thresh = 0.48
                else:
                    thresh = active_thresholds.get(category, self.threshold)
                    
                if score >= thresh:
                    if score > max_passed_score:
                        max_passed_score = score
                        passed_category = category
            
            if passed_category:
                return passed_category, max_passed_score
            else:
                overall_best_score = max(scores.values()) if scores else 0.0
                return "정상 문의", overall_best_score
        except Exception as e:
            print(f"Danger classification failed: {e}")
            return "정상 문의", 0.0

    def classify_external(self, text: str, custom_thresholds: dict[str, float] = None) -> tuple[str, float]:
        if not text.strip():
            return "정상 문의", 0.0
        
        try:
            self._ensure_cached()
            doc_emb = self.extractor._get_embedding(text)
            active_thresholds = {**self.thresholds, **(custom_thresholds or {})}
            
            # 형태소 토큰 분석을 통한 위해 렉시콘 매칭 진행
            tokens = self.extractor.kiwi.tokenize(text)
            words = {t.form for t in tokens}
            
            scores = {}
            for category, desc_emb in self.cached_external_embeddings.items():
                score = self.extractor._cosine_similarity(doc_emb, desc_emb)
                scores[category] = score
                
            passed_category = None
            max_passed_score = -1.0
            
            for category, score in scores.items():
                # 위해 사전 단어가 검출된 경우 외부 이슈 임계값을 0.40로 동적 완화
                has_lexicon_trigger = any(lex in words for lex in self.lexicons.get(category, []))
                
                if has_lexicon_trigger:
                    thresh = 0.40
                else:
                    thresh = active_thresholds.get(category, self.threshold)
                    
                if score >= thresh:
                    if score > max_passed_score:
                        max_passed_score = score
                        passed_category = category
            
            if passed_category:
                return passed_category, max_passed_score
            else:
                overall_best_score = max(scores.values()) if scores else 0.0
                return "정상 문의", overall_best_score
        except Exception as e:
            print(f"External classification failed: {e}")
            return "정상 문의", 0.0

    def is_protected(self, phrase: str) -> bool:
        if not phrase.strip():
            return False
        tokens = self.extractor.kiwi.tokenize(phrase)
        valid_tokens = [t.form for t in tokens if t.tag.startswith('N') or t.tag.startswith('V') or t.tag.startswith('M')]
        if not valid_tokens:
            return True
        return all(form in self.protected_words for form in valid_tokens)

    def classify_phrase(
        self,
        phrase: str,
        custom_thresholds: dict[str, float] = None,
        doc_risk_level: str = None,
        doc_external_level: str = None,
        custom_linked_threshold: float = None,
        custom_min_safeguard: float = None
    ) -> tuple[str, float]:
        """
        단일 명사 혹은 단편적 명사구 키워드에 대해 카테고리를 판별합니다. (선 통과-후 최적 전략 적용)
        """
        if not phrase.strip():
            return "정상", 0.0

        if self.is_protected(phrase):
            return "정상", 0.0

        try:
            self._ensure_cached()
            phrase_emb = self.extractor._get_embedding(phrase)
            
            active_thresholds = {**self.thresholds, **(custom_thresholds or {})}
            linked_thresh = custom_linked_threshold if custom_linked_threshold is not None else self.linked_threshold
            safeguard_thresh = custom_min_safeguard if custom_min_safeguard is not None else self.min_safeguard_score

            # 위험 카테고리 + 외부 카테고리 통합 스캔
            scores = {}
            for category, desc_emb in {**self.cached_danger_embeddings, **self.cached_external_embeddings}.items():
                score = self.extractor._cosine_similarity(phrase_emb, desc_emb)
                scores[category] = score

            if not scores:
                return "정상", 0.0

            # 1단계: 각 카테고리별 유효 임계값 계산 및 통과 여부 검사 (Threshold-First)
            passed = {}
            for category, score in scores.items():
                has_lexicon_match = any(w in phrase for w in self.lexicons.get(category, []))
                
                # 위해 사전 직접 매칭 시 임계값을 0.28로 대폭 완화하여 구문 확정 보장
                if has_lexicon_match:
                    thresh = 0.28
                elif doc_risk_level and doc_risk_level != "정상 문의" and category == doc_risk_level:
                    thresh = min(linked_thresh, safeguard_thresh)
                elif doc_external_level and doc_external_level != "정상 문의" and category == doc_external_level:
                    thresh = min(linked_thresh, safeguard_thresh)
                else:
                    thresh = active_thresholds.get(category, self.threshold)
                
                if score >= thresh:
                    passed[category] = score

            # 2단계: 통과한 후보군 중에서 가장 점수가 높은 카테고리 최종 판정
            if passed:
                best_cat = max(passed, key=passed.get)
                return best_cat, passed[best_cat]

            # 통과한 후보가 없을 시 최고 점수의 카테고리값과 함께 정상으로 반환하여 신호 유실 방지
            best_cat = max(scores, key=scores.get)
            return "정상", scores[best_cat]

        except Exception as e:
            print(f"Phrase classification failed: {e}")
            return "정상", 0.0

classifier = SemanticClassifier(
    extractor, 
    DANGER_GUIDELINES, 
    DEFAULT_EXTERNAL_GUIDELINES,
    DANGER_THRESHOLD, 
    DANGER_THRESHOLDS, 
    DANGER_KEYWORD_LINKED_THRESHOLD,
    DANGER_KEYWORD_MIN_SAFEGUARD_SCORE
)


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
def process_keyword_extraction(
    counseling_id: int, 
    text: str,
    custom_thresholds: dict[str, float] = None,
    custom_linked_threshold: float = None,
    custom_min_safeguard: float = None
) -> str:
    """
    Redis 큐에서 메시지를 받아 실행되는 비동기 작업.
    """
    try:
        # 1. 2D 위험 매트릭스 판별 진행
        risk_level, sim_score = classifier.classify_danger(text, custom_thresholds)
        external_issue, ext_score = classifier.classify_external(text, custom_thresholds)

        # 2. 키워드 구문 추출 (듀얼 가이드 및 1.5배 위해 가중치 적용)
        weight_coeff = float(os.getenv("DANGER_KEYWORD_GUIDE_WEIGHT", "0.35"))
        keywords_with_scores = extractor.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 3),  # 1단어 ~ 3단어 수준의 구문 도출
            top_n=8,
            doc_risk_level=risk_level,
            doc_external_level=external_issue,
            classifier=classifier,
            weight_coeff=weight_coeff
        )

        # 각 추출 키워드별 세부 위협 카테고리 판별 진행 (2D 판정 결과 연계)
        structured_keywords = []
        for word, score in keywords_with_scores:
            risk_cat, risk_score = classifier.classify_phrase(
                word, 
                custom_thresholds, 
                doc_risk_level=risk_level,
                doc_external_level=external_issue,
                custom_linked_threshold=custom_linked_threshold,
                custom_min_safeguard=custom_min_safeguard
            )
            structured_keywords.append({
                "word": word,
                "score": round(score, 4),
                "risk_category": risk_cat,
                "risk_score": round(risk_score, 4)
            })

        # DB에 JSON 문자열로 저장
        keywords_json_str = json.dumps(structured_keywords, ensure_ascii=False)

        # 5. PostgreSQL DB 업데이트 (2D 판정 동시 저장)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE counseling_data SET keywords = %s, status = 'COMPLETED', risk_level = %s, external_issue = %s WHERE id = %s",
            (keywords_json_str, risk_level, external_issue, counseling_id),
        )
        conn.commit()
        cur.close()
        conn.close()

        # 6. 긴급 안건 탐지 로그 출력
        if risk_level != "정상 문의" or external_issue != "정상 문의":
            print(f"[긴급 알림 발송 대상] ID: {counseling_id} - 2D 긴급 감지됨: 위험={risk_level} (유사도: {sim_score:.4f}), 외부={external_issue} (유사도: {ext_score:.4f})!")

        # 호환성을 위해 리턴 메시지에는 간단히 쉼표 문자열로 출력
        extracted_words = [kw[0] for kw in keywords_with_scores]
        keyword_str = ", ".join(extracted_words)
        return f"Success: ID {counseling_id} -> {keyword_str} | Risk: {risk_level} ({sim_score:.4f}), External: {external_issue} ({ext_score:.4f})"

    except Exception as e:
        return f"Fail: ID {counseling_id} -> Error: {str(e)}"
