import requests
import json

def test_api():
    url = "http://localhost:8000/api/extract/sync"
    payload = {
        "text": (
            "강남점에서 어제 도시락 구매하였습니다.\n"
            "해당 도시락을 여는 순간 잘린 쥐머리가 발견되었고 이때문에 구토 및 정신적 충격으로 "
            "병원 응급실에 이송되었습니다.\n\n"
            "먹는 음식에서 잘린 쥐머리가 나온것은 매우 충격적인 일이고 이를 언론사 제보 및 법적 "
            "소송준비를 하려고 합니다.\n\n"
            "관련해서 담당자에게 정확한 입장을 원합니다."
        ),
        "ngram_min": 1,
        "ngram_max": 3,
        "top_n": 8
    }
    
    print("Sending request to FastAPI sync extraction endpoint...")
    resp = requests.post(url, json=payload)
    print(f"Response status: {resp.status_code}")
    data = resp.json()
    print("\nAPI Response Payload:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_api()
