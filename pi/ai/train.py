"""AI 모델 학습 (노트북에서 실행).

실행 (레포 최상위): python -m pi.ai.train
입력: pi/data/ai_dataset.csv (make_dataset.py 결과)
출력: config.AI_MODEL_PATH (3단계 pi/data/ai_tree.json, 6단계 pi/data/ai_tree_6level.json)  ← Pi는 이 파일만 읽는다. Pi에는 scikit-learn이 필요 없다.

모델: 결정트리 분류기. 특징 6개 → 다음 단계(0 ~ config.NUM_LEVELS-1, 3단계 모드면 0~2).
  - 규칙처럼 "if 변화율 > x 이고 필요 투과율 < y 이면 4단계" 형태라 판단 근거를 설명할 수 있다.
  - 추론은 if문 몇 번이라 Pi에서 1ms도 안 걸린다.
검증: 날짜(day) 단위로 20%를 떼어 학습에 쓰지 않은 날로 평가한다.
지표: 정답의 대부분이 '가장 밝은 단계'라 전체 정확도는 과장된다(항상 가장 밝게만 해도 약 89%).
      그래서 '바꿔야 할 때 정확도'(정답이 현재 단계와 다른 순간만)를 주 지표로 본다. scores() 참고.
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np
from sklearn.metrics import balanced_accuracy_score
from sklearn.tree import DecisionTreeClassifier

from pi import config
from pi.ai.features import FEATURE_NAMES, HORIZON
from pi.control.decide import choose_level, load_lut


def load_dataset(path: str):
    """(day, X, y, test). 날짜 단위로 5일에 1일을 시험용으로 뗀다 (같은 날의 앞뒤 초가 학습·시험에 섞이지 않게)."""
    raw = np.genfromtxt(path, delimiter=",", skip_header=1)
    day, X, y = raw[:, 0].astype(int), raw[:, 1:-1], raw[:, -1].astype(int)
    return day, X, y, day % 5 == 0


def rule_predict(X, lut):
    """규칙은 '지금' 입사광(필요 투과율)만 보고 고른다. 같은 정답(미래 기준)과 비교하기 위해 특징에서 다시 계산."""
    i_t, i_c = FEATURE_NAMES.index("log_tneed"), FEATURE_NAMES.index("cur")
    return np.array([choose_level(float(np.exp(r[i_t])), int(r[i_c]), lut) for r in X])


def scores(pred, y, X) -> dict:
    """acc     : 전체 정확도
    balanced: 단계별 정확도의 평균 (적게 나오는 단계도 똑같이 셈)
    change  : 정답이 현재 단계와 다른 순간(= 단계를 바꿔야 할 때)만 본 정확도  ← 주 지표
    rising  : 빛이 오르는 중인 순간(최근 변화율 > 5%)만 본 정확도 (선제 차광이 필요한 때)"""
    cur = X[:, FEATURE_NAMES.index("cur")].astype(int)
    change = y != cur
    rising = X[:, FEATURE_NAMES.index("rate1")] > 0.05
    return {"acc": float((pred == y).mean()),
            "balanced": float(balanced_accuracy_score(y, pred)),
            "change": float((pred[change] == y[change]).mean()),
            "rising": float((pred[rising] == y[rising]).mean())}


def make_tree(depth: int = 8) -> DecisionTreeClassifier:
    return DecisionTreeClassifier(max_depth=depth, min_samples_leaf=20, random_state=0)


def export_tree(clf, path: str, meta: dict) -> None:
    t = clf.tree_
    model = {
        "features": FEATURE_NAMES,
        "classes": [int(c) for c in clf.classes_],
        "left": t.children_left.tolist(),
        "right": t.children_right.tolist(),
        "feature": t.feature.tolist(),
        "threshold": [round(float(x), 6) for x in t.threshold],
        "leaf_class": [int(np.argmax(v)) for v in t.value[:, 0, :]],
        "meta": meta,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="pi/data/ai_dataset.csv")
    ap.add_argument("--out", default=config.AI_MODEL_PATH)
    ap.add_argument("--depth", type=int, default=8)
    args = ap.parse_args()

    day, X, y, test = load_dataset(args.data)
    clf = make_tree(args.depth)
    clf.fit(X[~test], y[~test])
    lut = load_lut()
    ai = scores(clf.predict(X[test]), y[test], X[test])
    rule = scores(rule_predict(X[test], lut), y[test], X[test])

    meta = {"trained": datetime.now().strftime("%Y-%m-%d %H:%M"), "horizon": HORIZON,
            "depth": args.depth, "leaves": int(clf.get_n_leaves()),
            "train_rows": int((~test).sum()), "test_rows": int(test.sum()),
            "test_acc": round(ai["acc"], 4), "rule_acc": round(rule["acc"], 4),
            "change_acc": round(ai["change"], 4), "rule_change_acc": round(rule["change"], 4),
            "lut_source": config.LUT_SOURCE, "lut": [round(x, 4) for x in lut],
            "levels": [list(x) for x in config.LEVELS]}
    export_tree(clf, args.out, meta)

    print(f"학습 {meta['train_rows']}행 / 시험 {meta['test_rows']}행, 깊이 {args.depth}, 잎 {meta['leaves']}개")
    print(f"(정답 = {HORIZON}초 뒤 빛에 맞는 단계)      AI      규칙")
    for k, name in (("change", "바꿔야 할 때 정확도"), ("rising", "빛이 오르는 중"),
                    ("balanced", "단계별 평균"), ("acc", "전체 정확도")):
        print(f"  {name:<14} {ai[k]:>8.1%} {rule[k]:>8.1%}")
    imp = sorted(zip(FEATURE_NAMES, clf.feature_importances_), key=lambda x: -x[1])
    print("특징 중요도:", ", ".join(f"{n} {v:.2f}" for n, v in imp))
    print("저장:", args.out)


if __name__ == "__main__":
    main()
