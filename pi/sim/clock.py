"""가상 시계.

speed=1이면 실제 시간과 같고, speed=720이면 하루(24시간)가 2분에 지나간다.
시연의 '하루 압축 재생'에 쓴다.
"""
import time
from datetime import datetime, timedelta


class VirtualClock:
    def __init__(self, start: datetime, speed: float = 1.0) -> None:
        self.start = start
        self.speed = speed
        self._real0 = time.monotonic()

    def now(self) -> datetime:
        elapsed = (time.monotonic() - self._real0) * self.speed
        return self.start + timedelta(seconds=elapsed)

    def hour(self) -> float:
        """0.0 ~ 23.99 형태의 시각. 7.5는 07:30."""
        t = self.now()
        return t.hour + t.minute / 60 + t.second / 3600

    def set_now(self, now: datetime) -> None:
        """배속은 그대로 두고 지금 가상 시각만 바꾼다 (휴대폰 시각으로 맞출 때)."""
        self.start, self._real0 = now, time.monotonic()

    def set_speed(self, speed: float) -> None:
        """현재 가상 시각을 유지한 채 배속만 바꾼다."""
        self.start = self.now()
        self._real0 = time.monotonic()
        self.speed = speed
