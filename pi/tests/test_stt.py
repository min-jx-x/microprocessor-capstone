"""음성 → 글자(whisper.cpp 서버) 연결 테스트. 실제 whisper 없이 가짜 서버로 확인한다."""
import io
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pi import config
from pi.app import build_devices, create_app
from pi.control.loop import Controller
from pi.storage import LogStore
from pi.voice.handler import VoiceHandler
from pi.voice.intent import IntentModel
from pi.voice.stt import WhisperSTT, clean_text, is_prompt_echo, is_wav, speech_text


def make_wav(seconds=1.0, rate=16000) -> bytes:
    n = int(seconds * rate)
    data = struct.pack(f"<{n}h", *([1000, -1000] * (n // 2)))
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return hdr + b"data" + struct.pack("<I", len(data)) + data


class FakeWhisper(BaseHTTPRequestHandler):
    reply = {"text": " 너무 밝아 [음악]"}
    seen = {}

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeWhisper.seen = {"ctype": self.headers["Content-Type"], "body": body}
        out = json.dumps(FakeWhisper.reply).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture()
def whisper_url():
    srv = HTTPServer(("127.0.0.1", 0), FakeWhisper)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/inference"
    srv.shutdown()


def test_wav_check_and_cleanup():
    assert is_wav(make_wav()) and not is_wav(b"not a wav file at all" * 5)
    assert clean_text(" 2단계로 (박수) [음악] 해 줘 ") == "2단계로 해 줘"


def test_transcribe_sends_korean_request(whisper_url):
    stt = WhisperSTT(whisper_url)
    assert stt.available()
    assert stt.transcribe(make_wav()) == "너무 밝아"
    body = FakeWhisper.seen["body"]
    assert b'name="language"\r\n\r\nko' in body and b'name="file"; filename="voice.wav"' in body
    assert FakeWhisper.seen["ctype"].startswith("multipart/form-data; boundary=")


PROMPT = ("라이트큐 창문 밝기 명령. 눈부셔. 너무 밝아. 좀 어둡게 해 줘. 좀 밝게 해 줘. 너무 어두워. "
          "0단계로 바꿔 줘. 자동으로 해 줘. 지금 몇 단계야.")


@pytest.mark.parametrize("text,echo", [
    ("라이트큐 창문 밝기 명령.", True),                       # 제목 문장: 사용자가 할 말이 아님
    ("라이트큐 창문 밝기 명령 눈부셔", True),
    ("눈부셔. 너무 밝아. 좀 어둡게 해 줘.", True),            # 연속 3문장 순서 그대로
    ("너무밝아 좀어둡게해줘 좀 밝게 해 줘 너무 어두워", True),  # 띄어쓰기·문장부호가 달라도
    (PROMPT, True),
    ("눈부셔 너무 밝아", False),                              # 두 문장만 이은 건 실제 말일 수 있음
    ("눈부셔", False),
    ("2단계로 바꿔 줘", False),
    ("너무 밝아. 눈부셔. 좀 어둡게 해 줘.", False),           # 순서가 다르면 지어낸 것으로 보지 않음
    ("", False),
])
def test_prompt_echo_rule(monkeypatch, text, echo):
    monkeypatch.setattr(config, "VOICE_STT_PROMPT", PROMPT)
    assert is_prompt_echo(text) is echo


@pytest.mark.parametrize("heard,expected", [
    (" 라이트큐 창문 밝기 명령. 눈부셔. 너무 밝아.", ""),        # 잡음 → 프롬프트를 읊음 → 버림
    (" 눈부셔. 너무 밝아. 좀 어둡게 해 줘. 좀 밝게 해 줘.", ""),
    (" 눈부셔 너무 밝아", "눈부셔 너무 밝아"),
    (" 눈부셔", "눈부셔"),
])
def test_transcribe_drops_prompt_echo(monkeypatch, whisper_url, heard, expected):
    monkeypatch.setattr(config, "VOICE_STT_PROMPT", PROMPT)
    monkeypatch.setattr(FakeWhisper, "reply", {"text": heard})
    stt = WhisperSTT(whisper_url)
    assert stt.transcribe(make_wav()) == expected and stt.last_error is None


def seg(text, no_speech=0.05, logprob=-0.3):
    """whisper-server verbose_json의 segments 한 개 (필요한 필드만)."""
    s = {"id": 0, "text": text}
    if no_speech is not None:
        s["no_speech_prob"] = no_speech
    if logprob is not None:
        s["avg_logprob"] = logprob
    return s


def verbose(*segs):
    return {"task": "transcribe", "language": "korean", "duration": 1.0,
            "text": "".join(s["text"] for s in segs), "segments": list(segs)}


def test_request_asks_verbose_json(whisper_url):
    WhisperSTT(whisper_url).transcribe(make_wav())
    body = FakeWhisper.seen["body"]
    assert b'name="response_format"\r\n\r\nverbose_json' in body
    assert b'name="no_language_probabilities"\r\n\r\ntrue' in body


def test_verbose_json_keeps_speech_drops_noise():
    text, info = speech_text(verbose(seg(" 눈부셔"), seg(" 잘 거야.", no_speech=0.9), seg(" 1단계.", logprob=-1.4)))
    assert text.strip() == "눈부셔"
    assert info == {"segments": 3, "dropped": 2, "max_no_speech": 0.9, "min_logprob": -1.4}
    text, info = speech_text(verbose(seg(" 너무 밝아", no_speech=0.6, logprob=-1.0)))   # 기준과 같으면 통과
    assert text.strip() == "너무 밝아" and info["dropped"] == 0


@pytest.mark.parametrize("data", [
    {"text": " 너무 밝아"},                                                    # json 형식 (segments 없음)
    {"text": " 너무 밝아", "segments": []},
    {"text": " 너무 밝아", "segments": [{"id": 0, "text": " 너무 밝아"}]},      # 구간 값이 없는 옛 서버
    {"text": " 너무 밝아", "segments": [seg(" 너무 밝아", no_speech=None, logprob=None)]},
    {"text": " 너무 밝아", "segments": [{"text": " 너무 밝아", "no_speech_prob": None, "avg_logprob": "nan"}]},
])
def test_no_quality_fields_falls_back_to_text(data):
    text, info = speech_text(data)
    assert text.strip() == "너무 밝아" and info is None


def test_one_missing_field_uses_the_other():
    assert speech_text(verbose(seg(" 잘 거야.", no_speech=None, logprob=-2.0)))[0] == ""
    assert speech_text(verbose(seg(" 잘 거야.", no_speech=0.95, logprob=None)))[0] == ""
    assert speech_text(verbose(seg(" 잘 거야.", no_speech=None, logprob=-0.2)))[0].strip() == "잘 거야."


@pytest.mark.parametrize("heard,expected", [
    (verbose(seg(" 잘 거야.", no_speech=0.82)), ""),                 # 음악: 말 없음 확률 높음
    (verbose(seg(" 1단계.", no_speech=0.1, logprob=-1.6)), ""),      # 음악: 자신 없이 지어냄
    (verbose(seg(" 눈부셔", no_speech=0.02, logprob=-0.25)), "눈부셔"),
    ({"text": " 눈부셔"}, "눈부셔"),                                   # 값 없는 서버: 지금처럼 text
])
def test_transcribe_noise_gate(monkeypatch, whisper_url, heard, expected):
    monkeypatch.setattr(FakeWhisper, "reply", heard)
    stt = WhisperSTT(whisper_url)
    assert stt.transcribe(make_wav()) == expected and stt.last_error is None
    assert (stt.last_quality is None) == ("segments" not in heard)


def test_transcribe_server_down():
    stt = WhisperSTT("http://127.0.0.1:9/inference")
    assert not stt.available()
    assert stt.transcribe(make_wav()) is None and "whisper" in stt.last_error


class FakeSTT:
    def __init__(self, text):
        self.text = text
        self.last_error = None if text is not None else "whisper 오류 (URLError)"
        self.last_ms = 120

    def available(self):
        return True

    def transcribe(self, data):
        return self.text


@pytest.fixture()
def make_client(tmp_path):
    def _make(text):
        sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
        ctrl = Controller(sensor, relays, clock, outdoor, None)
        ctrl.step()
        store = LogStore(str(tmp_path / "t.db"))
        voice = VoiceHandler(ctrl, IntentModel(), None)
        return create_app(ctrl, store, voice=voice, stt=FakeSTT(text)).test_client(), ctrl
    return _make


def post_audio(client, data, device="폰1"):
    return client.post("/api/voice/audio", data={"audio": (io.BytesIO(data), "voice.wav"), "device": device},
                       content_type="multipart/form-data")


def test_audio_command_applies(make_client):
    client, ctrl = make_client("2단계로 해 줘")
    r = post_audio(client, make_wav())
    d = r.get_json()
    assert r.status_code == 200 and d["heard"] == "2단계로 해 줘" and d["level_after"] == min(2, config.NUM_LEVELS - 1)
    assert d["device"] == "폰1" and d["stt_ms"] == 120
    st = client.get("/api/state").get_json()
    assert st["voice"]["status"]["stt"] is True


def test_audio_silence_and_errors(make_client):
    client, ctrl = make_client("")
    d = post_audio(client, make_wav()).get_json()
    assert not d["applied"] and "다시" in d["reply"]
    assert post_audio(client, b"x" * 100).status_code == 400
    assert client.post("/api/voice/audio").status_code == 400
    client, _ = make_client(None)
    assert post_audio(client, make_wav()).status_code == 503


def test_audio_noise_shows_not_heard(monkeypatch, tmp_path, whisper_url):
    # 실제 WhisperSTT + 가짜 서버: 음악에서 "잘 거야."(privacy)를 지어내도 실행하지 않고 "잘 안 들렸어요"
    monkeypatch.setattr(FakeWhisper, "reply", verbose(seg(" 잘 거야.", no_speech=0.85, logprob=-0.4)))
    sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
    ctrl = Controller(sensor, relays, clock, outdoor, None)
    ctrl.step()
    before = ctrl.snapshot()["level"]
    voice = VoiceHandler(ctrl, IntentModel(), None)
    client = create_app(ctrl, LogStore(str(tmp_path / "t.db")), voice=voice, stt=WhisperSTT(whisper_url)).test_client()
    r = post_audio(client, make_wav())
    d = r.get_json()
    assert r.status_code == 200 and d["heard"] == "" and d["source"] == "none" and not d["applied"]
    assert d["reply"].startswith("잘 안 들렸어요")
    assert ctrl.snapshot()["level"] == before and voice.recent() == []


@pytest.mark.parametrize("text", ["고생하셨습니다", "감사합니다", "고파", "아", "음"])
def test_noise_words_do_nothing(make_client, text):
    # whisper가 잡음에서 자주 내는 말: 분류기가 '관계없음'으로 보고 단계를 바꾸지 않아야 한다
    client, ctrl = make_client(text)
    before = ctrl.snapshot()["level"]
    d = post_audio(client, make_wav()).get_json()
    assert d["intent"] == "other" and d["action"] == "none" and not d["applied"]
    assert ctrl.snapshot()["level"] == before


def test_audio_too_long(make_client):
    client, _ = make_client("너무 밝아")
    big = make_wav(seconds=(config.VOICE_AUDIO_MAX_BYTES // 32000) + 2)
    assert post_audio(client, big).status_code == 413
