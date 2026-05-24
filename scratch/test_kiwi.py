import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kiwipiepy import Kiwi

def test_kiwi():
    kiwi = Kiwi()
    text = (
        "강남점에서 어제 도시락 구매하였습니다.\n"
        "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
        "병원 응급실에 이송되었습니다.\n\n"
        "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
        "소송준비를 하려고 합니다."
    )
    
    tokens = kiwi.tokenize(text)
    print("=== Kiwi Token Details ===")
    for t in tokens:
        print(f"Form: '{t.form}' | Tag: '{t.tag}' | Start: {t.start} | Len: {t.len}")

if __name__ == "__main__":
    test_kiwi()
