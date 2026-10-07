"""수집한 로그 CSV(ms,hour,lux,level)를 점검한다. (표준 라이브러리만 사용)

사용법:
    python tools/validate_csv.py data/raw/log_xxx.csv [--levels 5]
"""
import argparse
import csv
import statistics
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--levels", type=int, default=5, help="단계 수 (params.h 의 NUM_LEVELS)")
    args = ap.parse_args()

    problems, rows = [], []
    with open(args.path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = ["ms", "hour", "lux", "level"]
        if reader.fieldnames != expected:
            print(f"헤더가 다름: {reader.fieldnames} (기대: {expected})")
            sys.exit(1)
        for i, r in enumerate(reader, start=2):
            try:
                ms, hour, lux, level = int(r["ms"]), int(r["hour"]), float(r["lux"]), int(r["level"])
            except (ValueError, TypeError):
                problems.append(f"line {i}: 숫자 변환 실패 {r}")
                continue
            if not 0 <= hour <= 23:
                problems.append(f"line {i}: hour 범위 밖 {hour}")
            if not 0 <= lux <= 100000:
                problems.append(f"line {i}: lux 이상값 {lux}")
            if not 0 <= level < args.levels:
                problems.append(f"line {i}: level 범위 밖 {level} (0~{args.levels - 1})")
            rows.append((ms, hour, lux, level))

    if not rows:
        print("유효한 행이 없음")
        sys.exit(1)

    gaps = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    if any(g <= 0 for g in gaps):
        problems.append("ms가 증가하지 않는 구간이 있음 (보드 재시작 가능성)")
    pos = [g for g in gaps if g > 0]
    if pos:
        med = statistics.median(pos)
        big = [g for g in pos if g > 5 * med]
        if big:
            problems.append(f"측정 간격이 중앙값({med}ms)의 5배 넘는 구간 {len(big)}곳 (끊김 가능성)")

    luxes = [r[2] for r in rows]
    print(f"행 수: {len(rows)}")
    print(f"lux 최소/중앙/최대: {min(luxes):.1f} / {statistics.median(luxes):.1f} / {max(luxes):.1f}")
    counts = {lv: sum(1 for r in rows if r[3] == lv) for lv in range(args.levels)}
    print(f"단계별 행 수: {counts}")
    print(f"hour 분포: {sorted(set(r[1] for r in rows))}")
    if problems:
        print(f"\n문제 {len(problems)}건 (최대 20건 표시):")
        for p in problems[:20]:
            print(" -", p)
        sys.exit(2)
    print("\n문제 없음")


if __name__ == "__main__":
    main()
