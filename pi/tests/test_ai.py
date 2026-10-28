"""AI 판단 테스트 (Pi용 JSON 추론)."""
import os

import pytest

from pi import config
from pi.ai.features import make_features

MODEL = "pi/data/ai_tree.json"
needs_model = pytest.mark.skipif(not os.path.exists(MODEL), reason="ai_tree.json 없음")


def test_features_pad_short_history():
    x = make_features(500, [1000], 3)
    assert len(x) == 6 and x[1] == 0.0          # 기록이 하나면 변화율 0


@needs_model
def test_policy_outputs_valid_level():
    from pi.ai.policy import AIPolicy
    ai = AIPolicy(list(config.LUT_T))
    for lux in (50, 200, 500, 900, 1500):
        level, info = ai.decide(lux, 12.0, 3, 7.5)
        assert 0 <= level < config.NUM_LEVELS


@needs_model
def test_night_is_level_0():
    from pi.ai.policy import AIPolicy
    ai = AIPolicy(list(config.LUT_T))
    assert ai.decide(800, 23.0, 4, 7.5)[0] == 0


@needs_model
def test_rising_light_not_brighter_than_steady():
    """같은 현재 빛이라도 빛이 빠르게 오르는 중이면 AI는 같거나 더 어두운 단계를 골라야 한다(선제 차광)."""
    from pi.ai.policy import AIPolicy
    lut = list(config.LUT_T)
    cur = 4
    steady, rising = AIPolicy(lut), AIPolicy(lut)
    for _ in range(4):
        lv_s, _ = steady.decide(1000 * lut[cur], 12.0, cur, 7.5)
    for inc in (500, 650, 820, 1000):
        lv_r, _ = rising.decide(inc * lut[cur], 12.0, cur, 7.5)
    assert lv_r <= lv_s


@needs_model
def test_stale_model_starts_with_rule(monkeypatch):
    """모델이 학습할 때와 투과율표가 다르면(실측 후 재학습 전) 규칙으로 시작해야 한다."""
    from pi.app import build_devices
    from pi.control.loop import Controller
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")
    monkeypatch.setattr(config, "LUT_T", [0.06, 0.17, 0.36, 0.47, 0.70, 1.0])
    ctrl = Controller(sensor, relays, clock, outdoor, None)
    assert ctrl.ai_meta["stale"] and ctrl.brain == "rule"
    assert "ai" in ctrl.policies                 # 웹에서 직접 고를 수는 있음


@needs_model
def test_stale_when_level_order_changed(monkeypatch):
    from pi.ai.policy import AIPolicy
    lut = list(config.LUT_T)
    assert not AIPolicy(lut).stale
    levels = list(config.LEVELS)
    levels[2], levels[3] = levels[3], levels[2]
    monkeypatch.setattr(config, "LEVELS", levels)
    assert AIPolicy(lut).stale
