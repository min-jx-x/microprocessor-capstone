"""의도 분류기 학습 (노트북에서 실행, scikit-learn 필요).

실행 (레포 최상위): python -m pi.voice.train
입력: pi/data/voice_intents.csv  (split, intent, text)  ← 예문을 추가하고 다시 실행하면 된다
출력: config.VOICE_MODEL_PATH (pi/data/intent_model.json)  ← Pi는 이 파일만 읽는다
      config.VOICE_REPORT_PATH (pi/data/voice_report.json) ← 시험 예문 정확도, 확신도 기준별 결과

모델: 글자 1~3개 묶음(n-gram) TF-IDF + 로지스틱 회귀.
  - 단어 대신 글자 묶음을 써서 띄어쓰기·어미가 달라도('해줘'/'해 줘'/'해줄래') 비슷하게 인식한다.
  - 추론은 곱셈·덧셈 몇백 번이라 Pi에서 1ms 안팎.
검증: split=test 예문은 학습에 쓰지 않고 정확도만 잰다.
"""
import argparse
import csv
import json
from datetime import datetime

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix

from pi import config
from pi.voice.intent import IntentModel
from pi.voice.text import char_ngrams


def load(path: str):
    rows = {"train": ([], []), "test": ([], [])}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            xs, ys = rows[r["split"]]
            xs.append(r["text"])
            ys.append(r["intent"])
    return rows["train"], rows["test"]


def export(vec: TfidfVectorizer, clf: LogisticRegression, path: str, meta: dict) -> None:
    vocab = {g: int(i) for g, i in vec.vocabulary_.items()}
    model = {
        "classes": [str(c) for c in clf.classes_],
        "vocab": vocab,
        "idf": [round(float(v), 6) for v in vec.idf_],
        "coef": [[round(float(v), 6) for v in row] for row in clf.coef_],
        "intercept": [round(float(v), 6) for v in clf.intercept_],
        "meta": meta,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, separators=(",", ":"))


def threshold_table(model: IntentModel, X, y):
    """확신도 기준별: 분류기가 직접 처리하는 비율(coverage)과 그 정확도. 나머지는 LLM으로 넘어간다."""
    preds = [model.predict(t) for t in X]
    out = []
    for th in (0.3, 0.4, 0.5, 0.6, 0.7):
        kept = [(p, yy) for (p, c), yy in zip(preds, y) if c >= th and p != "other"]
        handled = len(kept)
        correct = sum(p == yy for p, yy in kept)
        out.append({"threshold": th, "coverage": round(handled / len(y), 3),
                    "accuracy_when_handled": round(correct / handled, 3) if handled else None})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="음성 명령 의도 분류기 학습")
    ap.add_argument("--data", default=config.VOICE_DATA_PATH)
    ap.add_argument("--out", default=config.VOICE_MODEL_PATH)
    ap.add_argument("--report", default=config.VOICE_REPORT_PATH)
    args = ap.parse_args()

    (Xtr, ytr), (Xte, yte) = load(args.data)
    vec = TfidfVectorizer(analyzer=char_ngrams)
    A = vec.fit_transform(Xtr)
    clf = LogisticRegression(C=10.0, max_iter=2000)
    clf.fit(A, ytr)

    meta = {"trained_at": datetime.now().isoformat(timespec="seconds"),
            "train_n": len(Xtr), "test_n": len(Xte), "features": len(vec.vocabulary_)}
    export(vec, clf, args.out, meta)

    # Pi와 똑같은 순수 파이썬 추론으로 다시 평가한다 (내보내기가 틀리지 않았는지도 같이 확인)
    model = IntentModel(args.out)
    pred = [model.predict(t)[0] for t in Xte]
    skl = list(clf.predict(vec.transform(Xte)))
    acc = accuracy_score(yte, pred)
    report = {
        **meta,
        "test_accuracy": round(acc, 3),
        "matches_sklearn": pred == skl,
        "labels": list(clf.classes_),
        "confusion": confusion_matrix(yte, pred, labels=list(clf.classes_)).tolist(),
        "errors": [{"text": t, "true": a, "pred": b} for t, a, b in zip(Xte, yte, pred) if a != b],
        "thresholds": threshold_table(model, Xte, yte),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"학습 {len(Xtr)}문장, 특징 {len(vec.vocabulary_)}개 → {args.out}")
    print(f"시험 {len(Xte)}문장 정확도 {acc:.1%} (sklearn과 일치: {pred == skl})")
    for e in report["errors"]:
        print(f"  틀림: '{e['text']}' 정답 {e['true']} → {e['pred']}")
    for r in report["thresholds"]:
        print(f"  확신도 ≥ {r['threshold']}: 분류기가 처리 {r['coverage']:.0%}, 그때 정확도 {r['accuracy_when_handled']}")


if __name__ == "__main__":
    main()
