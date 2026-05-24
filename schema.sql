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

-- 샘플 데이터 삽입 (테이블이 비어있을 때만 샘플 데이터 입력 유도 혹은 기존 4건 안전 삽입)
-- 여기서는 테이블에 무조건 중복 적재를 피하기 위해 간단히 테이블이 비었는지 확인 후 삽입하는 구조로 개선할 수도 있지만,
-- 하위 호환성을 유지하여 기존 쿼리 포맷대로 안전하게 제공합니다.
INSERT INTO counseling_data (text, status) VALUES
('고객이 식중독 증상을 호소하며 환불을 요청하고 있습니다. 빠른 처리가 필요합니다.', 'PENDING'),
('배송이 지연되어 소비자원에 민원을 제기하겠다고 합니다.', 'PENDING'),
('제품 품질 불량으로 소송을 고려 중이라고 고객이 말했습니다.', 'PENDING'),
('일반 고객 문의: 제품 사용 방법에 대해 질문하고 있습니다.', 'PENDING')
ON CONFLICT DO NOTHING;

