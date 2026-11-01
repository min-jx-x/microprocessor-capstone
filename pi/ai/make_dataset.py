"""AI 학습 데이터 만들기.

실행 (레포 최상위): python -m pi.ai.make_dataset --days 300
결과: pi/data/ai_dataset.csv

하루마다 조건을 섞는다.
  - 바깥 빛 곡선: 기상청 일사량 곡선(data/OBS_ASOS*.csv) 또는 사인 곡선
  - 배속: 1회당 가상 2분 / 5분 / 12분 (시연 배속이 달라도 동작하도록)
  - 기상 시각: 06:30 ~ 08:30
  - 직사광: 하루 3~10번, 오르는 속도와 세기 무작위
운전은 규칙 판단으로 하되, 가끔 임의 단계를 넣어 여러 단계 상황이 고루 나오게 한다.

잡음 증강: 학습용 날(시험용이 아닌 날)마다 센서 값(raw lux)에 표준편차 AUG_NOISE(2%) 잡음을 더하고
제어 루프와 같은 중앙값 평활을 다시 거친 복사본을 AUG_COPIES개 더 넣는다. 정답은 원본과 같다.
(시뮬레이터 센서에는 원래 ±2% 균등 잡음이 있다. 증강은 그 위에 더 얹는 것)

정답(label)은 'HORIZON회 뒤 실제 입사광'에 맞는 단계다.
시뮬레이터는 미래 값을 알고 있으므로 정답을 만들 수 있고,
모델은 과거 4회의 변화만 보고 그 정답을 맞히도록 배운다.
"""
import argparse
import csv
import os
import random

from pi import config
from pi.ai.features import FEATURE_NAMES, HISTORY, HORIZON, make_features
from pi.ai.kma import load_profiles, pick
from pi.ai.offline import AMBIENT_LUX, run_day, sim_transmittance
from pi.control.decide import RulePolicy, choose_level, incident_of, load_lut
from pi.control.filter import LuxMedian

AUG_NOISE = 0.02      # 증강 잡음 (표준편차 비율)
AUG_COPIES = 1        # 학습용 날마다 잡음 복사본 수


def label_rows(rows, lut, day, horizon: int = HORIZON):
    """horizon: 몇 회 뒤 빛으로 정답을 정할지. 예측 시간 비교(compare_models.py)에서 바꿔 본다."""
    out = []
    incs = [incident_of(r.get("lux_in", r["lux"]), r["level"], lut) for r in rows]   # 판단에 쓴 값(평활 후)
    for i in range(HISTORY - 1, len(rows) - horizon):
        r = rows[i]
        if r["target"] is None:          # 저녁·취침은 AI가 판단하지 않음
            continue
        cur = r["level"]
        future_out = rows[i + horizon]["outdoor"]          # 시뮬레이터만 아는 미래 바깥 빛
        inc_future = (future_out * sim_transmittance(cur) + AMBIENT_LUX) / lut[cur]
        label = choose_level(r["target"] / max(inc_future, 1.0), cur, lut)
        feats = make_features(r["target"], incs[i - HISTORY + 1:i + 1], cur)
        out.append([day] + [round(x, 5) for x in feats] + [label])
    return out


def with_noise(rows, noise: float, rng: random.Random):
    """raw lux에 잡음을 더하고 제어 루프와 같은 중앙값 평활을 다시 거친 복사본."""
    filt, out = LuxMedian(), []
    for r in rows:
        lux = r["lux"] * (1.0 + rng.gauss(0.0, noise))
        out.append(dict(r, lux=lux, lux_in=filt.add(r["level"], lux)))
    return out


def augmented(days, noise: float = AUG_NOISE, copies: int = AUG_COPIES, seed: int = 0):
    """원본 날들 + 학습용 날(day % 5 != 0)의 잡음 복사본. 시험용 날은 그대로 둬서 시험 결과를 비교할 수 있게."""
    rng = random.Random(seed + 7)
    out = list(days)
    for day, rows in days:
        if day % 5 != 0:
            out += [(day, with_noise(rows, noise, rng)) for _ in range(copies)]
    return out


def simulate_days(days: int, seed: int, lut):
    """학습용 하루 기록들을 만든다. [(day, rows), ...]  같은 seed면 항상 같은 결과."""
    profiles = load_profiles()
    rng = random.Random(seed)
    out = []
    for day in range(days):
        use_kma = profiles and rng.random() < 0.7
        rows, _ = run_day(RulePolicy(lut),
                          profile=pick(profiles, rng.randrange(1000)) if use_kma else None,
                          dt_s=rng.choice([120, 300, 720]),
                          seed=seed * 100000 + day,
                          wake_hour=rng.uniform(6.5, 8.5),
                          bursts=rng.randint(3, 10),
                          explore=0.03)
        out.append((day, rows))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="pi/data/ai_dataset.csv")
    ap.add_argument("--aug-noise", type=float, default=AUG_NOISE, help="증강 잡음 표준편차 비율 (0이면 증강 안 함)")
    ap.add_argument("--aug-copies", type=int, default=AUG_COPIES)
    args = ap.parse_args()

    lut = load_lut()
    profiles = load_profiles()
    rows_out = []
    days = simulate_days(args.days, args.seed, lut)
    if args.aug_noise > 0 and args.aug_copies > 0:
        days = augmented(days, args.aug_noise, args.aug_copies, args.seed)
    for day, rows in days:
        rows_out += label_rows(rows, lut, day)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day"] + FEATURE_NAMES + ["label"])
        w.writerows(rows_out)
    counts = [sum(1 for r in rows_out if r[-1] == k) for k in range(config.NUM_LEVELS)]
    print(f"{args.days}일, {len(rows_out)}행 -> {args.out}  (잡음 증강 {args.aug_noise:.0%} × {args.aug_copies}개, 학습용 날만)")
    print("정답 단계 분포:", {k: c for k, c in enumerate(counts)})
    print(f"기상청 곡선 {len(profiles)}개 사용" if profiles else "기상청 파일 없음: 사인 곡선만 사용")


if __name__ == "__main__":
    main()
