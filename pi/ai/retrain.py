"""실측 후 한 번에 다시 학습하기 (노트북에서 실행).

실행 (레포 최상위): python -m pi.ai.retrain
순서: 학습 데이터 생성 → 결정트리 학습 → 규칙 대 AI 비교
lut.json(실측값)이 있으면 세 단계 모두 실측 기준으로 돈다. 끝나면 ai_tree.json을 커밋해서 Pi에 올린다.
"""
import argparse
import subprocess
import sys

from pi import config


def run(args) -> None:
    print("\n$ python -m " + " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m"] + args, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=300, help="학습 데이터 일수")
    ap.add_argument("--eval-days", type=int, default=40, help="비교 일수")
    a = ap.parse_args()
    print(f"투과율 기준: {'실측 lut.json' if config.LUT_SOURCE == 'measured' else '기본 가정값'}  {config.LUT_T}", flush=True)
    run(["pi.ai.make_dataset", "--days", str(a.days)])
    run(["pi.ai.train"])
    run(["pi.ai.evaluate", "--days", str(a.eval_days)])
    print("\n완료. 결과가 괜찮으면 pi/data/ai_tree.json (그리고 lut.json)을 커밋하세요.")


if __name__ == "__main__":
    main()
