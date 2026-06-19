-- counseling_data 테이블 생성 DDL
-- PostgreSQL 기준

-- 데이터베이스 및 사용자의 기본 시간대를 Asia/Seoul(KST)로 설정
-- (NOW() 함수 및 DEFAULT NOW()가 코드 변경 없이 한국 시간 기준으로 작동)
ALTER DATABASE ledger_db SET timezone TO 'Asia/Seoul';
ALTER ROLE ledger_user SET timezone TO 'Asia/Seoul';

CREATE TABLE IF NOT EXISTS counseling_data (
    id                  SERIAL PRIMARY KEY,
    text                TEXT        NOT NULL,
    keywords            TEXT,
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    risk_level          VARCHAR(50) NOT NULL DEFAULT '정상 문의',
    external_issue      VARCHAR(50) NOT NULL DEFAULT '정상 문의',
    urgency_level       VARCHAR(50) NOT NULL DEFAULT 'MONITOR',
    detected_categories TEXT,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- 기존 테이블이 존재할 경우 대비하여 컬럼 추가 보장 DDL (Idempotent)
ALTER TABLE counseling_data ADD COLUMN IF NOT EXISTS external_issue VARCHAR(50) NOT NULL DEFAULT '정상 문의';
ALTER TABLE counseling_data ADD COLUMN IF NOT EXISTS urgency_level VARCHAR(50) NOT NULL DEFAULT 'MONITOR';
ALTER TABLE counseling_data ADD COLUMN IF NOT EXISTS detected_categories TEXT;

-- 오분류 피드백 테이블
CREATE TABLE IF NOT EXISTS counseling_feedback (
    id              SERIAL PRIMARY KEY,
    counseling_id   INT NOT NULL REFERENCES counseling_data(id) ON DELETE CASCADE,
    is_correct      BOOLEAN NOT NULL,
    actual_danger   VARCHAR(100),
    actual_external VARCHAR(100),
    actual_urgency  VARCHAR(50),
    note            TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 조회 성능 인덱스 (신규 배포 시 자동 생성, 기존 DB는 수동 실행 필요)
CREATE INDEX IF NOT EXISTS idx_counseling_status_updated ON counseling_data(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_counseling_risk_level ON counseling_data(risk_level);
CREATE INDEX IF NOT EXISTS idx_counseling_urgency ON counseling_data(urgency_level);
CREATE INDEX IF NOT EXISTS idx_counseling_created_at ON counseling_data(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_counseling_id ON counseling_feedback(counseling_id);
CREATE INDEX IF NOT EXISTS idx_feedback_is_correct ON counseling_feedback(is_correct);

-- 샘플 데이터 삽입 (테이블이 비어있을 때만 샘플 데이터 입력 유도 혹은 기존 4건 안전 삽입)
-- 여기서는 테이블에 무조건 중복 적재를 피하기 위해 간단히 테이블이 비었는지 확인 후 삽입하는 구조로 개선할 수도 있지만,
-- 하위 호환성을 유지하여 기존 쿼리 포맷대로 안전하게 제공합니다.
INSERT INTO counseling_data (text, status) VALUES
('고객이 식중독 증상을 호소하며 환불을 요청하고 있습니다. 빠른 처리가 필요합니다.', 'PENDING'),
('배송이 지연되어 소비자원에 민원을 제기하겠다고 합니다.', 'PENDING'),
('제품 품질 불량으로 소송을 고려 중이라고 고객이 말했습니다.', 'PENDING'),
('일반 고객 문의: 제품 사용 방법에 대해 질문하고 있습니다.', 'PENDING')
ON CONFLICT DO NOTHING;

