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
import json
import os
import signal
import threading
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from pi import config
from pi.control.loop import Controller
from pi.control.preference import PreferenceStore
from pi.storage import LogStore
from pi.voice.handler import VoiceHandler
from pi.voice.intent import load_model
from pi.voice.llm import GeminiFallback
from pi.voice.stt import WhisperSTT, is_wav


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


def save_audio(data: bytes) -> None:
    """정확도 확인용으로 최근 녹음 config.VOICE_AUDIO_KEEP개만 남긴다 (기본 0 = 저장 안 함)."""
    if config.VOICE_AUDIO_KEEP <= 0:
        return
    os.makedirs(config.VOICE_AUDIO_DIR, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".wav"
    with open(os.path.join(config.VOICE_AUDIO_DIR, name), "wb") as f:
        f.write(data)
    files = sorted(os.listdir(config.VOICE_AUDIO_DIR))
    for old in files[:-config.VOICE_AUDIO_KEEP]:
        try:
            os.remove(os.path.join(config.VOICE_AUDIO_DIR, old))
        except OSError:
            pass


def create_app(ctrl: Controller, store: LogStore, time_sync: bool = False,
               voice: VoiceHandler = None, stt: WhisperSTT = None) -> Flask:
    """time_sync: 휴대폰 시각으로 시계를 맞출지. --start/--speed로 시각을 정한 시연·시뮬레이션에서는 끈다.
    voice: 문장 명령 처리기. 없으면 기본(의도 분류기 + 키가 있으면 Gemini)으로 만든다.
    stt: 음성 → 글자 (whisper.cpp 서버). 없으면 기본 주소로 만든다. 서버가 꺼져 있으면 마이크 녹음만 안 된다."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.VOICE_AUDIO_MAX_BYTES + 64 * 1024
    if voice is None:
        voice = VoiceHandler(ctrl, load_model(), GeminiFallback())
    if stt is None:
        stt = WhisperSTT()

    def voice_status() -> dict:
        return dict(voice.status(), stt=stt.available(), stt_error=stt.last_error, https_port=config.WEB_HTTPS_PORT
                    if os.path.exists(config.TLS_CERT) else None)
    app.json.ensure_ascii = False       # 한글 오류 메시지를 그대로 보이게

    def body() -> dict:
        return request.get_json(silent=True) or {}

    @app.get("/")
    def index():
        return render_template("index.html", num_levels=config.NUM_LEVELS)

    @app.get("/ai")
    def ai_page():
        return render_template("ai.html")

    @app.get("/api/state")
    def state():
        # 음성 명령 기록도 같이 보내서, 다른 기기에서 보낸 명령도 모든 화면에 보이게 한다
        return jsonify(dict(ctrl.snapshot(), voice={"recent": voice.recent()[:8], "status": voice_status()}))

    # ---- 음성(문장) 명령 ----
    @app.post("/api/voice")
    def voice_command():
        """{"text": "너무 밝아", "device": "폰1"} → 의도 판단 후 단계 변경. 응답에 처리 경로(model/llm/none) 포함."""
        b = body()
        try:
            return jsonify(voice.handle(b.get("text", ""), b.get("device", "")))
        except ValueError as e:
            return jsonify(error=str(e)), 400

    @app.post("/api/voice/audio")
    def voice_audio():
        """웹에서 녹음한 WAV(16kHz 모노) → whisper.cpp로 글자 → 문장 명령과 같은 처리."""
        f = request.files.get("audio")
        if f is None:
            return jsonify(error="audio 파일이 없음"), 400
        data = f.read(config.VOICE_AUDIO_MAX_BYTES + 1)
        if len(data) > config.VOICE_AUDIO_MAX_BYTES:
            return jsonify(error="녹음이 너무 김"), 413
        if not is_wav(data):
            return jsonify(error="WAV 형식이 아님"), 400
        text = stt.transcribe(data)
        if text is None:
            return jsonify(error=stt.last_error or "음성 인식 실패"), 503
        save_audio(data)
        if not text:
            return jsonify(text="", heard="", applied=False, source="none", action="none",
                           reply="잘 안 들렸어요. 다시 말해 주세요", stt_ms=stt.last_ms)
        result = voice.handle(text, request.form.get("device", ""))
        return jsonify(dict(result, heard=text, stt_ms=stt.last_ms))

    @app.get("/api/voice")
    def voice_info():
        return jsonify(status=voice_status(), recent=voice.recent())

    @app.post("/api/voice/learn")
    def voice_learn():
        value = body().get("enabled")
        if not isinstance(value, bool):
            return jsonify(error="enabled는 true 또는 false"), 400
        voice.set_learning(value)
        return jsonify(ok=True)

    # ---- AI 설명 페이지 ----
    @app.get("/api/ai/explain")
    def ai_explain():
        return jsonify(ctrl.explain())

    @app.get("/api/ai/report")
    def ai_report():
        """모델 선택 근거 실험 결과. 노트북에서 python -m pi.ai.compare_models로 만든 파일을 그대로 보낸다."""
        if not os.path.exists(config.AI_REPORT_PATH):
            return jsonify(error="실험 결과 파일 없음 (python -m pi.ai.compare_models)"), 404
        with open(config.AI_REPORT_PATH, encoding="utf-8") as f:
            return jsonify(json.load(f))

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
    ap.add_argument("--no-learn", action="store_true", help="수동 조절 학습을 끈 채로 시작 (시연용, 재부팅해도 유지)")
    args = ap.parse_args()

    # systemd가 서버를 끌 때(SIGTERM)도 Ctrl+C와 똑같이 처리해서 아래 finally에서 릴레이를 모두 끈다
    def _stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _stop)

    sensor, relays, clock, outdoor = build_devices(args.real, args.speed, args.start)
    store = LogStore(config.DB_PATH)
    ctrl = Controller(sensor, relays, clock, outdoor, store, PreferenceStore())
    if args.no_learn:
        ctrl.set_learning(False)
    ctrl.start()
    # 실제 시각을 따라가는 경우에만 휴대폰 시각으로 맞춘다 (시각 고정·배속 시연은 그대로 둠)
    app = create_app(ctrl, store, time_sync=args.start is None and args.speed == 1)
    https = None
    if os.path.exists(config.TLS_CERT) and os.path.exists(config.TLS_KEY):
        # 휴대폰 브라우저는 HTTPS에서만 마이크를 허용한다. HTTP(5000)는 그대로 두고 HTTPS를 하나 더 연다
        from werkzeug.serving import make_server
        https = make_server(args.host, config.WEB_HTTPS_PORT, app, threaded=True,
                            ssl_context=(config.TLS_CERT, config.TLS_KEY))
        threading.Thread(target=https.serve_forever, daemon=True).start()
        print(f"[web] HTTPS https://{args.host}:{config.WEB_HTTPS_PORT} (자체 서명 인증서)")
    try:
        # use_reloader=False: 자동 재시작이 켜지면 제어 스레드가 두 개 생겨 릴레이를 동시에 건드린다
        app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    finally:
        if https is not None:
            https.shutdown()
        ctrl.stop()
        relays.close()
        sensor.close()
        store.close()


if __name__ == "__main__":
    main()
