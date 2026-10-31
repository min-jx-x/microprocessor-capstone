"""음성(문장) 명령 테스트: 숫자 뽑기, 분류기 정확도, 동작 매핑, LLM 폴백, 웹 API."""
import csv

import pytest

from pi import config
from pi.app import build_devices, create_app
from pi.control.loop import Controller
from pi.voice.handler import VoiceHandler
from pi.voice.intent import IntentModel
from pi.voice.llm import GeminiFallback, validate
from pi.voice.text import extract_level

TOP = config.NUM_LEVELS - 1


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0
        self.enabled = True
        self.model = "fake"
        self.last_error = None

    def interpret(self, text, state):
        self.calls += 1
        return self.answer


@pytest.fixture()
def ctrl():
    sensor, relays, clock, outdoor = build_devices(False, 720, "12:00")
    c = Controller(sensor, relays, clock, outdoor, None)
    for _ in range(3):
        c.step()
    return c


@pytest.fixture(scope="module")
def model():
    return IntentModel()


def make(ctrl, model, llm=None):
    clock = FakeClock()
    h = VoiceHandler(ctrl, model, llm, clock=clock)
    return h, clock


@pytest.mark.parametrize("text,level", [
    ("2단계로 해줘", 2), ("이 단계로", 2), ("레벨 1로", 1), ("단계를 0으로 바꿔", 0),
    ("일단계로 해 줘", 1), ("한 단계 어둡게", None), ("지금 몇 단계야", None), ("일단 어둡게 해줘", None),
])
def test_extract_level(text, level):
    assert extract_level(text) == level


def test_model_accuracy_on_held_out(model):
    """학습에 쓰지 않은 시험 예문 정확도. 기준 85% (현재 약 92%)."""
    with open(config.VOICE_DATA_PATH, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test"]
    correct = sum(model.predict(r["text"])[0] == r["intent"] for r in rows)
    assert correct / len(rows) >= 0.85


def test_actions(ctrl, model):
    h, clock = make(ctrl, model)
    r = h.handle("2단계로 해줘", "폰1")
    assert r["source"] == "model" and r["applied"] and r["level_after"] == min(2, TOP) and r["mode"] == "manual"
    clock.t += 5
    r = h.handle("너무 밝아")
    assert r["action"] == "darker" and r["level_after"] == min(2, TOP) - 1
    clock.t += 5
    assert h.handle("다 가려줘")["level_after"] == 0
    clock.t += 5
    r = h.handle("너무 밝아")                    # 이미 0단계
    assert r["level_after"] == 0 and "이미" in r["reply"]
    clock.t += 5
    assert h.handle("완전 투명하게")["level_after"] == TOP
    clock.t += 5
    assert h.handle("자동으로 해줘")["mode"] == "auto"
    r = h.handle("지금 몇 단계야")
    assert r["action"] == "status" and not r["applied"] and "단계" in r["reply"]


def test_out_of_range_level_clamped(ctrl, model):
    h, _ = make(ctrl, model)
    r = h.handle("9단계로 해줘")
    assert r["level_after"] == TOP


def test_cooldown_between_changes(ctrl, model):
    h, clock = make(ctrl, model)
    h.handle("0단계로 해줘", "폰1")
    r = h.handle("2단계로 해줘", "폰2")            # 2초 안에 다른 기기가 보냄
    assert r["action"] == "cooldown" and not r["applied"] and r["level_after"] == 0
    assert h.handle("지금 상태 알려줘")["action"] == "status"   # 상태 질문은 막지 않음
    clock.t += config.VOICE_COOLDOWN_S + 0.1
    assert h.handle("2단계로 해줘")["level_after"] == min(2, TOP)


def test_low_confidence_goes_to_llm(ctrl, model):
    # 예문에 없는 애매한 문장 → 분류기가 확신하지 못해 LLM으로 넘어간다
    llm = FakeLLM({"action": "privacy", "level": None, "reply": "편히 쉬시게 가릴게요"})
    h, _ = make(ctrl, model, llm)
    r = h.handle("오늘 기분이 좀 그래")
    assert llm.calls == 1 and r["source"] == "llm" and r["level_after"] == 0
    assert r["reply"] == "편히 쉬시게 가릴게요"


def test_confident_command_skips_llm(ctrl, model):
    llm = FakeLLM({"action": "max_bright", "level": None, "reply": ""})
    h, _ = make(ctrl, model, llm)
    h.handle("2단계로 해줘")
    assert llm.calls == 0


def test_llm_failure_changes_nothing(ctrl, model):
    h, _ = make(ctrl, model, FakeLLM(None))
    before = ctrl.level
    r = h.handle("오늘 기분이 좀 그래")
    assert r["source"] == "none" and not r["applied"] and ctrl.level == before


def test_no_model_no_llm_is_safe(ctrl):
    h, _ = make(ctrl, None, None)
    r = h.handle("너무 밝아")
    assert r["source"] == "none" and not r["applied"]
    with pytest.raises(ValueError):
        h.handle("   ")


def test_voice_does_not_learn_by_default(ctrl, model):
    h, _ = make(ctrl, model)
    h.learn = False
    h.handle("1단계로 해줘")
    assert ctrl._pref_pending is None
    h.learn = True
    h.clock.t += 5
    h.handle("2단계로 해줘")
    assert ctrl._pref_pending is not None


@pytest.mark.parametrize("obj,ok", [
    ({"action": "darker", "level": None, "reply": "네"}, True),
    ({"action": "set_level", "level": 1, "reply": ""}, True),
    ({"action": "set_level", "level": 99, "reply": ""}, False),
    ({"action": "set_level", "level": "2", "reply": ""}, False),
    ({"action": "open_door", "level": None}, False),
    ("darker", False),
])
def test_llm_output_validation(obj, ok):
    assert (validate(obj) is not None) == ok


def test_llm_without_key_does_not_call_network():
    llm = GeminiFallback(key="")
    assert not llm.enabled and llm.interpret("영화 볼 거야", {}) is None


def test_voice_api(tmp_path, ctrl, model):
    from pi.storage import LogStore
    store = LogStore(str(tmp_path / "t.db"))
    client = create_app(ctrl, store, voice=VoiceHandler(ctrl, model, None)).test_client()
    r = client.post("/api/voice", json={"text": "1단계로 바꿔줘", "device": "노트북"})
    assert r.status_code == 200 and r.get_json()["level_after"] == 1
    assert client.post("/api/voice", json={"text": ""}).status_code == 400
    st = client.get("/api/state").get_json()
    assert st["voice"]["recent"][0]["device"] == "노트북" and st["level"] == 1
    assert client.post("/api/voice/learn", json={"enabled": "yes"}).status_code == 400
    assert client.post("/api/voice/learn", json={"enabled": True}).status_code == 200
    assert client.get("/api/voice").get_json()["status"]["learn"] is True
