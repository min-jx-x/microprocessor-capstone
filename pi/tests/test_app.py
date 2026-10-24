"""웹 API 테스트 (Flask 테스트 클라이언트, 서버를 띄우지 않음)."""
import pytest

from pi.app import build_devices, create_app
from pi.control.loop import Controller
from pi.storage import LogStore


@pytest.fixture()
def client(tmp_path):
    sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
    store = LogStore(str(tmp_path / "t.db"))
    ctrl = Controller(sensor, relays, clock, outdoor, store)
    for _ in range(5):
        ctrl.step()                    # 스레드 없이 직접 몇 번 돌림
    return create_app(ctrl, store).test_client()


def test_state(client):
    d = client.get("/api/state").get_json()
    assert d["sim"] and d["lux"] is not None and len(d["history"]) == 5


def test_manual_level(client):
    assert client.post("/api/level", json={"level": 2}).status_code == 200
    d = client.get("/api/state").get_json()
    assert d["mode"] == "manual" and d["level"] == 2
    assert client.post("/api/level", json={"level": 9}).status_code == 400


def test_bad_inputs(client):
    assert client.post("/api/settings", json={"wake_time": "25:00"}).status_code == 400
    assert client.post("/api/mode", json={"mode": "x"}).status_code == 400
    assert client.post("/api/brain", json={"brain": "x"}).status_code == 400


def test_csv_export(client):
    text = client.get("/api/export.csv").get_data(as_text=True)
    assert text.splitlines()[0] == "ms,hour,lux,level"


def test_sensor_failure_goes_safe(tmp_path):
    from pi import config
    sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
    ctrl = Controller(sensor, relays, clock, outdoor, None)
    ctrl.set_manual(4)
    sensor.read_lux = lambda: None     # 센서 고장 흉내
    for _ in range(config.SENSOR_FAIL_LIMIT):
        ctrl.step()
    assert ctrl.level == config.SAFE_LEVEL
    assert not any(relays.state.values())      # 모든 릴레이 꺼짐
