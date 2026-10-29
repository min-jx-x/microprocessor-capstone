"""AI 판단 (Pi에서 실행). scikit-learn 없이 ai_tree.json만 읽어 if문으로 추론한다.

RulePolicy(pi/control/decide.py)와 같은 모양이라 제어 루프에서 그대로 바꿔 끼울 수 있다.
저녁·취침(목표 없음)은 규칙과 똑같이 0단계 고정이고, 목표가 있는 시간대만 모델이 고른다.
"""
import json
from collections import deque
from typing import Dict, List, Tuple

from typing import Optional

from pi import config
from pi.ai.features import FEATURE_LABELS, HISTORY, make_features, show
from pi.control.decide import PERIOD_NAMES, incident_of, personal_target

DEFAULT_MODEL = config.AI_MODEL_PATH   # 3단계: ai_tree.json, 6단계: ai_tree_6level.json


class AIPolicy:
    name = "ai"

    def __init__(self, lut: List[float], path: str = DEFAULT_MODEL) -> None:
        with open(path, encoding="utf-8") as f:
            self.m = json.load(f)
        self.lut = lut
        self.meta = self.m.get("meta", {})
        self.hist: deque = deque(maxlen=HISTORY)
        self.last_x: Optional[List[float]] = None   # 마지막 판단의 입력 (화면 설명용, 저녁·취침이면 None)
        # 모델을 학습할 때의 투과율표·단계 순서와 지금 값이 다르면 다시 학습해야 한다 (python -m pi.ai.retrain)
        trained_lut = self.meta.get("lut")
        trained_levels = self.meta.get("levels")
        self.stale = (
            (trained_lut is not None and (len(trained_lut) != len(lut) or any(
                abs(a - b) > 1e-3 for a, b in zip(trained_lut, lut))))
            or (trained_levels is not None
                and [tuple(x) for x in trained_levels] != [tuple(x) for x in config.LEVELS]))
        if self.stale:
            print("[ai] 경고: 모델이 지금과 다른 투과율표로 학습됨 → python -m pi.ai.retrain 필요")

    def reset(self) -> None:
        self.hist.clear()
        self.last_x = None

    def predict(self, x: List[float]) -> int:
        """트리를 뿌리부터 따라 내려간다. 잎(left == -1)에 닿으면 그 잎의 단계."""
        m, node = self.m, 0
        while m["left"][node] != -1:
            go_left = x[m["feature"][node]] <= m["threshold"][node]
            node = m["left"][node] if go_left else m["right"][node]
        return self._leaf_level(node)

    def _leaf_level(self, node: int) -> int:
        # 다른 단계 수로 학습된 모델이 범위 밖 단계를 내도 가장 밝은 단계로 묶는다 (재학습 전 안전장치)
        return min(int(self.m["classes"][self.m["leaf_class"][node]]), config.NUM_LEVELS - 1)

    def _cond(self, node: int, x: Optional[List[float]] = None) -> Dict:
        """노드의 질문 하나. x가 있으면 그 값과 예/아니오도 같이."""
        name = self.m["features"][self.m["feature"][node]]
        th = self.m["threshold"][node]
        c = {"feature": name, "label": FEATURE_LABELS.get(name, name), "threshold": show(name, th)}
        if x is not None:
            v = x[self.m["feature"][node]]
            c.update(value=show(name, v), yes=v <= th)
        return c

    def path(self, x: List[float]) -> Tuple[List[Dict], int]:
        """x가 트리를 따라 내려간 길과 도착한 단계. predict와 같은 길이다 (화면에서 '왜 이 단계인지' 보여 줄 때)."""
        m, node, steps = self.m, 0, []
        while m["left"][node] != -1:
            c = self._cond(node, x)
            steps.append(c)
            node = m["left"][node] if c["yes"] else m["right"][node]
        return steps, self._leaf_level(node)

    def explain(self) -> Optional[Dict]:
        """마지막 판단의 입력과 트리 경로. 저녁·취침(목표 없음)이면 None."""
        if self.last_x is None:
            return None
        names = self.m["features"]
        steps, level = self.path(self.last_x)
        return {"inputs": [{"feature": n, "label": FEATURE_LABELS.get(n, n), "value": show(n, v)}
                           for n, v in zip(names, self.last_x)],
                "path": steps, "level": level}

    def top(self, depth: int = 3, node: int = 0) -> Dict:
        """트리 위쪽 depth단 (화면 표시용). 더 깊은 곳은 그 아래에서 나올 수 있는 단계만 적는다."""
        m = self.m
        if m["left"][node] == -1:
            return {"level": self._leaf_level(node)}
        if depth == 0:
            return {"levels": sorted(self._levels_under(node))}
        return dict(self._cond(node), yes=self.top(depth - 1, m["left"][node]),
                    no=self.top(depth - 1, m["right"][node]))

    def _levels_under(self, node: int) -> set:
        m, out, stack = self.m, set(), [node]
        while stack:
            n = stack.pop()
            if m["left"][n] == -1:
                out.add(self._leaf_level(n))
            else:
                stack += [m["left"][n], m["right"][n]]
        return out

    def decide(self, lux: float, hour: float, cur: int, wake_hour: float,
               scale: Optional[Dict[str, float]] = None) -> Tuple[int, Dict]:
        # 개인 선호 보정은 목표값만 바꾼다. 모델(빛 변화 예측)은 사용자와 무관한 공통 모델
        period, target, base = personal_target(hour, wake_hour, scale)
        info = {"period": period, "period_name": PERIOD_NAMES[period], "target": target,
                "base_target": base}
        inc = incident_of(lux, cur, self.lut)
        self.hist.append(inc)               # 저녁에도 기록은 이어서 쌓는다
        if target is None:
            self.last_x = None
            return 0, info
        x = make_features(target, self.hist, cur)
        self.last_x = x
        info.update({"incident": round(inc, 1), "t_need": round(target / inc, 3),
                     "rate": round(x[1], 3)})
        return self.predict(x), info
