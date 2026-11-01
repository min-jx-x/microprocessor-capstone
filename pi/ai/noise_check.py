"""시연 순서 잡음 실험: 실측 lux로 스탠드 2 → 10 → 7 → 2를 실제 제어 루프(Controller)에 넣어 본다.

실행 (레포 최상위): python -m pi.ai.noise_check
               python -m pi.ai.noise_check --noise 0.01 0.02 --runs 50 --median 1   (평활 끄고 비교)

- 센서 값 = 실측표[스탠드][지금 단계] × (1 + 정규분포 잡음). --noise는 표준편차 비율 (0.01 = 1%)
  11/1 실측 잡음: 센서 고정 전 스탠드 7에서 ±1.3%, 고정 후 280.0~280.8 lux(±0.15%).
- 제어 루프 그대로: 중앙값 평활(SENSOR_MEDIAN_N) → 판단(규칙/AI) → 디바운스(SWITCH_CONFIRM_N) → 전환 간격.
  1회 = SAMPLE_PERIOD_S(1초), 시각은 12:00(주간) 고정. 스탠드마다 --hold초 둔다.
- 오판: 스탠드마다 마지막 단계가 기대값(2, 0, 1, 2)과 다르면 그 회차는 오판.
- 반응 시간: 스탠드를 바꾼 뒤 마지막 단계에 처음 도착하기까지 걸린 초 (잡음 없음 기준으로 보고).
"""
import argparse
import random
from typing import Dict, List, Optional

from pi import config
from pi.devices.sim import SimRelays
from pi.sim.clock import VirtualClock

# 11/1 센서 위치 고정 후 실측 (잡광 172 lux). 단계별 센서 조도 [0단계, 1단계, 2단계]
MEASURED_LUX = {2: [202.5, 213.3, 234.2], 5: [245.8, 261.7, 291.7], 7: [278.3, 296.7, 335.8],
                10: [341.7, 366.7, 421.7]}
DEMO = (2, 10, 7, 2)
EXPECTED = (2, 0, 1, 2)


class DemoSensor:
    """지금 스탠드와 창문 단계에 맞는 실측 lux에 잡음을 얹어 돌려준다."""

    def __init__(self, noise: float, seed: int) -> None:
        self.noise, self.rng = noise, random.Random(seed)
        self.stand, self.ctrl = DEMO[0], None

    def read_lux(self) -> float:
        lux = MEASURED_LUX[self.stand][self.ctrl.level]
        return round(lux * (1.0 + self.rng.gauss(0.0, self.noise)), 1)


def run_once(policy: str, noise: float, seed: int, hold: int = 60, median: Optional[int] = None,
             model: Optional[str] = None, deadband: Optional[str] = None) -> Dict:
    """시연 순서를 한 번 돌린다. 반환: 스탠드별 마지막 단계, 스탠드별 도착 시간(초), 전환 횟수."""
    from datetime import datetime

    from pi.control.filter import LuxMedian
    from pi.control.loop import Controller

    sensor = DemoSensor(noise, seed)
    ctrl = Controller(sensor, SimRelays(), VirtualClock(datetime(2026, 11, 1, 12, 0), 0), policy=policy)
    sensor.ctrl = ctrl
    if median is not None:
        ctrl.lux_filter = LuxMedian(median)
    if model is not None and "ai" in ctrl.policies:
        from pi.ai.policy import AIPolicy
        ctrl.policies["ai"] = AIPolicy(ctrl.lut, model)
        ctrl.brain = policy
    if deadband is not None and "ai" in ctrl.policies:
        ctrl.policies["ai"].deadband = deadband
    if ctrl.brain != policy:
        raise SystemExit(f"{policy}로 시작하지 못함 (AI 모델이 없거나 재학습 전)")
    t = {"now": 0.0}
    ctrl.monotonic = lambda: t["now"]
    finals: List[int] = []
    arrive: List[float] = []
    for stand in DEMO:
        sensor.stand = stand
        trace = []
        for _ in range(hold):
            ctrl.step()
            trace.append(ctrl.level)
            t["now"] += config.SAMPLE_PERIOD_S
        final = trace[-1]
        finals.append(final)
        # 스탠드를 바꾼 뒤 k번째 측정(k초)에서 마지막 단계로 바뀌어 끝까지 유지된 첫 k (처음부터 같으면 0)
        first = next(i for i in range(len(trace)) if all(x == final for x in trace[i:]))
        arrive.append(first * config.SAMPLE_PERIOD_S)
    return {"finals": finals, "arrive": arrive, "switches": ctrl.switches}


def count_wrong(policy: str, noise: float, runs: int, **kw) -> int:
    return sum(tuple(run_once(policy, noise, seed, **kw)["finals"]) != EXPECTED for seed in range(runs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=float, nargs="+", default=[0.01, 0.02], help="잡음 표준편차 비율")
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--hold", type=int, default=60, help="스탠드마다 두는 시간(초)")
    ap.add_argument("--median", type=int, default=None, help=f"중앙값 개수 (기본 config {config.SENSOR_MEDIAN_N})")
    ap.add_argument("--model", default=None, help="비교할 AI 모델 파일 (기본 config.AI_MODEL_PATH)")
    ap.add_argument("--deadband", choices=("brighter", "both", "off"), default=None,
                    help=f"AI 출력 데드밴드 (기본 config {config.AI_DEADBAND})")
    a = ap.parse_args()
    kw = dict(hold=a.hold, median=a.median, model=a.model, deadband=a.deadband)
    print(f"시연 순서 {'→'.join(map(str, DEMO))}, 기대 단계 {list(EXPECTED)}, 목표 {config.TARGET_DAY_LUX:g} lux, "
          f"중앙값 {a.median or config.SENSOR_MEDIAN_N}개, 디바운스 {config.SWITCH_CONFIRM_N}회, "
          f"AI 데드밴드 {a.deadband or config.AI_DEADBAND}")
    for policy in ("rule", "ai"):
        clean = run_once(policy, 0.0, 0, **kw)
        print(f"{policy:>4} 잡음 없음: 단계 {clean['finals']}, 도착 시간(초) {clean['arrive']}")
    print(f"\n{'잡음(표준편차)':<14}{'규칙 오판':>10}{'AI 오판':>10}   ({a.runs}회씩)")
    for nz in a.noise:
        r = count_wrong("rule", nz, a.runs, **kw)
        x = count_wrong("ai", nz, a.runs, **kw)
        print(f"{nz:<14.1%}{r:>10}{x:>10}")


if __name__ == "__main__":
    main()
