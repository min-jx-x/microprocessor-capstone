"""단계별 실측값(lut.json) 읽기·쓰기.

필름을 조립한 뒤, 같은 광원(LED 스탠드)에서 조합마다 실내 조도를 재서 저장한다.

단계 구성은 환경변수 LIGHTQ_LEVELS로 고른다 (기본 3).
  3 (기본): 45V만 사용. 필름 업체 안내 구동 전압(60~70V) 안이라 안전하다.
      0단계: 꺼짐/꺼짐 (off / off)
      1단계: 45V/꺼짐 (low / off)
      2단계: 45V/45V  (low / low)
  6: 45V + 100V. 위 3개 뒤에
      3단계: 100V/꺼짐 (high / off)
      4단계: 100V/45V  (high / low)
      5단계: 100V/100V (high / high)
  예: LIGHTQ_LEVELS=6 python -m pi.app --real

이 파일이 있으면 config.py가 읽어서
  1) 단계 순서를 실측 밝기 순으로 자동 정렬하고 (2·3단계 순서가 바뀌어도 코드 수정 없음)
  2) 판단 규칙·시뮬레이터·AI 학습이 모두 실측 투과율을 쓰게 한다.

lut.json 형식:
{
  "levels": 3,
  "combos": [["off", "off"], ["low", "off"], ["low", "low"]],
  "lux": [120.0, 260.0, 410.0],
  "ratio": [0.28, 0.63, 1.0],
  "lamp_step": 7, "measured_at": "2026-11-01T15:00"
}

수동 측정 실행 예 (3단계: 값 3개, 6단계: 값 6개):
  python -m pi.calib --lux 120 260 410 --ambient 5 --lamp-step 7
"""
import argparse
from datetime import datetime
import json
import os
from typing import List, Optional, Sequence, Tuple

DEFAULT_PATH = os.environ.get("LIGHTQ_LUT", "pi/data/lut.json")
LEVELS_6 = [("off", "off"), ("low", "off"), ("low", "low"),
            ("high", "off"), ("high", "low"), ("high", "high")]
LEVELS_3 = LEVELS_6[:3]                 # 45V만: 꺼짐/꺼짐, 45V/꺼짐, 45V/45V


def level_mode(value: Optional[str]) -> int:
    """LIGHTQ_LEVELS 값 → 3 또는 6. 비었거나 모르는 값이면 안전한 3."""
    return 6 if (value or "").strip() == "6" else 3


LEVEL_MODE = level_mode(os.environ.get("LIGHTQ_LEVELS"))
DEFAULT_LEVELS = list(LEVELS_3 if LEVEL_MODE == 3 else LEVELS_6)
VOLT = {"off": "꺼짐", "low": "45V", "high": "100V"}


def combo_name(a: str, b: str) -> str:
    return f"{VOLT[a]}/{VOLT[b]}"


ORDER_TEXT = ", ".join(combo_name(a, b) for a, b in DEFAULT_LEVELS)

class Calibration:
    """정렬이 끝난 실측 결과. levels[i]와 ratio[i]는 같은 단계(i가 클수록 밝음)."""

    def __init__(self, levels: List[Tuple[str, str]], ratio: List[float],
                 lux: List[float], ambient: float, meta: dict) -> None:
        self.levels, self.ratio, self.lux, self.ambient, self.meta = levels, ratio, lux, ambient, meta


def build(levels: Sequence[Sequence[str]], lux: Sequence[float], ambient: float = 0.0,
          meta: Optional[dict] = None) -> Calibration:
    """조합과 조도를 받아 어두운 순으로 정렬하고 상대 투과율(가장 밝은 단계 = 1.0)을 계산."""
    if len(levels) != len(lux) or len(lux) < 2:
        raise ValueError("levels와 lux 개수가 같아야 하고 2개 이상이어야 함")
    net = [max(float(x) - ambient, 0.1) for x in lux]     # 잡광을 빼야 필름 효과만 남는다
    order = sorted(range(len(net)), key=lambda i: net[i])
    top = net[order[-1]]
    return Calibration(levels=[tuple(levels[i]) for i in order],
                       ratio=[round(net[i] / top, 4) for i in order],
                       lux=[float(lux[i]) for i in order],
                       ambient=float(ambient), meta=meta or {})


def load(path: str = DEFAULT_PATH) -> Optional[Calibration]:
    """파일이 없거나 형식이 틀리면 None (그러면 기본 가정값을 쓴다)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if "lux" in d:
            levels = d.get("combos") or d.get("levels")
            if not isinstance(levels, (list, tuple)) or len(levels) != len(d["lux"]):
                levels = DEFAULT_LEVELS
            return build(levels, d["lux"], d.get("ambient_lux", 0.0), d)
        if "ratio" in d:                                   # 예전 형식: 상대 투과율만
            return Calibration(list(DEFAULT_LEVELS), [float(r) for r in d["ratio"]],
                               [], 0.0, d)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[calib] {path} 읽기 실패, 기본값 사용: {e}")
    return None


def save(path: str, lux: Sequence[float], ambient: float = 0.0,
         levels: Sequence[Sequence[str]] = DEFAULT_LEVELS, note: str = "",
         lamp_step: int = 7) -> Calibration:
    cal = build(levels, lux, ambient)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "levels": len(cal.levels),
            "combos": [list(x) for x in cal.levels],
            "combinations": [combo_name(a, b) for a, b in cal.levels],   # combos와 같은 순서
            "lux": [float(x) for x in cal.lux],
            "ratio": cal.ratio,                   # 잡광을 뺀 값. 프로그램이 실제로 쓰는 값과 같음
            "ambient_lux": ambient,
            "lamp_step": lamp_step,
            "measured_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "measured": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": note,
        }, f, ensure_ascii=False, indent=2)
    return cal


def main() -> None:
    n = len(DEFAULT_LEVELS)
    ap = argparse.ArgumentParser(description=f"단계별 실측값으로 lut.json 만들기 ({n}단계 모드, 값 순서: {ORDER_TEXT})")
    ap.add_argument("--lux", type=float, nargs="+", required=True, help=f"조합별 실내 조도 {n}개 (순서: {ORDER_TEXT})")
    ap.add_argument("--ambient", type=float, default=0.0, help="광원을 끄고 잰 실내 잡광")
    ap.add_argument("--lamp-step", type=int, default=7, help="스탠드 밝기 단계 (기본값: 7)")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=DEFAULT_PATH)
    args = ap.parse_args()
    if len(args.lux) != len(DEFAULT_LEVELS):
        ap.error(f"--lux 값은 {n}개여야 함 ({n}단계 모드, 순서: {ORDER_TEXT}). 6단계로 재려면 LIGHTQ_LEVELS=6")
    cal = save(args.out, args.lux, args.ambient, note=args.note, lamp_step=args.lamp_step)
    name = VOLT
    print(f"저장: {args.out}")
    print("정렬된 단계 (0 = 가장 어두움)")
    for i, (lv, r, x) in enumerate(zip(cal.levels, cal.ratio, cal.lux)):
        print(f"  {i}단계  A {name[lv[0]]:>4} / B {name[lv[1]]:>4}   {x:7.1f} lux   상대 투과율 {r:.3f}")
    if [tuple(x) for x in cal.levels] != list(DEFAULT_LEVELS):
        print("주의: 실측 밝기 순서가 기본 단계표와 다릅니다. 프로그램이 자동으로 이 순서를 씁니다.")
    print("다음: python -m pi.ai.retrain  (실측값으로 AI 다시 학습)")


if __name__ == "__main__":
    main()
