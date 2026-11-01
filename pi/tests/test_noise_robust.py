"""센서 잡음 대책 테스트: 중앙값 평활, 디바운스 설정, AI 출력 데드밴드, 잡음 증강, 시연 순서 잡음 실험."""
import os
import random

import pytest

from pi import config
from pi.control.filter import LuxMedian

needs_model = pytest.mark.skipif(not os.path.exists(config.AI_MODEL_PATH), reason="AI 모델 없음")


def test_median_ignores_spike_and_old_level():
    f = LuxMedian(5)
    for x in (300, 302, 298, 301):
        f.add(1, x)
    assert f.add(1, 900) == 301                 # 튀는 값 하나는 무시
    # 단계를 바꾸면 이전 단계에서 잰 값은 섞지 않는다 (투과율이 달라서)
    assert f.add(2, 400) == 400
    assert f.add(2, 410) == 405


def test_median_n1_is_raw():
    f = LuxMedian(1)
    assert f.add(0, 100) == 100 and f.add(0, 900) == 900


def test_switch_confirm_n_is_stabilizer_count():
    from pi.control.stabilizer import Stabilizer
    assert config.STABLE_COUNT == config.SWITCH_CONFIRM_N
    assert Stabilizer().stable_count == config.SWITCH_CONFIRM_N


def test_controller_decides_on_median():
    from pi.app import build_devices
    from pi.control.loop import Controller

    class Seq:
        def __init__(self, xs):
            self.xs = iter(xs)

        def read_lux(self):
            return next(self.xs)

    _, relays, clock, outdoor = build_devices(False, 0, "12:00")
    ctrl = Controller(Seq([300, 301, 299, 300, 2000]), relays, clock, outdoor, None, policy="rule")
    for _ in range(5):
        ctrl.step()
    assert ctrl.lux == 2000                     # 화면·기록에는 실제 측정값
    assert ctrl.info["lux_in"] == 300           # 판단에는 중앙값


def test_manual_is_immediate():
    from pi.app import build_devices
    from pi.control.loop import Controller
    ctrl = Controller(*build_devices(False, 0, "12:00"), None)
    ctrl.set_manual(2)
    assert ctrl.level == 2                      # 디바운스 없이 바로


class _Fake:
    """hold_if_close만 시험하려고 AIPolicy의 lut·deadband만 흉내 낸다."""
    lut = [0.6796, 0.7797, 1.0]          # 11/1 센서 고정 후 lut.json

    def __init__(self, mode):
        self.deadband = mode


@pytest.mark.parametrize("mode, proposed, cur, t_need, expected", [
    ("brighter", 2, 0, 0.781, 0),   # 스탠드 7, 0단계(278.3 lux), 목표 320: AI가 2단계를 골라도 1단계보다 나쁘면 유지
    ("brighter", 1, 0, 0.781, 1),   # 확실히 나으면 바꾼다
    ("brighter", 0, 2, 1.0, 0),     # 어둡게 미리(선제 차광)는 그대로
    ("both", 0, 2, 1.0, 2),         # both는 선제 차광도 막는다
    ("off", 2, 0, 0.781, 2),
])
def test_ai_deadband(mode, proposed, cur, t_need, expected):
    from pi.ai.policy import AIPolicy
    assert AIPolicy.hold_if_close(_Fake(mode), proposed, cur, t_need) == expected


def test_augmented_only_train_days_and_keeps_labels():
    from pi.ai.make_dataset import augmented, with_noise
    rows = [{"lux": 300.0, "level": 1, "target": 330.0, "outdoor": 1000.0} for _ in range(10)]
    days = augmented([(0, rows), (1, rows)], noise=0.02, copies=2)
    assert [d for d, _ in days] == [0, 1, 1, 1]          # 시험용 날(0)은 복사하지 않음
    noisy = with_noise(rows, 0.02, random.Random(1))
    assert all(r["outdoor"] == 1000.0 and r["level"] == 1 for r in noisy)   # 정답 계산용 값은 그대로
    assert any(abs(r["lux"] - 300.0) > 0.1 for r in noisy)
    assert all("lux_in" in r for r in noisy)


@needs_model
@pytest.mark.parametrize("policy", ["rule", "ai"])
def test_demo_sequence_under_noise(policy):
    """시연 순서 2→10→7→2를 잡음 표준편차 2%로 10번: 매번 2, 0, 1, 2단계 (전체 50회는 python -m pi.ai.noise_check)."""
    from pi.ai import noise_check
    from pi.ai.policy import AIPolicy
    if policy == "ai" and AIPolicy(list(config.LUT_T)).stale:
        pytest.skip("모델이 지금 투과율표로 학습되지 않음")
    assert noise_check.count_wrong(policy, 0.02, 10) == 0
