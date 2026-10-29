"""모델 선택 근거 실험 (노트북에서 실행).

실행 (레포 최상위): python -m pi.ai.compare_models
결과: config.AI_REPORT_PATH (3단계 pi/data/ai_report.json)  ← 웹 'AI 설명' 페이지(/ai)가 읽는다.

"왜 결정트리인가, 왜 깊이 8인가, 왜 4초 앞인가, AI는 무엇을 보고 판단하나"에 숫자로 답한다.
  1. 모델 비교   : 같은 데이터·같은 시험 날짜로 다른 모델과 기준선(항상 가장 밝게, 현재 유지, 규칙)
  2. 트리 깊이   : 깊이를 바꾸며 정확도와 잎 개수(= 설명해야 할 규칙 수)
  3. 특징 빼기   : 특징을 하나씩 빼고 다시 학습해 각 특징이 맡은 역할
  4. 예측 시간   : 정답을 몇 초 뒤 빛으로 정할지 바꿔 학습하고, 제어 루프에 넣어 직사광 반응을 비교
지표는 train.py의 scores()와 같다. 주 지표는 '바꿔야 할 때 정확도'.
"""
import argparse
import json
import os
import pickle
import tempfile
from datetime import datetime

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pi import config
from pi.ai.evaluate import compare
from pi.ai.features import FEATURE_LABELS, FEATURE_NAMES, HORIZON
from pi.ai.make_dataset import label_rows, simulate_days
from pi.ai.offline import burst_stats
from pi.ai.policy import AIPolicy
from pi.ai.train import export_tree, load_dataset, make_tree, rule_predict, scores
from pi.control.decide import RulePolicy, load_lut

DEPTH = 8                      # 지금 쓰는 트리 깊이 (train.py 기본값)
DEPTHS = [2, 3, 4, 5, 6, 8, 10, 12, 16]
HORIZONS = [1, 2, 4, 6, 8]

# (키, 이름, 만들기, Pi에 올리는 방법, 설명할 수 있나)
MODELS = [
    ("tree", f"결정트리 (깊이 {DEPTH}, 현재)", lambda: make_tree(DEPTH),
     "JSON 파일 하나, if문 몇 번", "지나온 질문 경로가 곧 판단 근거"),
    ("logistic", "로지스틱 회귀", lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
     "가중치 몇 개", "가중치는 보이지만 경계가 직선뿐이라 부족"),
    ("knn", "k-최근접 이웃 (k=15)", lambda: make_pipeline(StandardScaler(), KNeighborsClassifier(15)),
     "학습 데이터 전체를 들고 다녀야 함", "비슷한 과거 사례를 보여 줄 수는 있음"),
    ("forest", "랜덤포레스트 (100그루)",
     lambda: RandomForestClassifier(100, max_depth=12, min_samples_leaf=5, n_jobs=-1, random_state=0),
     "트리 100개, scikit-learn 필요", "트리 100개의 투표라 경로 하나로 설명 불가"),
    ("boost", "그래디언트 부스팅", lambda: GradientBoostingClassifier(random_state=0),
     "트리 수백 개, scikit-learn 필요", "트리 수백 개의 합이라 설명 어려움"),
    ("mlp", "신경망 (MLP 32×32)",
     lambda: make_pipeline(StandardScaler(), MLPClassifier((32, 32), max_iter=300, random_state=0)),
     "가중치 행렬, 행렬 곱 구현 필요", "판단 근거를 사람이 읽기 어려움"),
]
ABLATIONS = [  # (빼는 특징들, 이름)
    (["rate1", "rate2", "rate3"], "빛 변화율 3개"),
    (["log_tneed"], "필요 투과율"),
    (["target"], "목표 조도"),
    (["cur"], "현재 단계"),
]


def rounded(d: dict) -> dict:
    return {k: round(v, 5) if isinstance(v, float) else v for k, v in d.items()}


def model_rows(X, y, test, lut):
    Xtr, ytr, Xte, yte = X[~test], y[~test], X[test], y[test]
    cur = Xte[:, FEATURE_NAMES.index("cur")].astype(int)
    top = config.NUM_LEVELS - 1
    rows = [
        dict(key="always_top", name="항상 가장 밝게", baseline=True, **scores(np.full_like(yte, top), yte, Xte)),
        dict(key="keep", name="지금 단계 유지", baseline=True, **scores(cur, yte, Xte)),
        dict(key="rule", name="규칙 (지금 빛만 봄)", baseline=True, **scores(rule_predict(Xte, lut), yte, Xte)),
    ]
    for key, name, make, deploy, explain in MODELS:
        print(f"  학습: {name}", flush=True)
        m = make().fit(Xtr, ytr)
        if key == "tree":            # Pi에 실제로 올리는 형식(JSON) 크기
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "t.json")
                export_tree(m, p, {})
                kb = os.path.getsize(p) / 1024
        else:
            kb = len(pickle.dumps(m)) / 1024
        rows.append(dict(key=key, name=name, baseline=False, size_kb=round(kb, 1), deploy=deploy,
                         explain=explain, current=key == "tree", **scores(m.predict(Xte), yte, Xte)))
    return [rounded(r) for r in rows]


def depth_rows(X, y, test):
    out = []
    for d in DEPTHS:
        m = make_tree(d).fit(X[~test], y[~test])
        s = scores(m.predict(X[test]), y[test], X[test])
        s_train = scores(m.predict(X[~test]), y[~test], X[~test])
        out.append(rounded(dict(depth=d, leaves=int(m.get_n_leaves()), train_change=s_train["change"], **s)))
    return out


