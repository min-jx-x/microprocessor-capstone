"""단계 전환 안전 순서 테스트.

가장 중요한 규칙: 전압 선택 릴레이(S)가 바뀌는 순간, 그 필름의 전원 릴레이(P)는 꺼져 있어야 한다.
모든 단계 → 모든 단계 전환(3단계 3 × 3 = 9가지, 6단계 6 × 6 = 36가지)을 확인한다.
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


def test_apply_combo_ignores_level_order(monkeypatch):
    """실측 후 단계 순서(config.LEVELS)가 바뀌어도 조합으로 켜면 그 조합이 켜져야 한다 (캘리브레이션)."""
    monkeypatch.setattr(config, "LEVELS", list(reversed(config.LEVELS)))
    relays = SimRelays()
    drv = LevelDriver(relays, settle_s=0)
    for combo in [("low", "low"), ("high", "off"), ("off", "off"), ("high", "high")]:
        drv.apply_combo(*combo)
        assert relays.film_states() == combo
    replay(relays.history)
    drv.apply(0)                       # 조합으로 켠 뒤에도 단계 전환이 동작해야 함
    assert relays.film_states() == tuple(config.LEVELS[0])


def test_calibrate_measures_each_combo_even_if_levels_reordered(tmp_path, monkeypatch):
    """lut.json이 이미 있어 단계 순서가 바뀐 상태에서 다시 재도 조합별 조도가 맞게 저장되어야 한다."""
    import json
    from pi.devices.sim import combo_transmittance
    from pi.tools import calibrate

    monkeypatch.setattr(config, "LEVELS", list(reversed(config.LEVELS)))
    monkeypatch.setattr(config, "CALIBRATION", None)          # 시뮬레이터는 가정 투과율 사용
    out = tmp_path / "lut.json"
    calibrate.run_calibration(sim=True, settle_s=0, samples=3, lamp_step=7, out_path=str(out))
    d = json.loads(out.read_text(encoding="utf-8"))
    assert 4 <= d["ambient_lux"] <= 6                         # 시뮬레이터 잡광 5 lux
    for (a, b), lux in zip(d["combos"], d["lux"]):
        expected = 1000 * combo_transmittance(a, b) + 5
        assert abs(lux - expected) <= expected * 0.02, (a, b, lux, expected)
    assert d["lux"] == sorted(d["lux"]) and d["ratio"][-1] == 1.0
