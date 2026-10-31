"""분류기가 확신하지 못한 문장만 LLM(Gemini)에 묻는다.

- 키: 환경변수 LIGHTQ_LLM_KEY (레포에 넣지 않는다. Pi에서는 /etc/default/lightq)
- 모델: 환경변수 LIGHTQ_LLM_MODEL (기본 config.VOICE_LLM_MODEL)
- 키가 없거나, 인터넷이 없거나, 시간 초과·형식 오류면 None을 돌려주고 분류기 결과로 처리한다.
- LLM 답은 그대로 쓰지 않는다. action/level을 코드에서 다시 검사한다 (validate).
- 파이썬 기본 라이브러리(urllib)만 써서 Pi에 새로 설치할 패키지가 없다.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Optional

from pi import config

ACTIONS = ("darker", "brighter", "set_level", "privacy", "max_bright", "auto", "status", "none")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM = """너는 스마트 조광 창문(PDLC 필름) 'LightQ'의 음성 명령 해석기다.
투과 단계는 0~{top}이다. 0은 가장 불투명하고 어두움(사생활 보호), {top}은 가장 투명하고 밝음.
사용자 문장을 아래 action 중 하나로 바꿔 JSON 하나만 출력한다. 설명 문장은 쓰지 않는다.
- darker: 지금보다 한 단계 어둡게(눈부심, 너무 밝음, 조금 가림)
- brighter: 지금보다 한 단계 밝게(어두움, 빛이 더 필요함)
- set_level: 특정 단계로. level에 0~{top} 정수
- privacy: 0단계(완전히 가림. 잠, 옷 갈아입기, 영화 감상, 사생활)
- max_bright: {top}단계(완전히 투명, 빛 최대)
- auto: 자동 제어로 돌아가기
- status: 현재 상태 질문
- none: 창문 밝기와 관계없는 말
형식: {{"action": "...", "level": 정수 또는 null, "reply": "사용자에게 할 짧은 한국어 답(20자 이내)"}}"""


def validate(obj) -> Optional[dict]:
    """LLM 답을 검사해서 안전한 dict만 돌려준다. 틀리면 None."""
    if not isinstance(obj, dict):
        return None
    action = obj.get("action")
    if action not in ACTIONS:
        return None
    level = obj.get("level")
    if action == "set_level":
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < config.NUM_LEVELS:
            return None
    else:
        level = None
    reply = obj.get("reply")
    reply = str(reply)[:40] if isinstance(reply, str) else ""
    return {"action": action, "level": level, "reply": reply}


class GeminiFallback:
    def __init__(self, key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.key = key if key is not None else os.environ.get("LIGHTQ_LLM_KEY", "")
        self.model = model or os.environ.get("LIGHTQ_LLM_MODEL") or config.VOICE_LLM_MODEL
        self.timeout = config.VOICE_LLM_TIMEOUT_S
        self._cache: "OrderedDict[str, dict]" = OrderedDict()
        self._calls = []                # 최근 1분 호출 시각 (무료 등급 분당 제한 보호)
        self._blocked_until = 0.0       # 429(사용량 초과)를 받으면 잠시 쉬기
        self._lock = threading.Lock()
        self.last_error = None

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _allowed(self, now: float) -> bool:
        if now < self._blocked_until:
            self.last_error = "사용량 제한으로 잠시 쉬는 중"
            return False
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= config.VOICE_LLM_MAX_PER_MIN:
            self.last_error = "분당 호출 한도(앱 설정)"
            return False
        self._calls.append(now)
        return True

    def _request(self, prompt: str) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM.format(top=config.NUM_LEVELS - 1)}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # 출력 길이 제한(maxOutputTokens)은 두지 않는다: 생각(thinking) 토큰도 같이 세는 모델이 있어 답이 잘릴 수 있음
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            URL.format(model=self.model), data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        text = [p["text"] for p in parts if "text" in p and not p.get("thought")][-1]
        return json.loads(text)

    def interpret(self, text: str, state: dict) -> Optional[dict]:
        """문장 + 현재 상태 → {"action","level","reply"} 또는 None(못 씀)."""
        if not self.enabled:
            self.last_error = "키 없음"
            return None
        key = text.strip()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if not self._allowed(time.monotonic()):
                return None
        prompt = (f"현재 단계 {state.get('level')} / 모드 {state.get('mode')} / "
                  f"조도 {state.get('lux')} lux\n사용자: {text}")
        try:
            result = validate(self._request(prompt))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                with self._lock:
                    self._blocked_until = time.monotonic() + 60
            self.last_error = f"HTTP {e.code}"
            return None
        except Exception as e:          # 인터넷 없음, 시간 초과, 형식 오류 등
            self.last_error = type(e).__name__
            return None
        if result is None:
            self.last_error = "형식 오류"
            return None
        self.last_error = None
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
        return result
