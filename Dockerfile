# 1. Base Image 선택
FROM python:3.11-slim

# 2. 필수 패키지 설치 (gcc 등 빌드 에러 방지)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 복사
COPY . .

# 6. Celery 실행
CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
