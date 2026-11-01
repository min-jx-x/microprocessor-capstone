"""음성 → 글자 (STT). Pi에서 따로 도는 whisper.cpp 서버(whisper-server)에 WAV를 보내고 글자를 받는다.

- whisper-server 설치·실행: bash deploy/setup_whisper.sh (Pi, 인터넷 필요한 건 설치 때 한 번뿐)
- 주소: 환경변수 LIGHTQ_STT_URL (기본 config.VOICE_STT_URL = http://127.0.0.1:8178/inference)
- 서버가 없거나 응답이 없으면 last_error를 남기고 None. 화면은 그때 마이크 대신 입력칸만 쓴다.
- 잡음만 들어와 Whisper가 프롬프트 문장을 지어내면(is_prompt_echo) 빈 글자로 돌려준다.
- verbose_json으로 받아 구간별 no_speech_prob / avg_logprob가 기준(config.VOICE_STT_MAX_NO_SPEECH,
  VOICE_STT_MIN_LOGPROB)을 넘는 구간은 버린다(음악·잡음에서 지어낸 "잘 거야." 같은 문장). 값이 없으면 text만 쓴다.
- 파이썬 기본 라이브러리(urllib)만 쓴다.
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Optional

from pi import config

# 소리가 거의 없을 때 Whisper가 지어내는 자막·효과음 표기 ([음악], (박수) 등)
_BRACKETS = re.compile(r"[\[\(（【][^\]\)）】]*[\]\)）】]")


def is_wav(data: bytes) -> bool:
    return len(data) > 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _BRACKETS.sub(" ", text or "")).strip()


_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")
ECHO_RUN = 3        # 프롬프트의 연속된 문장이 이만큼 그대로 나오면 지어낸 것으로 본다


def _norm(s: str) -> str:
    return _NOT_WORD.sub("", s or "")


def is_prompt_echo(text: str, prompt: Optional[str] = None) -> bool:
    """잡음만 들어왔을 때 Whisper가 프롬프트(config.VOICE_STT_PROMPT)를 그대로 읊은 결과인지.

    - 프롬프트 첫 문장이 들어 있으면: 사용자가 할 말이 아니므로 거른다
      (지금 프롬프트는 문장 없이 어휘만 나열한 한 덩어리라, 그것을 통째로 읊은 경우)
    - 프롬프트의 연속된 문장 ECHO_RUN개 이상이 순서 그대로 들어 있으면: 거른다
    - "눈부셔 너무 밝아"처럼 두 문장만 이은 것, 짧은 명령 한 문장은 실제 말일 수 있어 통과
    공백·문장부호는 무시하고 비교한다.
    """
    prompt = config.VOICE_STT_PROMPT if prompt is None else prompt
    sents = [n for n in (_norm(s) for s in re.split(r"[.!?。]", prompt or "")) if n]
    t = _norm(text)
    if not sents or not t:
        return False
    if sents[0] in t:
        return True
    return any("".join(sents[i:i + ECHO_RUN]) in t for i in range(len(sents) - ECHO_RUN + 1))


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def is_noise_segment(seg: dict) -> bool:
    """구간 하나가 말이 아닌 소리(음악·잡음)인지. 값이 없는 기준은 보지 않는다."""
    nsp, lp = _num(seg.get("no_speech_prob")), _num(seg.get("avg_logprob"))
    return (nsp is not None and nsp > config.VOICE_STT_MAX_NO_SPEECH) or \
           (lp is not None and lp < config.VOICE_STT_MIN_LOGPROB)


def speech_text(data: dict):
    """whisper 응답 → (글자, 판정 정보).

    verbose_json이면 segments의 no_speech_prob / avg_logprob로 잡음 구간을 빼고 남은 구간만 잇는다.
    구간 값이 없는 서버(옛 버전, response_format=json)면 text를 그대로 쓰고 판정 정보는 None.
    """
    segs = data.get("segments")
    segs = [s for s in segs if isinstance(s, dict)] if isinstance(segs, list) else []
    scored = [s for s in segs if _num(s.get("no_speech_prob")) is not None or _num(s.get("avg_logprob")) is not None]
    if not scored:
        return str(data.get("text") or ""), None
    kept = [s for s in segs if not is_noise_segment(s)]
    nsps = [v for v in (_num(s.get("no_speech_prob")) for s in segs) if v is not None]
    lps = [v for v in (_num(s.get("avg_logprob")) for s in segs) if v is not None]
    info = {
        "segments": len(segs), "dropped": len(segs) - len(kept),
        "max_no_speech": round(max(nsps), 3) if nsps else None,
        "min_logprob": round(min(lps), 3) if lps else None,
    }
    return " ".join(str(s.get("text") or "") for s in kept), info


class WhisperSTT:
    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or os.environ.get("LIGHTQ_STT_URL") or config.VOICE_STT_URL
        self.timeout = config.VOICE_STT_TIMEOUT_S
        self.last_error = None
        self._up = None                 # (확인 시각, 결과) 서버 살아 있는지 잠깐 기억
        self.last_ms = None
        self.last_quality = None        # 마지막 인식의 잡음 판정 정보 (speech_text 참고, 재측정용)

    def available(self) -> bool:
        """서버가 켜져 있는지. 화면이 1초마다 묻기 때문에 config.VOICE_STT_CHECK_S 동안 결과를 기억한다."""
        now = time.monotonic()
        if self._up is not None and now - self._up[0] < config.VOICE_STT_CHECK_S:
            return self._up[1]
        base = self.url.rsplit("/", 1)[0] + "/"
        try:
            with urllib.request.urlopen(base, timeout=1.0):
                ok = True
        except urllib.error.HTTPError:
            ok = True                   # 응답이 왔으면 켜져 있는 것
        except Exception as e:
            ok = False
            self.last_error = f"whisper 서버 없음 ({type(e).__name__})"
        self._up = (now, ok)
        return ok

    def _multipart(self, wav: bytes):
        boundary = uuid.uuid4().hex
        fields = {
            "language": config.VOICE_STT_LANG,
            "response_format": "verbose_json",     # 구간별 no_speech_prob / avg_logprob 를 받으려고
            "no_language_probabilities": "true",   # verbose_json에 붙는 언어 확률 계산(추가 연산)은 끈다
            "temperature": "0.0",
            "no_timestamps": "true",
            "suppress_nst": "true",
        }
        if config.VOICE_STT_PROMPT:
            fields["prompt"] = config.VOICE_STT_PROMPT
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.wav"\r\n'
                     f'Content-Type: audio/wav\r\n\r\n'.encode("utf-8") + wav + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def transcribe(self, wav: bytes) -> Optional[str]:
        """WAV(16kHz mono 권장) → 글자. 실패하면 None (last_error에 이유), 잡음으로 판정하면 ""."""
        self.last_quality = None
        if not is_wav(wav):
            self.last_error = "WAV 형식이 아님"
            return None
        body, ctype = self._multipart(wav)
        req = urllib.request.Request(self.url, data=body, method="POST", headers={"Content-Type": ctype})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:          # 서버 꺼짐, 시간 초과, 형식 오류
            self.last_error = f"whisper 오류 ({type(e).__name__})"
            self._up = (time.monotonic(), False)
            return None
        self.last_ms = round((time.perf_counter() - t0) * 1000)
        self.last_error = None
        self._up = (time.monotonic(), True)
        if not isinstance(data, dict):
            self.last_error = "whisper 응답 형식 오류"
            return None
        raw, self.last_quality = speech_text(data)
        q = self.last_quality
        if q is not None and q["dropped"]:
            print(f"[stt] 잡음 구간 {q['dropped']}/{q['segments']}개 버림 (말 없음 최대 {q['max_no_speech']}, "
                  f"logprob 최저 {q['min_logprob']}): '{clean_text(str(data.get('text') or ''))[:40]}'")
        text = clean_text(raw)
        if is_prompt_echo(text):
            print(f"[stt] 프롬프트를 그대로 읊은 결과라 버림: '{text[:40]}'")
            return ""                   # 화면에는 "잘 안 들렸어요"
        return text
