"""바깥 빛(필름에 닿는 조도) 시뮬레이션.

하루 곡선 두 가지 중 하나를 쓴다.
  - 기본: 해 뜨는 시각부터 지는 시각까지 사인 곡선
  - profile: 기상청 시간별 일사량에서 만든 24칸 곡선 (pi/ai/kma.py)
여기에 구름(천천히 변하는 감쇠)과 직사광(선제 차광 시험용)을 더한다.
값의 크기는 시연 조명(LED 스탠드) 수준에 맞춰 최대 수천 lux로 잡았다.

직사광은 한 번에 튀지 않고 rise_steps 동안 서서히 오른다.
실제로 구름이 걷힐 때도 몇 초에 걸쳐 밝아지므로, 오르기 시작하는 모습을 보고
먼저 어둡게 하는 선제 차광을 시험할 수 있다.
"""
import math
import random
from typing import Callable, Optional, Sequence


class OutdoorLight:
    def __init__(self, hour_fn: Callable[[], float], sunrise: float = 6.5,
                 sunset: float = 18.0, peak_lux: float = 2000.0,
                 night_lux: float = 2.0, seed: int = 0,
                 profile: Optional[Sequence[float]] = None) -> None:
        """
        hour_fn  : 현재 시각(0~24)을 돌려주는 함수 (가상 시계)
        peak_lux : 하루 중 가장 밝을 때의 바깥 빛
        profile  : 0~23시 각 시각의 상대 밝기(최대 1.0). 주면 사인 곡선 대신 사용
        """
        self.hour_fn = hour_fn
        self.sunrise = sunrise
        self.sunset = sunset
        self.peak_lux = peak_lux
        self.night_lux = night_lux
        self.profile = list(profile) if profile is not None else None
        self.rng = random.Random(seed)
        self.cloud = 1.0      # 1.0 = 맑음, 0.4 = 많이 흐림
        self.burst = 0.0      # 직사광 추가분(lux)
        self._goal = 0.0
        self._rise_left = 0
        self._rise_steps = 1
        self._hold_left = 0
        self.last = 0.0       # 마지막으로 계산한 값. 화면 표시용 (다시 계산하면 구름이 또 움직이므로)

    def trigger_burst(self, extra_lux: float = 1500.0, rise_steps: int = 8,
                      hold_steps: int = 10) -> None:
        """직사광: rise_steps 동안 extra_lux까지 오르고, hold_steps 유지한 뒤 서서히 줄어든다."""
        self._goal = extra_lux
        self._rise_steps = max(1, rise_steps)
        self._rise_left = self._rise_steps
        self._hold_left = hold_steps
        self.burst = 0.0

    def base(self, h: float) -> float:
        """구름·직사광을 빼고 그 시각의 바깥 빛."""
        if self.profile is not None:
            # 기상청 값은 '그 시각까지 1시간 누적'이므로 30분 앞을 대표 시각으로 본다
            x = h + 0.5
            i = int(math.floor(x)) % 24
            frac = x - math.floor(x)
            v = self.profile[i - 1] * (1 - frac) + self.profile[i] * frac
            return self.peak_lux * max(v, 0.0)
        if self.sunrise <= h <= self.sunset:
            x = (h - self.sunrise) / (self.sunset - self.sunrise)
            return self.peak_lux * math.sin(math.pi * x)
        return 0.0

    def _step_burst(self) -> None:
        if self._rise_left > 0:
            self.burst += self._goal / self._rise_steps
            self._rise_left -= 1
        elif self._hold_left > 0:
            self._hold_left -= 1
        else:
            self.burst *= 0.9     # 직사광은 조금씩 사라진다

    def __call__(self) -> float:
        h = self.hour_fn()
        # 구름: 작은 무작위 걸음으로 천천히 변하게 한다.
        self.cloud = min(1.0, max(0.4, self.cloud + self.rng.uniform(-0.02, 0.02)))
        self._step_burst()
        value = self.base(h) * self.cloud + self.night_lux + self.burst
        self.last = value
        return value
