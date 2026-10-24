"""AI 판단 (Pi에서 실행). scikit-learn 없이 ai_tree.json만 읽어 if문으로 추론한다.

RulePolicy(pi/control/decide.py)와 같은 모양이라 제어 루프에서 그대로 바꿔 끼울 수 있다.
저녁·취침(목표 없음)은 규칙과 똑같이 0단계 고정이고, 목표가 있는 시간대만 모델이 고른다.
"""
import json
from collections import deque
from typing import Dict, List, Tuple

from pi.ai.features import HISTORY, make_features
from typing import Optional

from pi.control.decide import PERIOD_NAMES, incident_of, personal_target

DEFAULT_MODEL = "pi/data/ai_tree.json"


class AIPolicy:
    name = "ai"

    def __init__(self, lut: List[float], path: str = DEFAULT_MODEL) -> None:
        with open(path, encoding="utf-8") as f:
            self.m = json.load(f)
        self.lut = lut
        self.meta = self.m.get("meta", {})
        self.hist: deque = deque(maxlen=HISTORY)
        # 모델을 학습할 때의 투과율표와 지금 투과율표가 다르면 다시 학습해야 한다 (python -m pi.ai.retrain)
        trained_lut = self.meta.get("lut")
        self.stale = trained_lut is not None and any(
            abs(a - b) > 1e-3 for a, b in zip(trained_lut, lut))
        if self.stale:
            print("[ai] 경고: 모델이 지금과 다른 투과율표로 학습됨 → python -m pi.ai.retrain 필요")

    def reset(self) -> None:
        self.hist.clear()

    def predict(self, x: List[float]) -> int:
        """트리를 뿌리부터 따라 내려간다. 잎(left == -1)에 닿으면 그 잎의 단계."""
        m, node = self.m, 0
        while m["left"][node] != -1:
            go_left = x[m["feature"][node]] <= m["threshold"][node]
            node = m["left"][node] if go_left else m["right"][node]
        return m["classes"][m["leaf_class"][node]]

    def decide(self, lux: float, hour: float, cur: int, wake_hour: float,
               scale: Optional[Dict[str, float]] = None) -> Tuple[int, Dict]:
        # 개인 선호 보정은 목표값만 바꾼다. 모델(빛 변화 예측)은 사용자와 무관한 공통 모델
        period, target, base = personal_target(hour, wake_hour, scale)
        info = {"period": period, "period_name": PERIOD_NAMES[period], "target": target,
                "base_target": base}
        inc = incident_of(lux, cur, self.lut)
        self.hist.append(inc)               # 저녁에도 기록은 이어서 쌓는다
        if target is None:
            return 0, info
        x = make_features(target, self.hist, cur)
        info.update({"incident": round(inc, 1), "t_need": round(target / inc, 3),
                     "rate": round(x[1], 3)})
        return self.predict(x), info
