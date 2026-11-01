"""센서 입력 평활: 최근 N개 측정의 중앙값 (규칙·AI 공통, 제어 루프와 오프라인 시뮬레이터가 같이 쓴다).

단계마다 투과율이 달라서, 단계를 바꾸기 전에 잰 값과 섞으면 입사광을 잘못 추정한다.
그래서 지금 단계에서 잰 값만 골라 중앙값을 낸다 (단계를 바꾼 직후에는 1개, 2개 … N개로 늘어남).
"""
import statistics
from collections import deque
from typing import Optional

from pi import config


class LuxMedian:
    def __init__(self, n: Optional[int] = None) -> None:
        self.n = max(1, int(config.SENSOR_MEDIAN_N if n is None else n))
        self.buf: deque = deque(maxlen=self.n)        # (단계, lux)

    def add(self, level: int, lux: float) -> float:
        """측정값을 넣고, 지금 단계에서 잰 최근 값들의 중앙값을 돌려준다."""
        self.buf.append((level, lux))
        same = [x for lv, x in self.buf if lv == level]
        return float(statistics.median(same))

    def reset(self) -> None:
        self.buf.clear()
