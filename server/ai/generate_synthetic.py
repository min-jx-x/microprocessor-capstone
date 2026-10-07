"""합성 학습 데이터를 만든다. (실제 데이터 수집 전 파이프라인 점검용)

임의의 입사광과 현재 단계를 뽑고, lux = 입사광 * T[현재 단계] 로 측정값을 만든 뒤
decision.h 의 규칙(decide_rule)과 같은 규칙으로 다음 단계(level)를 라벨로 붙인다.
따라서 이 데이터로 학습한 모델은 규칙을 흉내 낼 뿐이다. AI가 맡을 역할이 정해지면 교체할 것.

사용법 (저장소 루트에서):
    python server/ai/generate_synthetic.py
"""
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from params_loader import decide_rule, load_params  # noqa: E402


def main(n=5000, seed=0, out="server/ai/data/synthetic.csv"):
    p = load_params()
    rng = np.random.default_rng(seed)
    hours = rng.integers(0, 24, size=n)
    curs = rng.integers(0, p["NUM_LEVELS"], size=n)
    incident = np.exp(rng.uniform(np.log(1.0), np.log(5000.0), size=n))  # 입사광 1 ~ 5000 lux (로그 균등)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hour", "lux", "cur", "level"])
        for h, c, inc in zip(hours, curs, incident):
            lux = round(float(inc) * float(p["LUT_T"][int(c)]), 1)
            w.writerow([int(h), lux, int(c), decide_rule(p, lux, int(h), int(c))])
    print(f"{n} rows -> {out}")


if __name__ == "__main__":
    main()
