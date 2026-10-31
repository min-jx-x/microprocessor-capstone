"""음성 명령 평가 (발표용 지표). 시험 예문(split=test)으로 분류기만 vs 하이브리드(분류기 + LLM)를 비교한다.

실행 (레포 최상위):
  python -m pi.voice.evaluate          분류기만 (인터넷·키 불필요)
  python -m pi.voice.evaluate --llm    하이브리드. 환경변수 LIGHTQ_LLM_KEY 필요 (cmd: set LIGHTQ_LLM_KEY=키)
  python -m pi.voice.evaluate --llm --extra "영화 볼 거야" "책 읽을 거야"   예문에 없는 상황형 문장도 LLM 답 확인

지표
  accuracy      : 정답 의도와 같은 비율 (분류기가 '모름'이면 틀린 것으로 셈)
  llm_calls     : LLM에 넘어간 문장 수 (확신도 < config.VOICE_MIN_CONF 또는 'other')
  avg_ms        : 문장 하나 판단에 걸린 평균 시간
"""
import argparse
import csv
import time

from pi import config
from pi.voice.intent import IntentModel
from pi.voice.llm import GeminiFallback
from pi.voice.text import extract_level

STATE = {"level": 1, "mode": "auto", "lux": 600}


def decide(model, llm, text):
    intent, conf = model.predict(text)
    confident = intent != "other" and conf >= config.VOICE_MIN_CONF
    if confident and not (intent == "set_level" and extract_level(text) is None):
        return intent, "model"
    if llm is not None:
        r = llm.interpret(text, STATE)
        if r is not None:
            return ("other" if r["action"] == "none" else r["action"]), "llm"
    # handler.py와 같은 규칙: LLM을 못 쓰면 낮은 기준으로 분류기 답을 쓴다
    if intent != "other" and conf >= config.VOICE_MIN_CONF_OFFLINE and not (intent == "set_level" and extract_level(text) is None):
        return intent, "model"
    return "other", "none"


def run(model, llm, rows):
    hits, calls, ms = 0, 0, []
    for r in rows:
        t0 = time.perf_counter()
        pred, src = decide(model, llm, r["text"])
        ms.append((time.perf_counter() - t0) * 1000)
        calls += src == "llm"
        hits += pred == r["intent"]
        if pred != r["intent"]:
            print(f"    틀림 [{src}] '{r['text']}' 정답 {r['intent']} → {pred}")
    return hits / len(rows), calls, sum(ms) / len(ms)


def main() -> None:
    ap = argparse.ArgumentParser(description="음성 명령 평가")
    ap.add_argument("--llm", action="store_true", help="하이브리드도 평가 (LIGHTQ_LLM_KEY 필요)")
    ap.add_argument("--extra", nargs="*", default=[], help="LLM 답만 확인할 추가 문장")
    args = ap.parse_args()
    model = IntentModel()
    with open(config.VOICE_DATA_PATH, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test"]

    print(f"시험 예문 {len(rows)}개, 확신도 기준 {config.VOICE_MIN_CONF}")
    print("[분류기만]")
    acc, _, ms = run(model, None, rows)
    print(f"  정확도 {acc:.1%}, 평균 {ms:.1f}ms")
    if args.llm:
        llm = GeminiFallback()
        if not llm.enabled:
            raise SystemExit("LIGHTQ_LLM_KEY 환경변수가 없음")
        print(f"[하이브리드: 분류기 + {llm.model}]")
        acc, calls, ms = run(model, llm, rows)
        print(f"  정확도 {acc:.1%}, LLM 호출 {calls}회, 평균 {ms:.0f}ms, 마지막 LLM 오류: {llm.last_error}")
        for text in args.extra:
            t0 = time.perf_counter()
            r = llm.interpret(text, STATE)
            print(f"  '{text}' → {r} ({(time.perf_counter() - t0) * 1000:.0f}ms, 오류: {llm.last_error})")


if __name__ == "__main__":
    main()
