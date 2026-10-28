"""Raspberry Pi GPIO 릴레이 제어 드라이버.

gpiozero의 OutputDevice를 사용하여 4개 릴레이(SA, PA, SB, PB)를 제어한다.
모든 설정값(핀 번호, 액티브 로우 여부 등)은 config.py에서 가져오며, 코드에 숫자를 직접 쓰지 않는다.
"""
from typing import Optional
from gpiozero import OutputDevice

from pi import config


class GpioRelays:
    def __init__(self, pins: Optional[dict[str, int]] = None,
                 active_low: Optional[bool] = None) -> None:
        if pins is None:
            pins = config.GPIO_PINS
        if active_low is None:
            active_low = config.RELAY_ACTIVE_LOW

        self.pins = dict(pins)
        self.active_low = active_low
        self.devices: dict[str, OutputDevice] = {}

        for name, pin in self.pins.items():
            # PA, PB 모듈만 트리거 특성이 반대이므로 active_high 논리를 반전 설정
            is_active_high = self.active_low if name in ("PA", "PB") else not self.active_low
            self.devices[name] = OutputDevice(
                pin,
                active_high=is_active_high,
                initial_value=False
            )

    def set(self, name: str, on: bool) -> None:
        """지정한 릴레이를 켜거나 끈다. name은 'SA', 'PA', 'SB', 'PB' 중 하나."""
        if name not in self.devices:
            raise KeyError(f"알 수 없는 릴레이 이름: {name}")
        if on:
            self.devices[name].on()
        else:
            self.devices[name].off()

    def all_off(self) -> None:
        """모든 릴레이를 끈다."""
        for name in self.devices:
            self.set(name, False)

    def close(self) -> None:
        """모든 릴레이를 끄고 GPIO 핀을 해제한다."""
        self.all_off()
        for dev in self.devices.values():
            dev.close()