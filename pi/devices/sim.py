"""노트북용 가짜 장치.

SimRelays: 릴레이 상태를 메모리에만 저장한다.
SimSensor: 바깥 빛 × 필름 투과율 + 실내 잡광 + 잡음으로 조도를 계산한다.
           필름 상태는 SimRelays의 현재 릴레이 상태에서 읽는다.
"""
import random
from typing import Callable, Dict, Optional

from pi import config

# 필름 한 장의 상태별 투과율 (가정값).
# 실측(pi/tools/calibrate.py) 후 pi/data/lut.json 값으로 바꾼다.
# 두 장을 겹치면 투과율이 곱해진다. 예: high + low = 0.8 * 0.45 = 0.36
FILM_T = {"off": 0.30, "low": 0.45, "high": 0.80}


class SimRelays:
    def __init__(self) -> None:
        self.state: Dict[str, bool] = {name: False for name in config.GPIO_PINS}
        self.history = []  # (이름, on) 순서 기록. 전환 순서 테스트에 쓴다.

    def set(self, name: str, on: bool) -> None:
        if name not in self.state:
            raise KeyError(f"모르는 릴레이 이름: {name}")
        self.state[name] = on
        self.history.append((name, on))

    def all_off(self) -> None:
        for name in self.state:
            self.set(name, False)

    def close(self) -> None:
        self.all_off()

    def film_states(self) -> tuple:
        """릴레이 상태로부터 (필름 A 상태, 필름 B 상태)를 계산한다."""
        def one(sel: str, power: str) -> str:
            if not self.state[power]:
                return "off"
            return "high" if self.state[sel] else "low"
        return one("SA", "PA"), one("SB", "PB")


class SimSensor:
    def __init__(self, relays: SimRelays, outdoor_lux: Callable[[], float],
                 ambient_lux: float = 5.0, noise: float = 0.02,
                 seed: Optional[int] = None) -> None:
        """
        relays      : 필름 상태를 읽어 올 SimRelays
        outdoor_lux : 필름에 닿는 바깥 빛(lux)을 돌려주는 함수 (시나리오가 제공)
        ambient_lux : 필름과 무관한 실내 잡광
        noise       : 측정 잡음 비율 (0.02 = ±2%)
        """
        self.relays = relays
        self.outdoor_lux = outdoor_lux
        self.ambient_lux = ambient_lux
        self.noise = noise
        self.rng = random.Random(seed)

    def transmittance(self) -> float:
        a, b = self.relays.film_states()
        return FILM_T[a] * FILM_T[b]

    def read_lux(self) -> Optional[float]:
        lux = self.outdoor_lux() * self.transmittance() + self.ambient_lux
        lux *= 1.0 + self.rng.uniform(-self.noise, self.noise)
        return round(max(lux, 0.0), 1)

    def close(self) -> None:
        pass
