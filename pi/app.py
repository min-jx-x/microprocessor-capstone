"""LightQ 웹 대시보드 (Flask).

실행 (저장소 최상위 폴더에서):
  python -m pi.app                 노트북: 가짜 센서·릴레이 + 가상 시계
  python -m pi.app --speed 720     하루를 2분에 재생
  python -m pi.app --speed 720 --start 06:30   가상 시계를 06:30부터 시작 (시연용)
  python -m pi.app --real          Pi 5: 실제 BH1750 + GPIO 릴레이
  python -m pi.app --real --start 11:00 --speed 0   실물 시연: 시각을 11:00(주간)에 고정

브라우저: http://localhost:5000  (Pi 핫스팟에서는 http://10.42.0.1:5000, 확인 필요)
"""
import argparse
import signal
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from pi import config
from pi.control.loop import Controller
from pi.control.preference import PreferenceStore
from pi.storage import LogStore


def start_time(start: str = None) -> datetime:
    """가상 시계 시작 시각. 없으면 지금, "06:30"이면 오늘 06:30."""
    t0 = datetime.now()
    if start:
        h, m = (int(x) for x in start.split(":"))
        t0 = t0.replace(hour=h, minute=m, second=0, microsecond=0)
    return t0


def build_devices(real: bool, speed: float, start: str = None):
    """센서·릴레이·시계·바깥 빛을 만든다. 이 함수만 바꾸면 노트북 ↔ Pi 전환."""
    from pi.sim.clock import VirtualClock
    if real:
        # 대현이 만드는 실제 드라이버
        try:
            from pi.devices.bh1750 import BH1750Sensor
            from pi.devices.relays import GpioRelays
        except ImportError as e:
            raise SystemExit(f"--real 에 필요한 드라이버를 불러올 수 없음 "
                             f"(pi/devices/bh1750.py, relays.py): {e}")
        # 실물은 바깥 빛이 진짜(LED 스탠드)라 시간만 다룬다. 시연 때는 시각을 고정(speed 0)해
        # 언제 시연해도 '주간' 판단이 나오게 할 수 있다.
        return BH1750Sensor(), GpioRelays(), VirtualClock(start_time(start), speed), None
    from pi.devices.sim import SimRelays, SimSensor
    from pi.sim.outdoor import OutdoorLight
    clock = VirtualClock(start_time(start), speed)
    outdoor = OutdoorLight(clock.hour)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor)
    return sensor, relays, clock, outdoor


def create_app(ctrl: Controller, store: LogStore, time_sync: bool = False) -> Flask:
    """time_sync: 휴대폰 시각으로 시계를 맞출지. --start/--speed로 시각을 정한 시연·시뮬레이션에서는 끈다."""
    app = Flask(__name__)
    app.json.ensure_ascii = False       # 한글 오류 메시지를 그대로 보이게

    def body() -> dict:
        return request.get_json(silent=True) or {}

    @app.get("/")
    def index():
        return render_template("index.html", num_levels=config.NUM_LEVELS)

    @app.get("/api/state")
    def state():
        return jsonify(ctrl.snapshot())

    @app.post("/api/level")
    def level():
        try:
            ctrl.set_manual(int(body().get("level")))
        except (TypeError, ValueError) as e:
            return jsonify(error=str(e)), 400
        return jsonify(ok=True)

    @app.post("/api/mode")
    def mode():
        try:
            ctrl.set_mode(str(body().get("mode")))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        return jsonify(ok=True)

    @app.post("/api/brain")
    def brain():
        try:
            ctrl.set_brain(str(body().get("brain")))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        return jsonify(ok=True)

    @app.post("/api/pref/profile")
    def pref_profile():
        try:
            ctrl.set_profile(str(body().get("name", "")))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        return jsonify(ok=True)

    @app.post("/api/pref/learn")
    def pref_learn():
        value = body().get("enabled")
        if not isinstance(value, bool):
            return jsonify(error="enabled는 true 또는 false"), 400
        ctrl.set_learning(value)
        return jsonify(ok=True)

    @app.post("/api/pref/reset")
    def pref_reset():
        ctrl.reset_preference()
        return jsonify(ok=True)

    @app.post("/api/settings")
    def settings():
        try:
            ctrl.set_wake_time(str(body().get("wake_time")))
        except ValueError:
            return jsonify(error="시각 형식은 HH:MM"), 400
        return jsonify(ok=True)

    @app.post("/api/time")
    def sync_time():
        """휴대폰 브라우저의 현지 시각("2026-10-28T16:47:52")으로 시계를 맞춘다."""
        try:
            phone = datetime.fromisoformat(str(body().get("local")))
        except ValueError:
            return jsonify(error="시각 형식은 YYYY-MM-DDTHH:MM:SS"), 400
        diff = (phone - ctrl.clock.now()).total_seconds()
        adjusted = time_sync and abs(diff) > config.TIME_SYNC_MIN_DIFF_S
        if adjusted:
            ctrl.clock.set_now(phone)
            print(f"[time] 휴대폰 시각으로 맞춤: {phone:%Y-%m-%d %H:%M:%S} (차이 {diff:+.0f}초)")
        return jsonify(ok=True, adjusted=adjusted, diff_s=round(diff))

    # ---- 시뮬레이션 전용 (실제 장치에서는 400) ----
    @app.post("/api/sim/speed")
    def sim_speed():
        if ctrl.outdoor is None:
            return jsonify(error="시뮬레이션 모드에서만 가능"), 400
        try:
            speed = float(body().get("speed"))
        except (TypeError, ValueError):
            return jsonify(error="speed는 숫자"), 400
        if not 0 < speed <= 3600:
            return jsonify(error="speed 범위 0~3600"), 400
        ctrl.clock.set_speed(speed)
        return jsonify(ok=True)

    @app.post("/api/sim/burst")
    def sim_burst():
        if ctrl.outdoor is None:
            return jsonify(error="시뮬레이션 모드에서만 가능"), 400
        ctrl.outdoor.trigger_burst()
        return jsonify(ok=True)

    @app.get("/api/export.csv")
    def export_csv():
        return Response(store.export_csv(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=lightq_log.csv"})

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="LightQ 웹 대시보드")
    ap.add_argument("--real", action="store_true", help="실제 센서·릴레이 사용 (Pi 5)")
    ap.add_argument("--host", default=config.WEB_HOST)
    ap.add_argument("--port", type=int, default=config.WEB_PORT)
    ap.add_argument("--speed", type=float, default=1.0, help="가상 시계 배속. 0이면 시각 고정")
    ap.add_argument("--start", default=None, help="가상 시계 시작 시각 HH:MM")
    args = ap.parse_args()

    # systemd가 서버를 끌 때(SIGTERM)도 Ctrl+C와 똑같이 처리해서 아래 finally에서 릴레이를 모두 끈다
    def _stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _stop)

    sensor, relays, clock, outdoor = build_devices(args.real, args.speed, args.start)
    store = LogStore(config.DB_PATH)
    ctrl = Controller(sensor, relays, clock, outdoor, store, PreferenceStore())
    ctrl.start()
    # 실제 시각을 따라가는 경우에만 휴대폰 시각으로 맞춘다 (시각 고정·배속 시연은 그대로 둠)
    app = create_app(ctrl, store, time_sync=args.start is None and args.speed == 1)
    try:
        # use_reloader=False: 자동 재시작이 켜지면 제어 스레드가 두 개 생겨 릴레이를 동시에 건드린다
        app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    finally:
        ctrl.stop()
        relays.close()
        sensor.close()
        store.close()


if __name__ == "__main__":
    main()
