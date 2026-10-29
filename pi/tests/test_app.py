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
    ctrl.set_manual(config.NUM_LEVELS - 1)
    sensor.read_lux = lambda: None     # 센서 고장 흉내
    for _ in range(config.SENSOR_FAIL_LIMIT):
        ctrl.step()
    assert ctrl.level == config.SAFE_LEVEL
    assert not any(relays.state.values())      # 모든 릴레이 꺼짐


def test_time_sync(tmp_path):
    """휴대폰 시각과 30초 넘게 차이 나면 맞추고, 시각을 정한 시연 모드에서는 맞추지 않는다."""
    from datetime import timedelta
    sensor, relays, clock, outdoor = build_devices(False, 1, None)
    ctrl = Controller(sensor, relays, clock, outdoor, None)
    phone = clock.now() + timedelta(hours=3)
    local = phone.strftime("%Y-%m-%dT%H:%M:%S")

    off = create_app(ctrl, None).test_client()
    assert off.post("/api/time", json={"local": local}).get_json()["adjusted"] is False

    c = create_app(ctrl, None, time_sync=True).test_client()
    assert c.post("/api/time", json={"local": "x"}).status_code == 400
    assert c.post("/api/time", json={"local": local}).get_json()["adjusted"] is True
    assert abs((clock.now() - phone).total_seconds()) < 5
    assert c.post("/api/time", json={"local": local}).get_json()["adjusted"] is False   # 이미 맞음


def test_log_is_batched_and_pruned(tmp_path):
    import sqlite3
    import time as _time
    path = str(tmp_path / "b.db")
    store = LogStore(path, commit_s=3600, keep_days=1)
    store.add("12:00:00", 12.0, 100, 500, 2, "rule")
    count = lambda: sqlite3.connect(path).execute("SELECT COUNT(*) FROM log").fetchone()[0]
    assert count() == 0                                   # 아직 메모리에만
    store.add("12:00:01", 12.0, 100, 500, 3, "rule", "rule 2->3")
    assert count() == 2                                   # 이벤트는 바로 저장
    store.add("12:00:02", 12.0, 100, 500, 3, "rule")
    assert len(store.export_csv().splitlines()) == 4      # 내보내기 전에 저장
    store.conn.execute("UPDATE log SET ts = ? WHERE vtime = '12:00:00'", (_time.time() - 3 * 86400,))
    store.last_prune = 0
    store.close()
    assert count() == 2                                   # 하루 지난 기록은 지움


def test_ai_page_and_explain(client):
    assert client.get("/ai").status_code == 200
    assert 'href="/ai"' in client.get("/").get_data(as_text=True)     # 대시보드에서 가는 링크
    e = client.get("/api/ai/explain").get_json()
    for k in ("mode", "brain", "level", "answers", "rule", "stab"):
        assert k in e
    assert e["stab"]["need"] >= 1


def test_ai_report(client, monkeypatch, tmp_path):
    import json
    import os
    from pi import config
    if os.path.exists(config.AI_REPORT_PATH):
        r = client.get("/api/ai/report").get_json()
        assert r["levels"] == config.NUM_LEVELS
        assert any(m.get("current") for m in r["models"])
        assert {"depth", "ablation", "importance", "horizon", "horizon_rule"} <= set(r)
    monkeypatch.setattr(config, "AI_REPORT_PATH", str(tmp_path / "none.json"))
    assert client.get("/api/ai/report").status_code == 404
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"levels": 3}), encoding="utf-8")
    monkeypatch.setattr(config, "AI_REPORT_PATH", str(p))
    assert client.get("/api/ai/report").get_json() == {"levels": 3}
