"""LightQ 웹 대시보드 (Flask).

실행 (저장소 최상위 폴더에서):
  python -m pi.app                 노트북: 가짜 센서·릴레이 + 가상 시계
  python -m pi.app --speed 720     하루를 2분에 재생
  python -m pi.app --speed 720 --start 06:30   가상 시계를 06:30부터 시작 (시연용)
  python -m pi.app --real          Pi 5: 실제 BH1750 + GPIO 릴레이

브라우저: http://localhost:5000  (Pi 핫스팟에서는 http://10.42.0.1:5000, 확인 필요)
"""
import argparse
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from pi import config
from pi.control.loop import Controller
from pi.storage import LogStore


def build_devices(real: bool, speed: float, start: str = None):
    """센서·릴레이·시계·바깥 빛을 만든다. 이 함수만 바꾸면 노트북 ↔ Pi 전환."""
    from pi.sim.clock import VirtualClock
    if real:
        # 대현이 만드는 실제 드라이버. 파일이 아직 없으면 여기서 ImportError.
        from pi.devices.bh1750 import BH1750Sensor
        from pi.devices.relays import GpioRelays
        clock = VirtualClock(datetime.now(), 1.0)   # 실제 장치는 항상 실제 시간
        return BH1750Sensor(), GpioRelays(), clock, None
    from pi.devices.sim import SimRelays, SimSensor
    from pi.sim.outdoor import OutdoorLight
    t0 = datetime.now()
    if start:                                       # 시연: 원하는 시각부터 재생
        h, m = (int(x) for x in start.split(":"))
        t0 = t0.replace(hour=h, minute=m, second=0, microsecond=0)
    clock = VirtualClock(t0, speed)
    outdoor = OutdoorLight(clock.hour)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor)
    return sensor, relays, clock, outdoor


def create_app(ctrl: Controller, store: LogStore) -> Flask:
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

    @app.post("/api/settings")
    def settings():
        try:
            ctrl.set_wake_time(str(body().get("wake_time")))
        except ValueError:
            return jsonify(error="시각 형식은 HH:MM"), 400
        return jsonify(ok=True)

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
    ap.add_argument("--speed", type=float, default=1.0, help="가상 시계 배속 (시뮬레이션)")
    ap.add_argument("--start", default=None, help="가상 시계 시작 시각 HH:MM (시뮬레이션)")
    args = ap.parse_args()

    sensor, relays, clock, outdoor = build_devices(args.real, args.speed, args.start)
    store = LogStore(config.DB_PATH)
    ctrl = Controller(sensor, relays, clock, outdoor, store)
    ctrl.start()
    app = create_app(ctrl, store)
    try:
        # use_reloader=False: 자동 재시작이 켜지면 제어 스레드가 두 개 생겨 릴레이를 동시에 건드린다
        app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    finally:
        ctrl.stop()
        relays.close()
        sensor.close()


if __name__ == "__main__":
    main()
