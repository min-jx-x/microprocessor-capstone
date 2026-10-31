"""문장 정리와 특징 뽑기. 학습(train.py)과 추론(intent.py)이 반드시 같은 함수를 쓴다."""
import re
from typing import List, Optional

# 음성 인식 결과에 자주 섞이는 문장부호·특수문자
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

NGRAM_MIN, NGRAM_MAX = 1, 3


def normalize(text: str) -> str:
    """소문자, 문장부호 제거, 공백 하나로. 예: '2단계로 해 줘!!' → '2단계로 해 줘'"""
    t = _PUNCT.sub(" ", str(text or "").lower())
    return _SPACES.sub(" ", t).strip()


def char_ngrams(text: str) -> List[str]:
    """단어마다 앞뒤에 공백을 붙여 글자 1~3개 묶음을 만든다.
    띄어쓰기가 들쭉날쭉한 음성 인식 결과('해줘'/'해 줘')에도 비슷한 특징이 나오게 한다."""
    out = []
    for w in normalize(text).split():
        w = f" {w} "
        for n in range(NGRAM_MIN, NGRAM_MAX + 1):
            out.extend(w[i:i + n] for i in range(max(1, len(w) - n + 1)))
    return out


# '2단계', '이 단계', '레벨 1', '1번', '0으로' 같은 절대 단계 표현.
# '한 단계', '두 단계'는 '한 단계 어둡게'처럼 상대 표현으로 많이 쓰여서 일부러 넣지 않는다.
_NUM_WORDS = {"영": 0, "공": 0, "빵": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5}
_LEVEL_PATTERNS = [
    re.compile(r"(\d+)\s*(?:단계|번|레벨)"),
    re.compile(r"(?:단계|레벨)\s*(?:를|을)?\s*(\d+)"),
    re.compile(r"(?<![가-힣])(영|공|빵|일|이|삼|사|오)\s*(?:단계|번)"),
    re.compile(r"(?<![\d가-힣])(\d+)\s*(?:으로|로)\b"),
]


def extract_level(text: str) -> Optional[int]:
    """문장에서 절대 단계 숫자를 찾는다. 없으면 None. 범위 검사는 handler가 한다."""
    t = normalize(text)
    for pat in _LEVEL_PATTERNS:
        m = pat.search(t)
        if m:
            v = m.group(1)
            return int(v) if v.isdigit() else _NUM_WORDS[v]
    return None
