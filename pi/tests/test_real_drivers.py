"""실제 드라이버 테스트 (대현 작업 파일이 생기면 자동으로 돈다).

pi/devices/relays.py 가 없으면 건너뛴다. gpiozero의 가짜 핀(MockFactory)을 써서
Pi 없이 노트북에서도 돈다:  pip install gpiozero  후  python -m pytest pi/tests -q
"""
import importlib.util

import pytest

from pi import config

has_relays = importlib.util.find_spec("pi.devices.relays") is not None
has_gpiozero = importlib.util.find_spec("gpiozero") is not None
pytestmark = pytest.mark.skipif(not (has_relays and has_gpiozero),
                                reason="pi/devices/relays.py 또는 gpiozero 없음")


@pytest.fixture()
def relays():
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory
    Device.pin_factory = MockFactory()
    from pi.devices.relays import GpioRelays
    r = GpioRelays()
    yield r
    r.close()
    Device.pin_factory.reset()


def pin(name):
    from gpiozero import Device
    return int(Device.pin_factory.pin(config.GPIO_PINS[name]).state)


def on_level():
    """릴레이를 '켬'으로 했을 때 핀 전압. 저레벨 트리거면 0."""
    return 0 if config.RELAY_ACTIVE_LOW else 1


def test_starts_all_off(relays):
    for n in config.GPIO_PINS:
        assert pin(n) == 1 - on_level(), f"{n}이 시작부터 켜져 있음"


def test_set_each(relays):
    for n in config.GPIO_PINS:
        relays.set(n, True)
        assert pin(n) == on_level()
        others = [m for m in config.GPIO_PINS if m != n]
        assert all(pin(m) == 1 - on_level() for m in others), f"{n}을 켰는데 다른 핀이 바뀜"
        relays.set(n, False)
        assert pin(n) == 1 - on_level()


def test_all_off(relays):
    for n in config.GPIO_PINS:
        relays.set(n, True)
    relays.all_off()
    assert all(pin(n) == 1 - on_level() for n in config.GPIO_PINS)


def test_unknown_name_rejected(relays):
    with pytest.raises((KeyError, ValueError)):
        relays.set("XX", True)


def test_safe_order_with_real_driver(relays):
    """실제 드라이버 + 단계 전환기로 0 → 5 → 0 전환 후 모두 꺼짐."""
    from pi.control.loop import LevelDriver
    drv = LevelDriver(relays, settle_s=0)
    for lv in list(range(config.NUM_LEVELS)) + [0]:
        drv.apply(lv)
    assert all(pin(n) == 1 - on_level() for n in config.GPIO_PINS)
