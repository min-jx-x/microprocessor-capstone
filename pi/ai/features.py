"""AI 입력 특징. 학습(make_dataset.py)과 실행(policy.py)이 같은 함수를 써야 결과가 맞는다.

입사광 = 측정 조도 / 현재 단계 투과율 (필름 바깥 빛을 5단계 기준으로 거꾸로 추정한 값)

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
