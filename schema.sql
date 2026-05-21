-- counseling_data 테이블 생성 DDL
-- PostgreSQL 기준

CREATE TABLE IF NOT EXISTS counseling_data (
    id          SERIAL PRIMARY KEY,
    text        TEXT        NOT NULL,
    keywords    TEXT,
    status      VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- 샘플 데이터 삽입
INSERT INTO counseling_data (text, status) VALUES
('고객이 식중독 증상을 호소하며 환불을 요청하고 있습니다. 빠른 처리가 필요합니다.', 'PENDING'),
('배송이 지연되어 소비자원에 민원을 제기하겠다고 합니다.', 'PENDING'),
('제품 품질 불량으로 소송을 고려 중이라고 고객이 말했습니다.', 'PENDING'),
('일반 고객 문의: 제품 사용 방법에 대해 질문하고 있습니다.', 'PENDING');