def ablation_rows(X, y, test):
    full = make_tree(DEPTH).fit(X[~test], y[~test])
    out = [rounded(dict(drop=[], name="없음 (전체 사용)", **scores(full.predict(X[test]), y[test], X[test])))]
    for drop, name in ABLATIONS:
        keep = [i for i, n in enumerate(FEATURE_NAMES) if n not in drop]
        m = make_tree(DEPTH).fit(X[~test][:, keep], y[~test])
        out.append(rounded(dict(drop=drop, name=name, **scores(m.predict(X[test][:, keep]), y[test], X[test]))))
    importance = [{"feature": n, "label": FEATURE_LABELS[n], "value": round(float(v), 4)}
                  for n, v in zip(FEATURE_NAMES, full.feature_importances_)]
    return out, sorted(importance, key=lambda r: -r["value"])


def horizon_rows(days, lut, sim_days: int, eval_days: int, scenes: int):
    """예측 시간마다 정답을 다시 만들어 학습하고, 실제 제어(안정화 포함)에 넣어 결과를 본다."""
    out = []
    for h in HORIZONS:
        data = np.array([r for day, rows in days for r in label_rows(rows, lut, day, horizon=h)], dtype=float)
        day, X, y = data[:, 0].astype(int), data[:, 1:-1], data[:, -1].astype(int)
        test = day % 5 == 0
        m = make_tree(DEPTH).fit(X[~test], y[~test])
        offline = scores(m.predict(X[test]), y[test], X[test])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.json")
            export_tree(m, p, {"lut": [round(x, 4) for x in lut], "levels": [list(x) for x in config.LEVELS]})
            burst = burst_stats(AIPolicy(lut, p), scenes)
            daily = compare(days=eval_days, model=p)["ai"]
        print(f"  예측 {h}초: 직사광 반응 {burst['delay']:.2f}초, 눈부심 {burst['glare']:.2f}초, "
              f"하루 전환 {daily['switches']:.1f}회", flush=True)
        out.append(rounded(dict(horizon=h, current=h == HORIZON, change=offline["change"],
                                burst_delay=burst["delay"], burst_glare=burst["glare"],
                                day_glare=daily["glare"], day_switches=daily["switches"],
                                day_delay=daily["delay"], day_acc=daily["acc"])))
    rb = burst_stats(RulePolicy(lut), scenes)
    rd = compare(days=eval_days, model=config.AI_MODEL_PATH)["rule"]
    rule = rounded(dict(burst_delay=rb["delay"], burst_glare=rb["glare"], day_glare=rd["glare"],
                        day_switches=rd["switches"], day_delay=rd["delay"], day_acc=rd["acc"]))
    return out, rule


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="pi/data/ai_dataset.csv")
    ap.add_argument("--out", default=config.AI_REPORT_PATH)
    ap.add_argument("--sim-days", type=int, default=300, help="예측 시간 비교용 학습 일수 (make_dataset과 같게)")
    ap.add_argument("--eval-days", type=int, default=40)
    ap.add_argument("--scenes", type=int, default=40, help="직사광 장면 평균 횟수")
    args = ap.parse_args()

    lut = load_lut()
    day, X, y, test = load_dataset(args.data)
    print("1/4 모델 비교", flush=True)
    models = model_rows(X, y, test, lut)
    print("2/4 트리 깊이", flush=True)
    depth = depth_rows(X, y, test)
    print("3/4 특징 빼기", flush=True)
    ablation, importance = ablation_rows(X, y, test)
    print("4/4 예측 시간", flush=True)
    horizon, horizon_rule = horizon_rows(simulate_days(args.sim_days, 0, lut), lut,
                                         args.sim_days, args.eval_days, args.scenes)

    report = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "levels": config.NUM_LEVELS, "lut": [round(x, 4) for x in lut], "lut_source": config.LUT_SOURCE,
        "dataset": {"rows": int(len(y)), "train_rows": int((~test).sum()), "test_rows": int(test.sum()),
                    "label_share": [round(float((y == k).mean()), 4) for k in range(config.NUM_LEVELS)]},
        "current": {"depth": DEPTH, "horizon": HORIZON},
        "stabilizer": {"stable_count": config.STABLE_COUNT, "min_interval_s": config.MIN_SWITCH_INTERVAL_S},
        "models": models, "depth": depth, "ablation": ablation, "importance": importance,
        "horizon": horizon, "horizon_rule": horizon_rule,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print(f"\n{'모델':<24}{'바꿔야 할 때':>10}{'오르는 중':>9}{'단계 평균':>9}{'전체':>8}{'크기 KB':>9}")
    for r in models:
        kb = f"{r['size_kb']:.0f}" if "size_kb" in r else "-"
        print(f"{r['name']:<24}{r['change']:>10.1%}{r['rising']:>9.1%}{r['balanced']:>9.1%}{r['acc']:>8.1%}{kb:>9}")
    print("\n깊이  잎   바꿔야 할 때(시험/학습)")
    for r in depth:
        print(f"{r['depth']:>4} {r['leaves']:>4}   {r['change']:.1%} / {r['train_change']:.1%}")
    print("\n뺀 특징            바꿔야 할 때  오르는 중")
    for r in ablation:
        print(f"{r['name']:<16}{r['change']:>10.1%}{r['rising']:>10.1%}")
    print(f"\n예측(초)  직사광 반응  눈부심   하루 전환   (규칙: {horizon_rule['burst_delay']:.2f}초, "
          f"{horizon_rule['burst_glare']:.2f}초, {horizon_rule['day_switches']:.1f}회)")
    for r in horizon:
        print(f"{r['horizon']:>6}{r['burst_delay']:>11.2f}{r['burst_glare']:>9.2f}{r['day_switches']:>10.1f}")
    print("\n저장:", args.out)


if __name__ == "__main__":
    main()
