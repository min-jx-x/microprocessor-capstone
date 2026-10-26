"""깜빡임 방지 안정화기.

같은 방향(현재보다 어둡게 / 밝게) 후보가 stable_count번 연속이고,
마지막 전환 후 min_interval_s가 지나야 전환한다. 전환할 단계는 가장 최근 후보.
모든 설정값은 config.py에서 가져오며, 코드에 숫자를 직접 쓰지 않는다.
"""
from typing import Optional

from pi import config


class Stabilizer:
    def __init__(self, stable_count: int = config.STABLE_COUNT,
                 min_interval_s: float = config.MIN_SWITCH_INTERVAL_S) -> None:
        self.stable_count = stable_count
        self.min_interval_s = min_interval_s
        self.reset()
        self.last_switch = config.STABILIZER_INITIAL_LAST_SWITCH

    def propose(self, candidate: int, current: int, now: float) -> Optional[int]:
        """안정화 조건을 만족하면 candidate를 반환하고, 아니면 None을 반환한다."""
        direction = (candidate > current) - (candidate < current)  # -1 어둡게, 0 유지, +1 밝게
        if direction == 0:
            self.reset()
            return None

        if direction == self.direction:
            self.count += 1
        else:
            self.direction = direction
            self.count = 1

        if self.count >= self.stable_count and now - self.last_switch >= self.min_interval_s:
            return candidate
        return None

    def mark_switched(self, now: float) -> None:
        """단계가 실제로 전환되었을 때 호출하여 전환 시각을 기록한다."""
        self.last_switch = now
        self.reset()

    def reset(self) -> None:
        """방향 카운트와 방향 상태를 초기화한다."""
        self.direction = 0
        self.count = 0
