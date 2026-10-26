"""단계 전환 드라이버 (안전 전환 순서 보장).

PDLC 필름의 전압 선택 릴레이(S)를 바꿀 때 항상 전원 릴레이(P)를 먼저 차단하여
쇼트 및 아크 방지를 보장한다.
모든 설정값은 config.py에서 가져오며, 코드에 숫자를 직접 쓰지 않는다.
"""
import time
from typing import Optional

from pi import config


def relay_plan(level: int) -> dict[str, bool]:
    """단계 번호를 {"SA", "PA", "SB", "PB"} 릴레이 상태로 변환한다.

    필름 상태가 'high'면 S=True(NO=100V), 'low'면 S=False(NC=45V), 'off'면 P=False·S=False.
    """
    a, b = config.LEVELS[level]
    return {
        "SA": a == "high",
        "PA": a != "off",
        "SB": b == "high",
        "PB": b != "off",
    }


class LevelDriver:
    """S가 바뀌는 필름은 P를 먼저 끄고 → settle_s 대기 → S 변경 → 대기 → P를 계획대로 켠다."""

    def __init__(self, relays, settle_s: float = config.RELAY_SETTLE_S) -> None:
        self.relays = relays
        self.settle_s = settle_s
        self.current_level: Optional[int] = None
        self.state = {k: False for k in config.GPIO_PINS}
        self.relays.all_off()

    def apply(self, level: int) -> None:
        """지정한 단계로 릴레이를 안전한 순서로 전환한다."""
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
