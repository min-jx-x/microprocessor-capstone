"""AI 모델 학습 (노트북에서 실행).

실행 (레포 최상위): python -m pi.ai.train
입력: pi/data/ai_dataset.csv (make_dataset.py 결과)
출력: config.AI_MODEL_PATH (3단계 pi/data/ai_tree.json, 6단계 pi/data/ai_tree_6level.json)  ← Pi는 이 파일만 읽는다. Pi에는 scikit-learn이 필요 없다.

모델: 결정트리 분류기. 특징 6개 → 다음 단계(0 ~ config.NUM_LEVELS-1, 3단계 모드면 0~2).
  - 규칙처럼 "if 변화율 > x 이고 필요 투과율 < y 이면 4단계" 형태라 판단 근거를 설명할 수 있다.
  - 추론은 if문 몇 번이라 Pi에서 1ms도 안 걸린다.
검증: 날짜(day) 단위로 20%를 떼어 학습에 쓰지 않은 날로 평가한다.
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from pi import config
from pi.ai.features import FEATURE_NAMES, HORIZON
from pi.control.decide import choose_level, load_lut


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

    raw = np.genfromtxt(args.data, delimiter=",", skip_header=1)
    day, X, y = raw[:, 0].astype(int), raw[:, 1:-1], raw[:, -1].astype(int)
    test = day % 5 == 0                       # 5일에 1일은 시험용
    clf = DecisionTreeClassifier(max_depth=args.depth, min_samples_leaf=20, random_state=0)
    clf.fit(X[~test], y[~test])
    acc = float((clf.predict(X[test]) == y[test]).mean())

    # 비교: 규칙은 '지금' 입사광만 보고 고른다. 같은 정답(미래 기준)에 얼마나 맞나
    lut = load_lut()
    i_t, i_c = FEATURE_NAMES.index("log_tneed"), FEATURE_NAMES.index("cur")
    rule_pred = np.array([choose_level(float(np.exp(r[i_t])), int(r[i_c]), lut) for r in X[test]])
    rule_acc = float((rule_pred == y[test]).mean())

    # 직사광이 오르는 중인 구간만 따로 (선제 차광이 의미 있는 구간)
    rising = X[test][:, FEATURE_NAMES.index("rate1")] > 0.05
    acc_r = float((clf.predict(X[test][rising]) == y[test][rising]).mean())
    rule_r = float((rule_pred[rising] == y[test][rising]).mean())

    meta = {"trained": datetime.now().strftime("%Y-%m-%d %H:%M"), "horizon": HORIZON,
            "depth": args.depth, "leaves": int(clf.get_n_leaves()),
            "train_rows": int((~test).sum()), "test_rows": int(test.sum()),
            "test_acc": round(acc, 4), "rule_acc": round(rule_acc, 4),
            "lut_source": config.LUT_SOURCE, "lut": [round(x, 4) for x in lut],
            "levels": [list(x) for x in config.LEVELS]}
    export_tree(clf, args.out, meta)

    print(f"학습 {meta['train_rows']}행 / 시험 {meta['test_rows']}행, 깊이 {args.depth}, 잎 {meta['leaves']}개")
    print(f"시험 정확도  AI {acc:.1%}  |  규칙 {rule_acc:.1%}   (정답 = {HORIZON}초 뒤 빛에 맞는 단계)")
    print(f"빛이 오르는 구간({int(rising.sum())}행)  AI {acc_r:.1%}  |  규칙 {rule_r:.1%}")
    imp = sorted(zip(FEATURE_NAMES, clf.feature_importances_), key=lambda x: -x[1])
    print("특징 중요도:", ", ".join(f"{n} {v:.2f}" for n, v in imp))
    print("저장:", args.out)


if __name__ == "__main__":
    main()
