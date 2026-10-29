"""가짜 장치가 제대로 동작하는지 확인하는 스크립트.

실행: 레포 최상위 폴더에서  python -m pi.tests.try_sim
정오(12시)의 바깥 빛에서 모든 단계를 차례로 적용해 실내 조도를 출력한다.
"""
from datetime import datetime

from pi import config
from pi.devices.sim import SimRelays, SimSensor
from pi.sim.clock import VirtualClock
from pi.sim.outdoor import OutdoorLight


def apply_level_naive(relays: SimRelays, level: int) -> None:
    """임시 단계 적용 (안전 순서 없음). 정식 버전은 대현이의 control/levels.py."""
    a, b = config.LEVELS[level]
    for film, (sel, power) in ((a, ("SA", "PA")), (b, ("SB", "PB"))):
        relays.set(sel, film == "high")
        relays.set(power, film != "off")


def main() -> None:
    clock = VirtualClock(datetime(2026, 10, 24, 12, 0), speed=0)  # 정오에 고정
    outdoor = OutdoorLight(clock.hour, seed=1)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor, seed=1)
    print(f"가상 시각 {clock.now():%H:%M}, 바깥 빛 약 {outdoor():.0f} lux")
    for level in range(config.NUM_LEVELS):
        apply_level_naive(relays, level)
        print(f"{level}단계 {relays.film_states()} -> 실내 {sensor.read_lux()} lux")


if __name__ == "__main__":
    main()
