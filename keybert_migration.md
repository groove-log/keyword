# KeyBERT 제거 및 마이그레이션 기록

## KeyBERT란?

**KeyBERT**는 BERT 계열 언어 모델의 임베딩을 활용해 텍스트에서 핵심 키워드를 추출하는 Python 라이브러리입니다.

### 동작 원리

```
입력 텍스트
    │
    ▼
① n-gram 후보 추출        예) "식중독 신고", "환불 요청", "식중독", "신고" ...
    │
    ▼
② 문서 전체 임베딩        [0.023, -0.041, 0.198, ...]  (수천 차원 벡터)
    │
    ▼
③ 후보별 임베딩           각 후보 단어/구절을 벡터로 변환
    │
    ▼
④ 코사인 유사도 계산      문서 벡터 ↔ 후보 벡터 간 유사도 측정
    │
    ▼
⑤ 상위 n개 반환           유사도 높은 순서로 키워드 선정
```

### 의존성 체인 (문제의 원인)

```
keybert
  └── sentence-transformers
        └── torch (PyTorch)
              └── MPS / CUDA (GPU 초기화)
```

KeyBERT 자체가 크지 않지만, **sentence-transformers → torch** 체인이 자동으로 따라옵니다.

---

## 제거 이유: Celery Fork + MPS 충돌

### 크래시 발생 경위

```
Celery 워커 시작
    │
    ├── worker.py 모듈 import
    │     └── from keybert import KeyBERT
    │           └── import sentence_transformers
    │                 └── import torch
    │                       └── MPS(Metal GPU) 초기화 ← 여기서 GPU 컨텍스트 생성
    │
    ├── Celery가 fork()로 자식 워커 프로세스 생성
    │
    └── 자식 프로세스에서 GPU 리소스 접근 시도
          └── SIGSEGV (Segmentation Fault) 💥
```

### 크래시 로그 핵심

```
Exception Type:    EXC_BAD_ACCESS (SIGSEGV)
Termination Reason: Namespace SIGNAL, Code 11, Segmentation fault: 11

*** multi-threaded process forked ***
crashed on child side of fork pre-exec

Thread 0:
  libtorch_cpu.dylib → at::mps::HeapAllocator::MPSHeapAllocatorImpl::get_free_buffer
  IOGPU → IOGPUDeviceGetAllocatedSize
```

macOS의 Metal(MPS)은 **fork-unsafe**입니다.
부모 프로세스에서 GPU를 초기화한 후 fork하면, 자식 프로세스에서 해당 리소스를 사용할 수 없어 충돌합니다.

> **핵심**: 우리는 로컬 모델을 전혀 사용하지 않음에도,
> `keybert`를 import하는 것만으로 torch가 로드되고 GPU가 초기화됩니다.

---

## 해결 방법: KeyBERT 완전 제거

KeyBERT가 하는 일을 분해하면 다음 두 가지입니다:

1. **임베딩 생성** → 이미 llama.cpp가 담당
2. **코사인 유사도 계산** → `numpy`만 있으면 충분

따라서 KeyBERT 없이 동일한 로직을 직접 구현했습니다.

---

## 변경 내역

### `requirements.txt`

```diff
  celery==5.3.6
- keybert==0.8.5
  requests==2.32.3
+ numpy>=1.26.0
  psycopg[binary]==3.2.13
  redis==5.0.4
  python-dotenv==1.0.1
```

**제거된 의존성 (자동 해소)**

| 패키지 | 크기 | 역할 |
|--------|------|------|
| keybert | ~50MB | 키워드 추출 래퍼 |
| sentence-transformers | ~100MB | 임베딩 모델 로더 |
| torch (PyTorch) | ~2GB | 딥러닝 프레임워크 |
| torchvision / torchaudio | ~수백MB | torch 부속 패키지 |

**추가된 의존성**

| 패키지 | 크기 | 역할 |
|--------|------|------|
| numpy | ~30MB | 코사인 유사도 계산 |

---

### `worker.py`

#### 제거된 코드

```python
# 삭제됨
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer

sentence_model = SentenceTransformer('BAAI/bge-m3', device='mps')
kw_model = KeyBERT(model=sentence_model)

# 또는 (llama.cpp 연동 버전)
class LlamaCppEmbedder:
    def embed(self, sentences): ...

kw_model = KeyBERT(model=LlamaCppEmbedder(...))
```

#### 추가된 코드

```python
import numpy as np

class KeywordExtractor:
    """torch 없이 llama.cpp HTTP + numpy만으로 KeyBERT 동일 기능 구현"""

    def _get_embedding(self, text) -> list[float]:
        """llama.cpp /v1/embeddings 호출"""
        ...

    def _extract_candidates(self, text, ngram_range) -> list[str]:
        """n-gram 후보 추출 (정규식 + 집합 기반)"""
        ...

    def _cosine_similarity(self, a, b) -> float:
        """numpy 기반 코사인 유사도"""
        va, vb = np.array(a), np.array(b)
        return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))

    def extract_keywords(self, text, keyphrase_ngram_range=(1,2), top_n=3):
        """KeyBERT 동일 인터페이스 → [(키워드, 점수), ...]"""
        ...

extractor = KeywordExtractor(...)  # kw_model 대체
```

#### 호출부 변경

```diff
- keywords_with_scores = kw_model.extract_keywords(
+ keywords_with_scores = extractor.extract_keywords(
      text,
      keyphrase_ngram_range=(1, 2),
      top_n=3,
  )
```

반환값 형식 동일: `[("키워드", 0.92), ("구절", 0.88), ...]`

---

## 전후 비교

| 항목 | 기존 (KeyBERT) | 변경 후 (KeywordExtractor) |
|------|---------------|--------------------------|
| 의존 라이브러리 | keybert, sentence-transformers, torch | requests, numpy |
| 설치 용량 | ~2.5GB+ | ~30MB |
| 모델 로드 위치 | 워커 프로세스 내부 (메모리 점유) | llama.cpp 서버 (별도 프로세스) |
| GPU 초기화 | import 시점에 MPS 초기화 | 없음 |
| Celery fork 호환 | ❌ SIGSEGV 크래시 | ✅ 정상 동작 |
| 임베딩 품질 | BGE-m3 (동일) | BGE-m3 (동일) |
| 키워드 추출 방식 | 동일 (n-gram + 코사인 유사도) | 동일 |
| 인터페이스 | `kw_model.extract_keywords()` | `extractor.extract_keywords()` |

---

## 재설치 방법

```bash
# 기존 .venv의 torch/sentence-transformers 완전 제거 후 재설치
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> [!TIP]
> torch가 이미 설치된 환경이라면 `.venv`를 완전히 삭제하고 재생성하는 것이 가장 확실합니다.

---

## 워커 재기동

```bash
# pool 옵션 없이 기본 prefork 모드로 정상 동작
.venv/bin/celery -A worker worker --loglevel=info
```
