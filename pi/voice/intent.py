"""의도 분류기 추론 (Pi에서 인터넷 없이 실행, scikit-learn 불필요).

모델 파일(pi/data/intent_model.json)은 노트북에서 python -m pi.voice.train 으로 만든다.
계산: 글자 n-gram 개수 × idf → 길이 1로 정규화(TF-IDF) → 의도별 점수(로지스틱 회귀) → softmax 확률.
"""
import json
import math
import os
from typing import Dict, Optional, Tuple

from pi import config
from pi.voice.text import char_ngrams

INTENTS = ("darker", "brighter", "set_level", "privacy", "max_bright", "auto", "status", "other")


class IntentModel:
    def __init__(self, path: Optional[str] = None) -> None:
        path = path or config.VOICE_MODEL_PATH
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        self.classes = m["classes"]
        self.vocab: Dict[str, int] = m["vocab"]
        self.idf = m["idf"]
        self.coef = m["coef"]               # [의도][특징]
        self.intercept = m["intercept"]
        self.meta = m.get("meta", {})

    def proba(self, text: str) -> Dict[str, float]:
        counts: Dict[int, float] = {}
        for g in char_ngrams(text):
            j = self.vocab.get(g)
            if j is not None:
                counts[j] = counts.get(j, 0.0) + 1.0
        x = {j: c * self.idf[j] for j, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in x.values())) or 1.0
        scores = [b + sum(w[j] * v / norm for j, v in x.items())
                  for w, b in zip(self.coef, self.intercept)]
        top = max(scores)
        exp = [math.exp(s - top) for s in scores]
        total = sum(exp)
        return {c: e / total for c, e in zip(self.classes, exp)}

    def predict(self, text: str) -> Tuple[str, float]:
        """(의도, 확률). 아는 글자 묶음이 하나도 없으면 ('other', 0.0)."""
        if not any(g in self.vocab for g in char_ngrams(text)):
            return "other", 0.0
        p = self.proba(text)
        best = max(p, key=p.get)
        return best, p[best]


def load_model() -> Optional[IntentModel]:
    """모델 파일이 없으면 None (그때는 LLM만, LLM도 없으면 '못 알아들음')."""
    if not os.path.exists(config.VOICE_MODEL_PATH):
        return None
    return IntentModel()
