"""단계 전환 안전 순서 테스트.

가장 중요한 규칙: 전압 선택 릴레이(S)가 바뀌는 순간, 그 필름의 전원 릴레이(P)는 꺼져 있어야 한다.
모든 단계 → 모든 단계 전환(6 × 6 = 36가지)을 확인한다.
대현의 levels.py가 들어오면 loop.py가 그쪽을 쓰므로 같은 테스트로 검증된다.
"""
import itertools

from pi import config
from pi.control.loop import LevelDriver
from pi.devices.sim import SimRelays

PAIRS = (("SA", "PA"), ("SB", "PB"))


def replay(history):
    """릴레이 기록을 처음부터 다시 따라가며, S가 바뀔 때 P 상태를 검사한다."""
    state = {k: False for k in config.GPIO_PINS}
    for name, on in history:
        for sel, power in PAIRS:
            if name == sel and state[sel] != on:
                assert not state[power], f"{power}가 켜진 채로 {sel} 변경"
        state[name] = on
    return state


def test_safe_order_all_transitions():
    for a, b in itertools.product(range(config.NUM_LEVELS), repeat=2):
        relays = SimRelays()
        drv = LevelDriver(relays, settle_s=0)
        drv.apply(a)
        relays.history.clear()
        drv.apply(b)
        replay(relays.history)


def test_relay_state_matches_level_table():
    for level, films in enumerate(config.LEVELS):
        relays = SimRelays()
        LevelDriver(relays, settle_s=0).apply(level)
        assert relays.film_states() == tuple(films)


def test_starts_all_off():
    relays = SimRelays()
    LevelDriver(relays, settle_s=0)
    assert not any(relays.state.values())
