"""시작 판단 방식(LIGHTQ_POLICY, --policy)과 현장 조정용 주간 목표(LIGHTQ_TARGET_DAY_LUX) 테스트."""
import os
import subprocess
import sys

import pytest

from pi import config
from pi.app import build_devices, create_app
from pi.control.loop import Controller

needs_fresh_model = pytest.mark.skipif(
    not os.path.exists(config.AI_MODEL_PATH), reason="AI 모델 없음")


def _ctrl(**kw):
    sensor, relays, clock, outdoor = build_devices(False, 0, "12:00")
    return Controller(sensor, relays, clock, outdoor, None, **kw)


def _config_in_new_process(env_extra):
    """config는 import할 때 환경변수를 읽으므로, 재부팅(새 프로세스)처럼 새로 띄워서 확인한다."""
    env = {k: v for k, v in os.environ.items() if k not in ("LIGHTQ_POLICY", "LIGHTQ_TARGET_DAY_LUX")}
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-c",
                          "from pi import config; print(config.DEFAULT_POLICY, config.TARGET_DAY_LUX)"],
                         env=env, capture_output=True, text=True, check=True)
    policy, target = out.stdout.strip().splitlines()[-1].split()
    return policy, float(target)


def test_env_policy_values():
    assert config.env_policy(None) == "ai"            # 기본은 AI
    assert config.env_policy("") == "ai"
    assert config.env_policy(" RULE ") == "rule"      # 시연 중 문제가 생기면 규칙으로
    assert config.env_policy("tree") == "ai"          # 모르는 값은 경고 후 기본


def test_env_float(monkeypatch):
    monkeypatch.delenv("LIGHTQ_X", raising=False)
    assert config.env_float("LIGHTQ_X", 330.0) == 330.0
    monkeypatch.setenv("LIGHTQ_X", "320")
    assert config.env_float("LIGHTQ_X", 330.0) == 320.0
    for bad in ("abc", "0", "-5", " "):
        monkeypatch.setenv("LIGHTQ_X", bad)
        assert config.env_float("LIGHTQ_X", 330.0) == 330.0   # 잘못 넣어도 서비스가 죽지 않게 기본값


def test_new_process_defaults_and_overrides():
    assert _config_in_new_process({}) == ("ai", 320.0)
    assert _config_in_new_process({"LIGHTQ_POLICY": "rule", "LIGHTQ_TARGET_DAY_LUX": "310"}) == ("rule", 310.0)
    assert _config_in_new_process({"LIGHTQ_TARGET_DAY_LUX": "abc"}) == ("ai", 320.0)


def test_policy_rule_from_env(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_POLICY", "rule")   # LIGHTQ_POLICY=rule 과 같음
    assert _ctrl().brain == "rule"


@needs_fresh_model
def test_policy_ai_when_model_fresh(monkeypatch):
    ctrl = _ctrl(policy="ai")
    if ctrl.ai_meta["stale"]:
        pytest.skip("모델이 지금 투과율표로 학습되지 않음 (python -m pi.ai.retrain)")
    assert ctrl.brain == "ai"
    monkeypatch.setattr(config, "DEFAULT_POLICY", "ai")   # 기본값
    assert _ctrl().brain == "ai"
    assert _ctrl(policy="rule").brain == "rule"           # 실행 옵션이 환경변수보다 우선


@needs_fresh_model
def test_web_switch_both_ways(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_POLICY", "ai")
    ctrl = _ctrl()
    client = create_app(ctrl, None).test_client()
    assert client.post("/api/brain", json={"brain": "rule"}).status_code == 200   # 시연 중 문제 → 바로 규칙
    assert ctrl.brain == "rule"
    assert client.post("/api/brain", json={"brain": "ai"}).status_code == 200
    assert ctrl.brain == "ai"
    monkeypatch.setattr(config, "DEFAULT_POLICY", "rule")
    assert _ctrl().brain == "rule"                        # 다시 시작하면(재부팅) 설정값으로
