import sys
import os

# 현재 디렉토리를 sys.path에 추가하여 worker.py를 임포트할 수 있도록 함
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from worker import classifier

def test_hybrid_safeguard():
    print("\n==================================================")
    print("TDD RED Stage Check: Hybrid Safeguard Detection")
    print("==================================================")
    
    text = (
        "상계점 점포 앞 눈이 많이 쌓여있는데, 전혀 처리를 안해주고 계시네요. "
        "저대로 두면 길이 굉장히 미끄러워 질것 같습니다. "
        "통행하시는 분들 낙상사고도 우려가 됩니다."
    )
    
    # 1. AI 유사도 점수 사전 확보
    risk_level, score = classifier.classify(text)
    print(f"Raw Output - Category: '{risk_level}', Score: {score:.4f}")
    
    # 2. TDD RED 어설션: 하이브리드 렉시콘이 작동하여 최종적으로 '안전사고'로 감지되어야 함.
    # 하지만 현재 미구현된 상태이므로 아래 어설션은 실패(AssertionError)해야 정상입니다!
    assert risk_level == "안전사고", f"FAIL: Expected '안전사고' due to lexicon '낙상' trigger, but got '{risk_level}'"
    print("PASS: Hybrid Lexicon Safeguard is working perfectly!")

if __name__ == "__main__":
    try:
        test_hybrid_safeguard()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[RED STAGE CONFIRMED] Test failed as expected: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected test error: {e}")
        sys.exit(2)
