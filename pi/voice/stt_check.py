"""whisper 서버 확인 (Pi에서 실행). 녹음 파일을 글자로 바꾸고 걸린 시간과 의도 판단까지 보여 준다.

실행 (레포 최상위):
  .venv/bin/python -m pi.voice.stt_check 파일1.wav 파일2.wav ...
  .venv/bin/python -m pi.voice.stt_check            파일 없이: 서버가 켜져 있는지만 확인
녹음 파일은 웹에서 마이크로 말하면 Pi의 pi/data/voice_audio/ 에 최근 것이 저장된다 (config.VOICE_AUDIO_KEEP).
"""
import sys

from pi.voice.intent import load_model
from pi.voice.stt import WhisperSTT


def main() -> None:
    stt = WhisperSTT()
    print(f"whisper 서버 {stt.url}: {'켜짐' if stt.available() else '꺼짐 ' + str(stt.last_error)}")
    model = load_model()
    for path in sys.argv[1:]:
        with open(path, "rb") as f:
            text = stt.transcribe(f.read())
        if text is None:
            print(f"  {path}: 실패 ({stt.last_error})")
            continue
        intent = model.predict(text) if model and text else ("-", 0)
        q = stt.last_quality
        quality = "구간 값 없음(text만 사용)" if q is None else (
            f"구간 {q['segments']}개 중 {q['dropped']}개 버림, 말 없음 최대 {q['max_no_speech']}, logprob 최저 {q['min_logprob']}")
        print(f"  {path}: '{text}' ({stt.last_ms}ms) → {intent[0]} {intent[1]:.2f} | {quality}")


if __name__ == "__main__":
    main()
