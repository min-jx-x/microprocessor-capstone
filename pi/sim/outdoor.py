"""바깥 빛(필름에 닿는 조도) 시뮬레이션.

해 뜨는 시각부터 지는 시각까지 사인 곡선으로 밝아졌다 어두워지고,
구름(천천히 변하는 감쇠)과 갑작스러운 직사광(선제 차광 시험용)을 더한다.
값의 크기는 시연 조명(LED 스탠드) 수준에 맞춰 최대 수천 lux로 잡았다.
"""
import math
import random
from typing import Callable


class OutdoorLight:
    def __init__(self, hour_fn: Callable[[], float], sunrise: float = 6.5,
                 sunset: float = 18.0, peak_lux: float = 2000.0,
                 night_lux: float = 2.0, seed: int = 0) -> None:
        self.hour_fn = hour_fn
        self.sunrise = sunrise
        self.sunset = sunset
        self.peak_lux = peak_lux
        self.night_lux = night_lux
        self.rng = random.Random(seed)
        self.cloud = 1.0      # 1.0 = 맑음, 0.4 = 많이 흐림
        self.burst = 0.0      # 갑작스러운 직사광 추가분(lux)
        self.last = 0.0       # 마지막으로 계산한 값. 화면 표시용 (다시 계산하면 구름이 또 움직이므로)

    def trigger_burst(self, extra_lux: float = 1500.0) -> None:
        """선제 차광 시연용: 바깥 빛을 갑자기 올린다. 이후 서서히 줄어든다."""
        self.burst = extra_lux

    def __call__(self) -> float:
        h = self.hour_fn()
        if self.sunrise <= h <= self.sunset:
            x = (h - self.sunrise) / (self.sunset - self.sunrise)
            base = self.peak_lux * math.sin(math.pi * x)
        else:
            base = 0.0
        # 구름: 작은 무작위 걸음으로 천천히 변하게 한다.
        self.cloud = min(1.0, max(0.4, self.cloud + self.rng.uniform(-0.02, 0.02)))
        value = base * self.cloud + self.night_lux + self.burst
        self.burst *= 0.9     # 직사광은 조금씩 사라진다
        self.last = value
        return value
