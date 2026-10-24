"""임시 단계 전환기와 안정화기.

정식 버전은 김대현이 만드는 pi/control/levels.py(LevelDriver),
pi/control/stabilizer.py(Stabilizer)다. 두 파일이 생기면 loop.py가 자동으로 그쪽을 쓴다.
함수 이름과 동작은 팀에 공유한 명세와 같다.
"""
import time
from typing import Dict, Optional

from pi import config


def relay_plan(level: int) -> Dict[str, bool]:
    a, b = config.LEVELS[level]
    return {"SA": a == "high", "PA": a != "off", "SB": b == "high", "PB": b != "off"}


class LevelDriver:
    """S가 바뀌는 필름은 P를 먼저 끄고 → S 변경 → P를 계획대로 켠다."""

    def __init__(self, relays, settle_s: float = config.RELAY_SETTLE_S) -> None:
        self.relays = relays
        self.settle_s = settle_s
        self.current_level: Optional[int] = None
        self.state = {k: False for k in ("SA", "PA", "SB", "PB")}
        relays.all_off()

    def apply(self, level: int) -> None:
        if level == self.current_level:
            return
        plan = relay_plan(level)
        for sel, power in (("SA", "PA"), ("SB", "PB")):
            if plan[sel] != self.state[sel]:
                if self.state[power]:
                    self._set(power, False)
                    time.sleep(self.settle_s)
                self._set(sel, plan[sel])
                time.sleep(self.settle_s)
            if plan[power] != self.state[power]:
                self._set(power, plan[power])
        self.current_level = level

    def _set(self, name: str, on: bool) -> None:
        self.relays.set(name, on)
        self.state[name] = on


class Stabilizer:
    """같은 후보가 stable_count번 연속이고, 마지막 전환 후 min_interval_s가 지나야 전환."""

    def __init__(self, stable_count: int = config.STABLE_COUNT,
                 min_interval_s: float = config.MIN_SWITCH_INTERVAL_S) -> None:
        self.stable_count = stable_count
        self.min_interval_s = min_interval_s
        self.reset()
        self.last_switch = -1e9

    def propose(self, candidate: int, current: int, now: float) -> Optional[int]:
        if candidate == self.last_candidate:
            self.count += 1
        else:
            self.last_candidate, self.count = candidate, 1
        if (candidate != current and self.count >= self.stable_count
                and now - self.last_switch >= self.min_interval_s):
            return candidate
        return None

    def mark_switched(self, now: float) -> None:
        self.last_switch = now
        self.count = 0

    def reset(self) -> None:
        self.last_candidate: Optional[int] = None
        self.count = 0
