"""AI 입력 특징. 학습(make_dataset.py)과 실행(policy.py)이 같은 함수를 써야 결과가 맞는다.

입사광 = 측정 조도 / 현재 단계 투과율 (필름 바깥 빛을 가장 밝은 단계 기준으로 거꾸로 추정한 값)

특징 6개
  log_tneed : log(목표 / 입사광)  지금 필요한 투과율 (규칙이 보는 값과 같음)
  rate1~3   : 최근 3구간의 입사광 변화율  (오르는 중인지 = 선제 차광의 근거)
  cur       : 현재 단계
  target    : 목표 조도
정답(라벨): HORIZON 회 뒤의 입사광에 맞는 단계. 즉 "곧 올 빛"에 맞춰 미리 고르도록 학습한다.
"""
import math
from typing import List, Sequence

HISTORY = 4          # 특징을 만들 때 필요한 최근 입사광 개수
HORIZON = 4          # 몇 회 뒤의 빛을 보고 정답을 정할지 (1회 = 1초)
FEATURE_NAMES = ["log_tneed", "rate1", "rate2", "rate3", "cur", "target"]
# 화면(AI 설명 페이지)에 보이는 이름
FEATURE_LABELS = {"log_tneed": "필요 투과율", "rate1": "직전 1회 빛 변화", "rate2": "1~2회 전 빛 변화",
                  "rate3": "2~3회 전 빛 변화", "cur": "현재 단계", "target": "목표 조도"}


def _rate(a: float, b: float) -> float:
    return (a - b) / max(b, 1.0)


def make_features(target: float, incs: Sequence[float], cur: int) -> List[float]:
    """incs: 오래된 것부터 최근 것까지의 입사광. 4개보다 적으면 가장 오래된 값으로 채운다."""
    incs = list(incs)[-HISTORY:]
    while len(incs) < HISTORY:
        incs.insert(0, incs[0])
    i3, i2, i1, i0 = incs
    return [math.log(target / max(i0, 1.0)), _rate(i0, i1), _rate(i1, i2), _rate(i2, i3),
            float(cur), float(target)]


def show(name: str, v: float) -> str:
    """특징 값이나 트리 기준값을 사람이 읽는 글자로. 필요 투과율은 log를 풀고, 변화율은 %로."""
    if name == "log_tneed":
        return f"{math.exp(v):.2f}"
    if name.startswith("rate"):
        return f"{v * 100:+.1f}%"
    if name == "target":
        return f"{v:.0f} lux"
    return f"{v:g}"
