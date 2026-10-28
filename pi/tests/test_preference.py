"""개인 선호 보정 테스트."""
import pytest

from pi import config
from pi.app import build_devices, create_app
from pi.control.decide import decide_rule
from pi.control.loop import Controller
from pi.control.preference import PreferenceStore
from pi.storage import LogStore


def test_learn_moves_partially_and_clamps():
    p = PreferenceStore(path=None, alpha=0.3, max_offset=0.3)
    assert p.learn("day", 500, 600) == pytest.approx(0.06)        # 차이 20%의 30%
    for _ in range(30):
        p.learn("day", 500, 2000)                                 # 아무리 밝게 해도
    assert p.snapshot()["offset"]["day"] == pytest.approx(0.3, abs=1e-3)   # +30% 근처에서 멈춤
    assert p.scale()["day"] <= 1.3


def test_ramp_shares_morning_and_night_ignored():
    p = PreferenceStore(path=None)
    p.learn("ramp", 100, 130)
    assert p.snapshot()["offset"]["morning"] > 0
    assert p.learn("evening", None, 100) is None
    assert p.learn("sleep", None, 100) is None


def test_profiles_are_separate_and_saved(tmp_path):
    path = str(tmp_path / "pref.json")
    p = PreferenceStore(path=path)
    p.select("민재")
    p.learn("day", 500, 650)
    p.select("대현")
    assert p.snapshot()["offset"]["day"] == 0.0                   # 다른 사용자는 영향 없음
    p.learn("day", 500, 400)
    again = PreferenceStore(path=path)                            # 껐다 켠 것처럼 다시 읽기
    assert again.active == "대현"
    again.select("민재")
    assert again.snapshot()["offset"]["day"] > 0
    with pytest.raises(ValueError):
        again.select("   ")


def test_scale_changes_target():
    _, info = decide_rule(500, 12.0, 3, list(config.LUT_T), 7.5, {"day": 1.2})
    assert info["target"] == pytest.approx(config.TARGET_DAY_LUX * 1.2)
    assert info["base_target"] == config.TARGET_DAY_LUX


def test_controller_learns_from_manual(tmp_path):
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")   # 12:00 고정 = 주간
    ctrl = Controller(sensor, relays, clock, outdoor, None, PreferenceStore(path=None))
    for _ in range(6):
        ctrl.step()
    ctrl.set_manual(5)                                            # 가장 밝게 → 목표보다 밝음
    for _ in range(config.PREF_SETTLE):
        ctrl.step()
    v = ctrl.snapshot()["pref"]
    assert v["count"]["day"] == 1 and v["offset"]["day"] > 0
    assert v["targets"]["day"][1] > config.TARGET_DAY_LUX


def test_back_to_auto_before_settle_does_not_learn():
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")
    ctrl = Controller(sensor, relays, clock, outdoor, None, PreferenceStore(path=None))
    ctrl.step()
    ctrl.set_manual(5)
    ctrl.step()
    ctrl.set_mode("auto")
    for _ in range(5):
        ctrl.step()
    assert ctrl.snapshot()["pref"]["count"]["day"] == 0


def test_pref_api(tmp_path):
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")
    store = LogStore(str(tmp_path / "t.db"))
    ctrl = Controller(sensor, relays, clock, outdoor, store, PreferenceStore(path=None))
    c = create_app(ctrl, store).test_client()
    assert c.post("/api/pref/profile", json={"name": "재우"}).status_code == 200
    assert c.get("/api/state").get_json()["pref"]["active"] == "재우"
    assert c.post("/api/pref/profile", json={"name": ""}).status_code == 400
    assert c.post("/api/pref/reset").status_code == 200


def test_learning_can_be_turned_off(tmp_path):
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")
    store = LogStore(str(tmp_path / "t.db"))
    ctrl = Controller(sensor, relays, clock, outdoor, store, PreferenceStore(path=None))
    c = create_app(ctrl, store).test_client()
    assert c.post("/api/pref/learn", json={"enabled": False}).status_code == 200
    assert c.post("/api/pref/learn", json={"enabled": "no"}).status_code == 400
    ctrl.step()
    ctrl.set_manual(5)
    for _ in range(config.PREF_SETTLE + 1):
        ctrl.step()
    v = ctrl.snapshot()["pref"]
    assert v["learn"] is False and v["count"]["day"] == 0
