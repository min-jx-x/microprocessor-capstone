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


def test_app_page_and_routes(client):
    r = client.get("/app")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for part in ("voice-rec.js", "mobile.js", "mobile.css", 'href="#home"', 'href="#voice"', 'href="#settings"', "/?full=1"):
        assert part in html
    r = client.get("/voice")                                 # 예전 음성 화면 주소는 앱 음성 탭으로
    assert r.status_code == 302 and r.headers["Location"].endswith("/app#voice")
    assert 'location.replace("/")' in html                  # 노트북으로 열면 대시보드로
    dash = client.get("/").get_data(as_text=True)
    assert 'location.replace("/app#home")' in dash          # 휴대폰이면 앱 화면으로
    # 음성 명령과 앱은 휴대폰에서만: 대시보드에는 음성 카드·음성/앱 버튼이 없다 ('음성도 학습' 설정만 남음)
    assert 'id="voice-card"' not in dash and 'id="mic"' not in dash
    assert 'href="/voice"' not in dash and 'href="/app"' not in dash
    assert 'id="voice-learn"' in dash
    assert client.get("/favicon.ico").status_code == 204


def _lock_client(tmp_path, lock):
    sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
    store = LogStore(str(tmp_path / "lock.db"))
    ctrl = Controller(sensor, relays, clock, outdoor, store)
    ctrl.step()
    return create_app(ctrl, store, demo_lock=lock).test_client()


LOCKED_CALLS = [
    ("/api/pref/profile", {"name": "관람객"}),
    ("/api/pref/learn", {"enabled": False}),
    ("/api/pref/reset", {}),
    ("/api/voice/learn", {"enabled": True}),
]


def test_demo_lock_on(tmp_path):
    c = _lock_client(tmp_path, True)
    assert c.get("/api/state").get_json()["demo_lock"] is True
    for url, data in LOCKED_CALLS:
        r = c.post(url, json=data)
        assert r.status_code == 403, url
        assert r.get_json()["error"] == "시연 중에는 잠겨 있어요"
    st = c.get("/api/state").get_json()
    assert "관람객" not in st["pref"]["profiles"]           # 실제로 바뀌지 않음
    # 기상 시간과 단계·자동 전환은 잠그지 않는다
    assert c.post("/api/settings", json={"wake_time": "06:45"}).status_code == 200
    assert c.post("/api/level", json={"level": 1}).status_code == 200
    assert c.post("/api/mode", json={"mode": "auto"}).status_code == 200
    assert c.get("/api/state").get_json()["wake_time"] == "06:45"


def test_demo_lock_off(tmp_path, monkeypatch):
    monkeypatch.delenv("LIGHTQ_DEMO_LOCK", raising=False)
    c = _lock_client(tmp_path, None)                        # 환경변수가 없으면 꺼짐
    assert c.get("/api/state").get_json()["demo_lock"] is False
    for url, data in LOCKED_CALLS:
        assert c.post(url, json=data).status_code == 200, url
    assert "관람객" in c.get("/api/state").get_json()["pref"]["profiles"]


def test_demo_lock_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTQ_DEMO_LOCK", "1")
    c = _lock_client(tmp_path, None)
    assert c.get("/api/state").get_json()["demo_lock"] is True
    assert c.post("/api/pref/reset", json={}).status_code == 403


def test_voice_device_auto_name():
    from pi.app import DeviceNames, device_kind
    iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
    galaxy = "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 SamsungBrowser/25.0 Chrome/121 Mobile Safari/537.36"
    assert device_kind(iphone) == "아이폰"
    assert device_kind(galaxy) == "갤럭시"
    assert device_kind("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130") == "노트북"
    names = DeviceNames()
    assert names.name("10.42.0.5", iphone) == "아이폰 1"
    assert names.name("10.42.0.6", galaxy) == "갤럭시 2"
    assert names.name("10.42.0.5", iphone) == "아이폰 1"    # 같은 폰은 같은 번호


def test_voice_command_gets_device_name(client):
    ua = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Mobile/15E148 Safari/604.1"}
    d = client.post("/api/voice", json={"text": "2단계로 바꿔 줘"}, headers=ua).get_json()
    assert d["device"] == "아이폰 1"
    d = client.post("/api/voice", json={"text": "2단계로", "device": "노트북"}).get_json()
    assert d["device"] == "노트북"                           # 직접 준 이름은 그대로
