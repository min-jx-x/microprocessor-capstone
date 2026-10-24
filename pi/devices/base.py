"""장치 인터페이스 정의.

진짜 장치(BH1750Sensor, GpioRelays)와 가짜 장치(SimSensor, SimRelays)는
모두 아래와 같은 함수를 가진다. 제어 코드는 이 함수만 부르기 때문에
노트북에서는 가짜 장치, Pi에서는 진짜 장치를 끼워 넣기만 하면 된다.
"""
from typing import Optional, Protocol


class Sensor(Protocol):
    def read_lux(self) -> Optional[float]:
        """현재 조도(lux). 읽기에 실패하면 None."""
        ...

    def close(self) -> None:
        ...


class RelayBank(Protocol):
    def set(self, name: str, on: bool) -> None:
        """name: "SA", "PA", "SB", "PB" 중 하나."""
        ...

    def all_off(self) -> None:
        ...

    def close(self) -> None:
        ...
