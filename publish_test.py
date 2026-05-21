"""
테스트용 태스크 발행 스크립트
워커가 실행 중인 상태에서 이 스크립트를 실행하면 Redis 큐에 작업이 쌓입니다.
"""

from worker import process_keyword_extraction

# 샘플 상담 데이터 (DB에서 직접 읽어오는 것을 시뮬레이션)
test_cases = [
    (1, "고객이 식중독 증상을 호소하며 환불을 요청하고 있습니다. 빠른 처리가 필요합니다."),
    (2, "배송이 지연되어 소비자원에 민원을 제기하겠다고 합니다."),
    (3, "제품 품질 불량으로 소송을 고려 중이라고 고객이 말했습니다."),
    (4, "일반 고객 문의: 제품 사용 방법에 대해 질문하고 있습니다."),
]

if __name__ == "__main__":
    print("=== 태스크 발행 시작 ===")
    for counseling_id, text in test_cases:
        # .delay()를 사용하면 Celery 워커에게 비동기로 태스크를 전달
        result = process_keyword_extraction.delay(counseling_id, text)
        print(f"[발행 완료] ID: {counseling_id} | Task ID: {result.id}")
    print("=== 모든 태스크 발행 완료. 워커 로그를 확인하세요. ===")
