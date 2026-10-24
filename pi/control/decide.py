"""단계 판단 규칙.

Uno 시절 firmware/sketches/capstone_main/decision.h 의 규칙을 Python으로 옮겼다.

  1) 필름에 들어오는 빛(입사광) 추정 : incident = lux / T[cur]
  2) 필요한 투과율                   : T_need = 목표 lux / incident
  3) T가 T_need에 가장 가까운 단계를 고른다
  4) 현재 단계 오차가 (최적 단계 오차 + DEADBAND_T) 이하이면 현재 단계를 유지한다

여기에 시간대 규칙(취침·저녁은 0단계 고정, 기상 전 램프)을 더했다.
나중에 AI 모델은 같은 입력을 받아 단계를 돌려주는 함수로 이 자리를 바꾼다.
"""
import json
import os
from typing import Dict, List, Optional, Tuple

from pi import config

PERIOD_NAMES = {"sleep": "취침", "ramp": "기상 준비", "morning": "아침",
                "day": "주간", "evening": "저녁"}


def load_lut(path: str = "pi/data/lut.json") -> List[float]:
    """실측 LUT가 있으면 그 상대 투과율을, 없으면 기본값을 돌려준다."""
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                ratio = json.load(f)["ratio"]
            if len(ratio) == config.NUM_LEVELS and all(r > 0 for r in ratio):
                return [float(r) for r in ratio]
        except (OSError, ValueError, KeyError):
            pass
    return list(config.LUT_T_DEFAULT)


def parse_hhmm(text: str) -> float:
    """"07:30" -> 7.5"""
    h, m = (int(x) for x in text.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("시각 범위 밖")
    return h + m / 60


def schedule(hour: float, wake_hour: float) -> Tuple[str, Optional[float]]:
    """시각을 시간대로 나누고 목표 조도를 돌려준다. 목표가 None이면 0단계 고정."""
    ramp_start = wake_hour - config.WAKE_RAMP_MIN / 60
    if ramp_start <= hour < wake_hour:
        x = (hour - ramp_start) / (wake_hour - ramp_start)   # 0 → 1
        target = config.TARGET_WAKE_START_LUX + x * (config.TARGET_WAKE_LUX - config.TARGET_WAKE_START_LUX)
        return "ramp", target
    if wake_hour <= hour < config.WAKE_END_HOUR:
        return "morning", config.TARGET_WAKE_LUX
    if config.WAKE_END_HOUR <= hour < config.SUNSET_HOUR:
        return "day", config.TARGET_DAY_LUX
    if config.SUNSET_HOUR <= hour < config.SLEEP_START_HOUR:
        return "evening", None
    return "sleep", None


def choose_level(t_need: float, cur: int, lut: List[float]) -> int:
    """필요한 투과율에 가장 가까운 단계. 현재 단계도 충분히 가까우면(데드밴드) 그대로 둔다.
    규칙 판단과 AI 학습 정답(라벨) 만들기가 같은 함수를 쓴다."""
    errors = [abs(t - t_need) for t in lut]
    best = min(range(len(lut)), key=lambda i: errors[i])
    if errors[cur] <= errors[best] + config.DEADBAND_T:
        return cur
    return best


def incident_of(lux: float, cur: int, lut: List[float]) -> float:
    """측정 조도와 현재 단계로 필름에 들어오는 빛(5단계 기준)을 거꾸로 추정한다."""
    return max(lux / lut[cur], 1.0)     # 어두울 때 0으로 나누기 방지


def decide_rule(lux: float, hour: float, cur: int, lut: List[float],
                wake_hour: float) -> Tuple[int, Dict]:
    """다음 단계와 판단 근거(info)를 돌려준다. info는 화면 표시와 로그에 쓴다."""
    period, target = schedule(hour, wake_hour)
    info = {"period": period, "period_name": PERIOD_NAMES[period], "target": target}
    if target is None:                      # 취침·저녁: 0단계 고정
        return 0, info

    cur = max(0, min(cur, len(lut) - 1))
    incident = incident_of(lux, cur, lut)
    t_need = target / incident
    info.update({"incident": round(incident, 1), "t_need": round(t_need, 3)})
    return choose_level(t_need, cur, lut), info


class RulePolicy:
    """규칙 판단을 AI와 같은 모양(decide 메서드)으로 감싼 것. 제어 루프는 이 모양만 안다."""
    name = "rule"

    def __init__(self, lut: List[float]) -> None:
        self.lut = lut

    def decide(self, lux: float, hour: float, cur: int, wake_hour: float) -> Tuple[int, Dict]:
        return decide_rule(lux, hour, cur, self.lut, wake_hour)

    def reset(self) -> None:
        pass
