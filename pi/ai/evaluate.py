"""규칙 대 AI 비교 (노트북에서 실행).

실행 (레포 최상위): python -m pi.ai.evaluate --days 30
학습에 안 쓴 seed로 같은 하루를 규칙과 AI로 한 번씩 돌려 지표를 비교한다.
같은 seed라 바깥 빛·구름·직사광·센서 잡음이 똑같다.

지표 (목표가 있는 시간대만)
  정확도    : 실내 조도가 목표 ±20% 안에 든 비율
  MAPE      : 목표 대비 평균 절대 오차율
  눈부심    : 실내 조도가 목표의 1.3배를 넘은 회차 수 (적을수록 좋음)
  전환 횟수 : 단계가 바뀐 횟수 (적을수록 덜 깜빡임)
  반응 지연 : 직사광이 오르기 시작한 뒤 어둡게 바꿀 때까지 걸린 회차(초)
"""
import argparse
import csv
import os
import random
import statistics

from pi import config
from pi.ai.kma import load_profiles, pick
from pi.ai.offline import run_day
from pi.ai.policy import AIPolicy
from pi.control.decide import RulePolicy, load_lut

TOL, GLARE = 0.20, 1.3


def metrics(rows, bursts):
    day = [r for r in rows if r["target"] is not None]
    err = [abs(r["lux"] - r["target"]) / r["target"] for r in day]
    switches = sum(1 for a, b in zip(rows, rows[1:]) if a["level"] != b["level"])
    delays = []
    for s in bursts:
        lv0 = rows[s]["level"]
        d = next((k for k in range(1, 25) if s + k < len(rows) and rows[s + k]["level"] < lv0), None)
        if d is not None:
            delays.append(d)
    return {"acc": sum(e <= TOL for e in err) / max(len(err), 1),
            "mape": statistics.mean(err) if err else 0.0,
            "glare": sum(r["lux"] > r["target"] * GLARE for r in day),
            "switches": switches,
            "delay": statistics.mean(delays) if delays else float("nan")}


def save_log(rows, path):
    """tools/metrics.py 형식(ms, hour, lux, level)"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ms", "hour", "lux", "level"])
        for r in rows:
            w.writerow([r["i"] * 1000, int(r["hour"]), r["lux"], r["level"]])


METRIC_ROWS = (("acc", "정확도(±20%)", "{:.1%}"), ("mape", "MAPE", "{:.1%}"),
               ("glare", "눈부심 회차/일", "{:.1f}"), ("switches", "전환 횟수/일", "{:.1f}"),
               ("delay", "반응 지연(초)", "{:.2f}"))


def compare(days: int = 40, seed: int = 777, speed: float = 720,
            model: str = config.AI_MODEL_PATH, logdir: str = None) -> dict:
    """같은 날들을 규칙과 AI로 돌려 지표 평균을 돌려준다. {"rule": {...}, "ai": {...}}"""
    lut = load_lut()
    profiles = load_profiles()
    rule, ai = RulePolicy(lut), AIPolicy(lut, model)
    rng = random.Random(seed)
    res = {"rule": [], "ai": []}
    for d in range(days):
        kw = dict(profile=pick(profiles, d) if profiles and d % 3 else None,
                  dt_s=speed, seed=seed * 1000 + d,
                  wake_hour=rng.uniform(6.5, 8.5), bursts=rng.randint(4, 10))
        for name, pol in (("rule", rule), ("ai", ai)):
            rows, bursts = run_day(pol, **kw)
            res[name].append(metrics(rows, bursts))
            if d == 0 and logdir:
                save_log(rows, os.path.join(logdir, f"eval_{name}.csv"))

    def avg(name, k):
        v = [m[k] for m in res[name] if m[k] == m[k]]   # NaN 제외
        return statistics.mean(v) if v else float("nan")

    return {name: {k: avg(name, k) for k, _, _ in METRIC_ROWS} for name in res}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=777)     # 학습(seed 0)과 다른 날들
    ap.add_argument("--speed", type=float, default=720)
    ap.add_argument("--model", default=config.AI_MODEL_PATH)
    ap.add_argument("--logdir", default="pi/data")
    args = ap.parse_args()

    r = compare(args.days, args.seed, args.speed, args.model, args.logdir)
    print(f"{args.days}일 비교 (배속 {args.speed:g}, 직사광 하루 4~10번)")
    print(f"{'지표':<14}{'규칙':>10}{'AI':>10}")
    for k, label, fmt in METRIC_ROWS:
        print(f"{label:<14}{fmt.format(r['rule'][k]):>10}{fmt.format(r['ai'][k]):>10}")
    print(f"첫째 날 로그: {args.logdir}/eval_rule.csv, eval_ai.csv (tools/metrics.py 형식)")


if __name__ == "__main__":
    main()
