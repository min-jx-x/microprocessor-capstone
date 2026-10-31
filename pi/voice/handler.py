"""문장 명령 처리: 문장 → (분류기, 필요하면 LLM) → 동작 → 응답.

처리 순서
  1) 의도 분류기(Pi, 오프라인)가 확신도 config.VOICE_MIN_CONF 이상이면 그 답을 쓴다.
  2) 아니면(또는 '모름'이면) LLM에 묻는다. 키·인터넷이 없으면 건너뛴다.
  3) LLM을 못 쓰면 낮은 기준(config.VOICE_MIN_CONF_OFFLINE) 이상인 분류기 답을 쓴다.
  4) 그것도 아니면 바꾸지 않고 "다시 말해 주세요".
동작은 웹 단계 버튼과 같은 Controller.set_manual / set_mode 를 쓴다.
여러 기기가 동시에 보내도 하나씩 처리하고, 단계를 바꾸는 명령 사이에는 config.VOICE_COOLDOWN_S 간격을 둔다.
"""
import re
import threading
import time
from collections import deque
from datetime import datetime
from typing import Callable, Optional

from pi import config
from pi.voice.text import extract_level

_CTRL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

HELP = "예: '너무 밝아', '2단계로', '자동으로'"


def clean_device(name) -> str:
    return _CTRL_CHARS.sub("", str(name or "")).strip()[:16] or "이름 없음"


class VoiceHandler:
    def __init__(self, ctrl, model=None, llm=None, clock: Callable[[], float] = time.monotonic) -> None:
        self.ctrl = ctrl
        self.model = model
        self.llm = llm
        self.clock = clock
        self.learn = config.VOICE_LEARN          # 음성 명령을 개인 선호 학습에 쓸지 (시연 기본: 끔)
        self._last_change = None
        self._seq = 0                   # 화면이 새 기록을 알아보는 번호
        self._log = deque(maxlen=config.VOICE_LOG_SIZE)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 판단
    def _decide(self, text: str, state: dict) -> dict:
        intent, conf = self.model.predict(text) if self.model is not None else ("other", 0.0)
        level = extract_level(text)
        out = {"intent": intent, "confidence": round(conf, 3), "source": "none",
               "action": "none", "level": None, "llm_reply": ""}
        confident = intent != "other" and conf >= config.VOICE_MIN_CONF
        if confident and not (intent == "set_level" and level is None):
            out.update(source="model", action=intent, level=level)
            return out
        if self.llm is not None and self.llm.enabled:
            r = self.llm.interpret(text, state)
            if r is not None:
                out.update(source="llm", action=r["action"], level=r["level"], llm_reply=r["reply"])
                return out
        # LLM을 못 쓰면(키·인터넷 없음, 실패) 기준을 낮춰 분류기 답을 쓴다. 너무 애매하면 그래도 '모름'
        if intent != "other" and conf >= config.VOICE_MIN_CONF_OFFLINE and not (intent == "set_level" and level is None):
            out.update(source="model", action=intent, level=level)
        return out

    # ------------------------------------------------------------ 실행
    def handle(self, text: str, device: str = "") -> dict:
        text = str(text or "").strip()[:config.VOICE_MAX_CHARS]
        if not text:
            raise ValueError("문장이 비어 있음")
        device = clean_device(device)
        t0 = time.perf_counter()
        with self._lock:
            snap = self.ctrl.snapshot()
            state = {"level": snap["level"], "mode": snap["mode"], "lux": snap["lux"]}
            d = self._decide(text, state)
            cur, top = state["level"], config.NUM_LEVELS - 1
            action, target, reply, applied = d["action"], None, "", False

            if action == "darker":
                target = max(0, cur - 1)
                reply = "이미 가장 어두운 단계예요" if cur == 0 else f"{target}단계로 어둡게 할게요"
            elif action == "brighter":
                target = min(top, cur + 1)
                reply = "이미 가장 밝은 단계예요" if cur == top else f"{target}단계로 밝게 할게요"
            elif action == "set_level":
                lv = d["level"]
                if lv is None:
                    action, reply = "none", "몇 단계로 할지 말해 주세요"
                elif lv > top:
                    target, reply = top, f"단계는 0~{top}이라 {top}단계로 할게요"
                else:
                    target, reply = lv, f"{lv}단계로 바꿀게요"
            elif action == "privacy":
                target, reply = 0, "0단계로 가릴게요"
            elif action == "max_bright":
                target, reply = top, f"{top}단계로 가장 밝게 할게요"
            elif action == "auto":
                reply = "자동 제어로 돌아갈게요"
            elif action == "status":
                lux = "?" if state["lux"] is None else f"{state['lux']:.0f}"
                mode = "자동" if state["mode"] == "auto" else "수동"
                reply = f"지금 {cur}단계, {mode} 모드, {lux} lux예요"
            if action == "none" and not reply:
                # LLM이 '관계없는 말'로 판단했으면 그 짧은 답을 보여 준다 (예: 인사)
                reply = d["llm_reply"] or f"잘 못 알아들었어요. {HELP}"

            changes = target is not None or action == "auto"
            now = self.clock()
            if changes and self._last_change is not None and now - self._last_change < config.VOICE_COOLDOWN_S:
                reply, changes = "잠시 후 다시 말해 주세요", False
                action = "cooldown"
            if changes:
                if action == "auto":
                    self.ctrl.set_mode("auto")
                else:
                    self.ctrl.set_manual(target, learn=self.learn)
                self._last_change = now
                applied = True
                if d["source"] == "llm" and d["llm_reply"]:
                    reply = d["llm_reply"]

            after = self.ctrl.snapshot()
            self._seq += 1
            result = {
                "id": self._seq, "time": datetime.now().strftime("%H:%M:%S"),
                "text": text, "device": device, "intent": d["intent"], "confidence": d["confidence"],
                "source": d["source"], "action": action, "applied": applied,
                "level_before": cur, "level_after": after["level"], "mode": after["mode"],
                "reply": reply, "ms": round((time.perf_counter() - t0) * 1000),
                "vtime": after["vtime"],
            }
            self._log.appendleft(result)
        print(f"[voice] {device}: '{text}' → {d['source']}:{action} ({cur}→{result['level_after']}) {result['ms']}ms")
        return result

    # ------------------------------------------------------------ 화면용
    def recent(self) -> list:
        with self._lock:
            return list(self._log)

    def status(self) -> dict:
        llm = self.llm
        return {
            "model": self.model is not None,
            "model_meta": getattr(self.model, "meta", None),
            "min_conf": config.VOICE_MIN_CONF,
            "llm": bool(llm is not None and llm.enabled),
            "llm_model": getattr(llm, "model", None) if llm is not None and llm.enabled else None,
            "llm_error": getattr(llm, "last_error", None) if llm is not None else None,
            "learn": self.learn,
            "cooldown_s": config.VOICE_COOLDOWN_S,
        }

    def set_learning(self, enabled: bool) -> None:
        with self._lock:
            self.learn = bool(enabled)
