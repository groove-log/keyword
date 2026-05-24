import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kiwipiepy import Kiwi

class DummyExtractor:
    def __init__(self):
        self.kiwi = Kiwi()

    def _extract_candidates(
        self, text: str, ngram_range: tuple[int, int]
    ) -> list[str]:
        if not text.strip():
            return []

        tokens = self.kiwi.tokenize(text)
        candidates: set[str] = set()
        min_n, max_n = ngram_range

        # 1. 단일 명사 후보군 추가 (2글자 이상 핵심 명사)
        for t in tokens:
            if t.tag in ('NNG', 'NNP'):
                if len(t.form) >= 2:
                    candidates.add(t.form)

        # 2. 인접한 명사들의 연속 구간을 결합하여 명사구 후보 생성 (슬라이딩 윈도우 적용)
        i = 0
        while i < len(tokens):
            if tokens[i].tag in ('NNG', 'NNP', 'XSN'):
                j = i + 1
                chunk = [tokens[i].form]
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        chunk[-1] = chunk[-1] + tokens[j].form
                    else:
                        chunk.append(tokens[j].form)
                    current_len = len(chunk)
                    if min_n <= current_len <= max_n:
                        candidates.add(' '.join(chunk))
                        candidates.add(''.join(chunk))
                    j += 1
                i += 1
            else:
                i += 1

        # 3. 실질 동사(VV) 및 형용사(VA) 어간을 명사화
        for t in tokens:
            if t.tag in ('VV', 'VA'):
                stem = t.form
                if len(stem) >= 2:
                    last_char = stem[-1]
                    code = ord(last_char) - 0xAC00
                    if 0 <= code <= 11172:
                        jongseong = code % 28
                        if jongseong == 0:
                            nominalized_char = chr(ord(last_char) + 16)
                            nominalized = stem[:-1] + nominalized_char
                        else:
                            nominalized = stem + "음"
                        candidates.add(nominalized)

        # 4. 관형어 + 명사구 결합 구문 (예: "잘린 쥐머리")
        i = 0
        while i < len(tokens) - 2:
            if tokens[i].tag in ('VV', 'VA') and tokens[i+1].tag == 'ETM':
                modifier = tokens[i].form
                etm = tokens[i+1].form
                
                if etm == 'ᆫ':
                    if modifier.endswith('리'):
                        modifier_str = modifier[:-1] + '린'
                    elif modifier.endswith('하'):
                        modifier_str = modifier[:-1] + '한'
                    elif modifier.endswith('되'):
                        modifier_str = modifier[:-1] + '된'
                    else:
                        modifier_str = modifier + 'ㄴ'
                elif etm == '는':
                    modifier_str = modifier + '는'
                elif etm == '은':
                    modifier_str = modifier + '은'
                elif etm == '을':
                    modifier_str = modifier + '을'
                else:
                    modifier_str = modifier + etm
                
                j = i + 2
                chunk = []
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        if chunk:
                            chunk[-1] = chunk[-1] + tokens[j].form
                    else:
                        chunk.append(tokens[j].form)
                    
                    if chunk:
                        phrase_spaced = modifier_str + ' ' + ' '.join(chunk)
                        phrase_unspaced = modifier_str + ' ' + ''.join(chunk)
                        candidates.add(phrase_spaced)
                        candidates.add(phrase_unspaced)
                    j += 1
                i = j
            else:
                i += 1

        # 5. 명사구 + 동사구 동작 결합 구문 (예: "쥐머리 발견", "응급실 이송")
        i = 0
        while i < len(tokens):
            if tokens[i].tag in ('NNG', 'NNP'):
                noun_chunk = [tokens[i].form]
                j = i + 1
                while j < len(tokens) and tokens[j].tag in ('NNG', 'NNP', 'XSN', 'NNB'):
                    if tokens[j].tag == 'XSN':
                        noun_chunk[-1] = noun_chunk[-1] + tokens[j].form
                    else:
                        noun_chunk.append(tokens[j].form)
                    j += 1
                
                k = j
                if k < len(tokens) and tokens[k].tag in ('JKS', 'JKO', 'JKB', 'JX'):
                    k += 1
                
                if k < len(tokens) - 1:
                    if tokens[k].tag in ('NNG', 'NNP') and tokens[k+1].tag in ('XSV', 'XSA', 'VV'):
                        action_noun = tokens[k].form
                        
                        spaced_nouns = ' '.join(noun_chunk)
                        unspaced_nouns = ''.join(noun_chunk)
                        
                        candidates.add(spaced_nouns + ' ' + action_noun)
                        candidates.add(unspaced_nouns + ' ' + action_noun)
                        candidates.add(unspaced_nouns + action_noun)
                        
                        suffix = tokens[k+1].form
                        if suffix == '되':
                            candidates.add(spaced_nouns + ' ' + action_noun + '됨')
                            candidates.add(unspaced_nouns + ' ' + action_noun + '됨')
                            candidates.add(unspaced_nouns + action_noun + '됨')
                        elif suffix == '하':
                            candidates.add(spaced_nouns + ' ' + action_noun + '함')
                            candidates.add(unspaced_nouns + ' ' + action_noun + '함')
                            candidates.add(unspaced_nouns + action_noun + '함')
                i = max(i + 1, j)
            else:
                i += 1

        return list(candidates)

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
    
    targets = ["잘린 쥐", "잘린 쥐 머리", "잘린 쥐머리", "병원 응급실 이송", "병원 응급실 이송됨", "소송 준비", "소송준비", "소송준비함", "어제 도시락 구매"]
    print("\n--- Verification of Expected Context Phrases ---")
    for t in targets:
        present = t in candidates
        print(f" -> '{t}': {'PASSED' if present else 'FAILED'}")

if __name__ == "__main__":
    main()
