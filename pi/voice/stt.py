"""음성 → 글자 (STT). Pi에서 따로 도는 whisper.cpp 서버(whisper-server)에 WAV를 보내고 글자를 받는다.

- whisper-server 설치·실행: bash deploy/setup_whisper.sh (Pi, 인터넷 필요한 건 설치 때 한 번뿐)
- 주소: 환경변수 LIGHTQ_STT_URL (기본 config.VOICE_STT_URL = http://127.0.0.1:8178/inference)
- 서버가 없거나 응답이 없으면 last_error를 남기고 None. 화면은 그때 마이크 대신 입력칸만 쓴다.
- 잡음만 들어와 Whisper가 프롬프트 문장을 지어내면(is_prompt_echo) 빈 글자로 돌려준다.
- 파이썬 기본 라이브러리(urllib)만 쓴다.
"""
import json
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

    - 프롬프트 첫 문장(제목, "라이트큐 창문 밝기 명령")이 들어 있으면: 사용자가 할 말이 아니므로 거른다
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


class WhisperSTT:
    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or os.environ.get("LIGHTQ_STT_URL") or config.VOICE_STT_URL
        self.timeout = config.VOICE_STT_TIMEOUT_S
        self.last_error = None
        self._up = None                 # (확인 시각, 결과) 서버 살아 있는지 잠깐 기억
        self.last_ms = None

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
            "response_format": "json",
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
        """WAV(16kHz mono 권장) → 글자. 실패하면 None (last_error에 이유)."""
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
        text = clean_text(data.get("text", ""))
        if is_prompt_echo(text):
            print(f"[stt] 프롬프트를 그대로 읊은 결과라 버림: '{text[:40]}'")
            return ""                   # 화면에는 "잘 안 들렸어요"
        return text
