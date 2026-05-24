import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kiwipiepy import Kiwi
from scratch.test_phrase_extractor import DummyExtractor

def main():
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다.\n\n"
        "관련해서 담당자에게 정확한 입장을 원합니다."
    )
    
    extractor = DummyExtractor()
    candidates = extractor._extract_candidates(text, (1, 3))
    print(f"Total Extracted Candidates: {len(candidates)}")
    print("Candidates List:")
    print(sorted(list(candidates)))

if __name__ == "__main__":
    main()
