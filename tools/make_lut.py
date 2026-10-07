"""캘리브레이션 측정값(구동값 vs lux)으로 룩업테이블을 만든다.

입력 CSV: 줄마다 "drive,lux" (calibration_sweep 스케치 출력). '#'로 시작하는 줄과 숫자가 아닌 줄은 무시.
    python tools/make_lut.py data/raw/sweep.csv --levels 5
    python tools/make_lut.py data/raw/sweep.csv --levels 5 --ref-lux 850   # 필름 없이 잰 기준 lux가 있을 때

방식:
  - 투과율 T = lux / 기준 lux.  --ref-lux 가 없으면 가장 밝은 측정값을 기준(1.0)으로 하는 "상대 투과율"이다.
    (절대 투과율은 필름을 치우고 같은 위치에서 잰 기준 lux가 필요하다.)
  - 구동값이 커질수록 투과율이 커진다고 가정하고, 단조 증가가 되도록 보정한다.
  - 최소~최대 투과율 구간을 단계 수만큼 "투과율 기준으로 균등하게" 나누고,
    각 목표 투과율에 가장 가까운 측정점의 구동값을 고른다.
출력: params.h 에 붙여넣을 LUT_T / LUT_PWM 배열 (탭 방식이면 구동값 열은 직접 채운다).
"""
import argparse
import sys


def read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return sorted(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--levels", type=int, default=5)
    ap.add_argument("--ref-lux", type=float, default=None)
    args = ap.parse_args()

    rows = read_rows(args.path)
    if len(rows) < args.levels:
        print(f"측정점({len(rows)}개)이 단계 수({args.levels})보다 적음")
        sys.exit(1)

    denom = args.ref_lux if args.ref_lux else max(l for _, l in rows)
    if denom <= 0:
        print("기준 lux가 0 이하")
        sys.exit(1)
    kind = "절대" if args.ref_lux else "상대(최대 측정값 = 1.0)"

    drives = [d for d, _ in rows]
    raw_T = [l / denom for _, l in rows]
    T, run = [], 0.0
    for t in raw_T:
        run = max(run, t)
        T.append(run)
    if any(abs(a - b) > 1e-9 for a, b in zip(raw_T, T)):
        print("경고: 측정값이 단조 증가가 아니어서 보정했음. 측정을 다시 확인할 것 (센서/광원 흔들림, 필름 안정화 시간)")

    t_min, t_max = T[0], T[-1]
    if t_max - t_min < 0.1:
        print(f"경고: 투과율 범위가 너무 좁음 ({t_min:.3f} ~ {t_max:.3f}). 단계 분할이 의미 없을 수 있음")

    n = args.levels
    targets = [t_min + (t_max - t_min) * i / (n - 1) for i in range(n)]
    picks = []
    for tg in targets:
        idx = min(range(len(T)), key=lambda i: abs(T[i] - tg))
        picks.append(idx)

    if len(set(drives[i] for i in picks)) < n:
        print("경고: 서로 다른 단계가 같은 구동값으로 합쳐짐. 측정점을 더 촘촘히 하거나 단계 수를 줄일 것")

    print(f"// 투과율 종류: {kind}")
    print(f"// 목표 투과율: {', '.join(f'{t:.3f}' for t in targets)}")
    print("static const float LUT_T[NUM_LEVELS] = {" + ", ".join(f"{T[i]:.3f}f" for i in picks) + "};")
    print("static const int LUT_PWM[NUM_LEVELS] = {" + ", ".join(str(int(round(drives[i]))) for i in picks) + "};")
    print("// LUT_TAP (탭 방식)은 단계별 릴레이 채널 번호를 직접 채울 것")


if __name__ == "__main__":
    main()
