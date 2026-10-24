"""단계별 실측값(lut.json) 읽기·쓰기.

필름을 조립한 뒤, 같은 광원(LED 스탠드)에서 6가지 조합마다 실내 조도를 재서 저장한다.
이 파일이 있으면 config.py가 읽어서
  1) 단계 순서를 실측 밝기 순으로 자동 정렬하고 (2·3단계 순서가 바뀌어도 코드 수정 없음)
  2) 판단 규칙·시뮬레이터·AI 학습이 모두 실측 투과율을 쓰게 한다.

lut.json 형식
{
  "levels": [["off","off"], ["low","off"], ["low","low"], ["high","off"], ["high","low"], ["high","high"]],
  "lux":    [182, 279, 410, 475, 715, 1273],   같은 광원에서 각 조합의 실내 조도
  "ambient_lux": 5,                            광원을 끄고 잰 실내 잡광 (빼고 계산)
  "measured": "2026-10-28 15:00", "note": "LED 스탠드 10단계, 거리 30cm"
}

손으로 잰 값으로 바로 만들기 (웹 수동 모드로 0~5단계를 하나씩 켜고 화면의 실내 조도를 적는다):
  python -m pi.calib --lux 182 279 410 475 715 1273 --ambient 5 --note "LED 30cm"
값 순서는 config.py 기본 단계표 순서(꺼짐/꺼짐, 45V/꺼짐, 45V/45V, 100V/꺼짐, 100V/45V, 100V/100V).

주의: 이 파일은 config를 import하지 않는다 (config가 이 파일을 쓰기 때문).
"""
import argparse
import json
import os
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

DEFAULT_PATH = os.environ.get("LIGHTQ_LUT", "pi/data/lut.json")
DEFAULT_LEVELS = [("off", "off"), ("low", "off"), ("low", "low"),
                  ("high", "off"), ("high", "low"), ("high", "high")]


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
            return build(d.get("levels", DEFAULT_LEVELS), d["lux"], d.get("ambient_lux", 0.0), d)
        if "ratio" in d:                                   # 예전 형식: 상대 투과율만
            return Calibration(list(DEFAULT_LEVELS), [float(r) for r in d["ratio"]],
                               [], 0.0, d)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[calib] {path} 읽기 실패, 기본값 사용: {e}")
    return None


def save(path: str, lux: Sequence[float], ambient: float = 0.0,
         levels: Sequence[Sequence[str]] = DEFAULT_LEVELS, note: str = "") -> Calibration:
    cal = build(levels, lux, ambient)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"levels": [list(x) for x in levels], "lux": list(lux), "ambient_lux": ambient,
                   "measured": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": note},
                  f, ensure_ascii=False, indent=2)
    return cal


def main() -> None:
    ap = argparse.ArgumentParser(description="단계별 실측값으로 lut.json 만들기")
    ap.add_argument("--lux", type=float, nargs="+", required=True, help="조합별 실내 조도 (기본 단계표 순서)")
    ap.add_argument("--ambient", type=float, default=0.0, help="광원을 끄고 잰 실내 잡광")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=DEFAULT_PATH)
    args = ap.parse_args()
    if len(args.lux) != len(DEFAULT_LEVELS):
        ap.error(f"--lux 값은 {len(DEFAULT_LEVELS)}개여야 함")
    cal = save(args.out, args.lux, args.ambient, note=args.note)
    name = {"off": "꺼짐", "low": "45V", "high": "100V"}
    print(f"저장: {args.out}")
    print("정렬된 단계 (0 = 가장 어두움)")
    for i, (lv, r, x) in enumerate(zip(cal.levels, cal.ratio, cal.lux)):
        print(f"  {i}단계  A {name[lv[0]]:>4} / B {name[lv[1]]:>4}   {x:7.1f} lux   상대 투과율 {r:.3f}")
    if [tuple(x) for x in cal.levels] != list(DEFAULT_LEVELS):
        print("주의: 실측 밝기 순서가 기본 단계표와 다릅니다. 프로그램이 자동으로 이 순서를 씁니다.")
    print("다음: python -m pi.ai.retrain  (실측값으로 AI 다시 학습)")


if __name__ == "__main__":
    main()
