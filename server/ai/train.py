"""결정트리를 학습하고 아두이노에서 돌릴 C 헤더(model.h)로 내보낸다.

입력 CSV 컬럼: hour, lux, cur, level  (다른 컬럼은 무시)
    python server/ai/train.py                          # 합성 데이터
    python server/ai/train.py --data data/raw/xxx.csv  # 실제 데이터

출력:
    firmware/sketches/capstone_main/model.h   (int ml_predict(float lux, int hour, int cur))
    server/ai/data/test_vectors.csv           (C 쪽 검증용 입력/기대 출력)

모델을 펌웨어에 적용하려면 capstone_main.ino 맨 위(다른 include 보다 앞)에 #define USE_ML_MODEL 을 추가한다.
주의: 우노는 SRAM 이 2KB 뿐이라 트리 깊이를 키우면 코드가 커진다. 깊이 6 정도로 시작한다.
"""
import argparse
import csv

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

FEATURES = ["lux", "hour", "cur"]  # 이 순서가 model.h 와 일치해야 한다


def load(path):
    X, y = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            X.append([float(r["lux"]), float(r["hour"]), float(r["cur"])])
            y.append(int(r["level"]))
    return np.array(X, dtype=np.float32), np.array(y)


def tree_to_c(clf) -> str:
    t = clf.tree_

    def rec(node, depth):
        pad = "  " * depth
        if t.feature[node] == -2:  # leaf
            return f"{pad}return {int(clf.classes_[t.value[node][0].argmax()])};\n"
        name = FEATURES[t.feature[node]]
        thr = float(t.threshold[node])
        s = f"{pad}if ({name} <= {thr:.6f}f) {{\n"
        s += rec(t.children_left[node], depth + 1)
        s += f"{pad}}} else {{\n"
        s += rec(t.children_right[node], depth + 1)
        s += f"{pad}}}\n"
        return s

    return (
        "#pragma once\n"
        "// 자동 생성 파일 (server/ai/train.py). 직접 수정하지 말 것.\n"
        "static inline int ml_predict(float lux_in, int hour_in, int cur_in) {\n"
        "  float lux = lux_in;\n"
        "  float hour = (float)hour_in;\n"
        "  float cur = (float)cur_in;\n"
        f"{rec(0, 1)}"
        "}\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="server/ai/data/synthetic.csv")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--out", default="firmware/sketches/capstone_main/model.h")
    ap.add_argument("--vectors", default="server/ai/data/test_vectors.csv")
    args = ap.parse_args()

    X, y = load(args.data)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
    clf = DecisionTreeClassifier(max_depth=args.depth, random_state=0).fit(Xtr, ytr)
    acc = accuracy_score(yte, clf.predict(Xte))
    print(f"test accuracy: {acc:.4f} (depth={args.depth}, 노드 {clf.tree_.node_count}개)")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(tree_to_c(clf))
    print(f"model -> {args.out}")

    with open(args.vectors, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lux", "hour", "cur", "expected"])
        for (lux, hour, cur), p in zip(Xte[:300], clf.predict(Xte[:300])):
            w.writerow([f"{lux:.4f}", int(hour), int(cur), int(p)])
    print(f"test vectors -> {args.vectors}")


if __name__ == "__main__":
    main()
