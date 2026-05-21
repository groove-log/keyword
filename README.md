# 키워드 추출 프로토타입 (Keyword Extraction Prototype)

## 프로젝트 구조

```
keyword/
├── worker.py          # Celery 워커 (핵심 로직)
├── publish_test.py    # 태스크 발행 테스트 스크립트
├── schema.sql         # PostgreSQL 테이블 DDL
├── requirements.txt   # Python 패키지 의존성
└── README.md
```

## 아키텍처

```
[클라이언트 / API 서버]
        │ .delay() 호출
        ▼
[Redis 브로커 (큐)] ←──────── 메시지 보관
        │
        ▼
[Celery 워커 - worker.py]
  ├── BGE-m3 모델 (KeyBERT)
  │     └── 키워드 추출
  ├── PostgreSQL 업데이트 (keywords, status)
  └── 긴급 키워드 룰베이스 탐지
```

## 환경 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

> **Mac MPS(Metal) 주의**: `sentence-transformers`는 PyTorch를 사용합니다.  
> MPS 가속을 위해 PyTorch 2.0+ (Apple Silicon 지원 빌드)가 필요합니다.
> ```bash
> pip install torch torchvision torchaudio
> ```

### 2. Redis 실행 (Homebrew)

```bash
brew install redis
brew services start redis

# 연결 확인
redis-cli ping  # → PONG
```

### 3. PostgreSQL 설정

```bash
# 테이블 생성
psql -U postgres -d postgres -f schema.sql
```

`worker.py`의 `get_db_connection()` 함수에서 비밀번호를 실제 값으로 변경하세요.

```python
def get_db_connection():
    return psycopg2.connect(
        dbname="postgres", user="postgres", password="your_password", ...
    )
```

## 실행 방법

### 워커 시작 (터미널 1)

```bash
celery -A worker worker --loglevel=info
```

### 태스크 발행 테스트 (터미널 2)

```bash
python publish_test.py
```

## 태스크 흐름

| 단계 | 처리 내용 |
|------|-----------|
| 1    | Redis 큐에서 `(counseling_id, text)` 수신 |
| 2    | BGE-m3 모델로 상위 3개 키워드 추출 (1~2단어) |
| 3    | PostgreSQL `counseling_data` 테이블 업데이트 (`keywords`, `status='COMPLETED'`) |
| 4    | 긴급 키워드 룰베이스 탐지 (`소비자원`, `식중독`, `소송`, `언론`) |

## 긴급 키워드 목록

| 키워드 | 비고 |
|--------|------|
| 소비자원 | 민원 제기 위험 |
| 식중독 | 건강/안전 이슈 |
| 소송 | 법적 분쟁 위험 |
| 언론 | 언론 노출 위험 |

> 향후 `[긴급 알림 발송 대상]` 로그가 출력되는 시점에 Mpush API 호출 로직을 추가하세요.

.venv/bin/celery -A worker worker --loglevel=info

python3 publish_test.py