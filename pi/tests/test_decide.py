"""판단 규칙과 안정화 테스트."""
import pytest

from pi import config
from pi.control.decide import choose_level, decide_rule, parse_hhmm, schedule
from pi.control.loop import Stabilizer

LUT = [0.14, 0.21, 0.32, 0.38, 0.56, 1.00]


def test_schedule_periods():
    wake = 7.5
    assert schedule(3.0, wake) == ("sleep", None)
    p, t = schedule(7.25, wake)                 # 기상 20분 전 ~ 기상 사이
    assert p == "ramp" and config.TARGET_WAKE_START_LUX < t < config.TARGET_WAKE_LUX
    assert schedule(8.0, wake) == ("morning", config.TARGET_WAKE_LUX)
    assert schedule(12.0, wake) == ("day", config.TARGET_DAY_LUX)
    assert schedule(19.0, wake) == ("evening", None)


def test_night_forces_level_0():
    level, info = decide_rule(300, 23.0, 4, LUT, 7.5)
    assert level == 0 and info["target"] is None


def test_picks_nearest_level():
    # 입사광 1250, 목표 500 → 필요 투과율 0.40 → 3단계(0.38)
    level, info = decide_rule(1250 * LUT[5], 12.0, 5, LUT, 7.5)
    assert level == 3
    assert info["t_need"] == pytest.approx(0.4, abs=0.01)


def test_deadband_keeps_current():
    # 필요 0.36: 최적은 3단계(0.38, 오차 0.02). 현재 2단계(0.32, 오차 0.04)는
    # 최적 오차 + 데드밴드(0.05) 안이라 바꾸지 않고 유지
    assert choose_level(0.36, 3, LUT) == 3
    assert choose_level(0.36, 2, LUT) == 2
    # 차이가 크면 바꾼다
    assert choose_level(0.90, 2, LUT) == 5


def test_parse_hhmm():
    assert parse_hhmm("07:30") == 7.5
    for bad in ("25:00", "07:99", "abc"):
        with pytest.raises(ValueError):
            parse_hhmm(bad)


def test_stabilizer_needs_three_in_a_row():
    st = Stabilizer(stable_count=3, min_interval_s=5)
    assert st.propose(4, 2, now=100) is None
    assert st.propose(4, 2, now=101) is None
    assert st.propose(4, 2, now=102) == 4
    st.mark_switched(102)
    # 전환 직후 5초 안에는 바뀌지 않음
    for t in (103, 104, 105):
        assert st.propose(1, 4, now=t) is None


def test_stabilizer_counts_direction_not_value():
    """AI 후보가 2 → 1 → 2처럼 값은 흔들려도 '어둡게' 방향이 3번 이어지면 전환 (최근 후보로)."""
    st = Stabilizer(stable_count=3, min_interval_s=5)
    assert st.propose(2, 3, now=10) is None
    assert st.propose(1, 3, now=11) is None
    assert st.propose(2, 3, now=12) == 2


def test_stabilizer_resets_on_direction_change():
    st = Stabilizer(stable_count=3, min_interval_s=5)
    st.propose(1, 3, now=10)
    st.propose(1, 3, now=11)
    assert st.propose(4, 3, now=12) is None     # 방향이 바뀌면 처음부터
    assert st.propose(3, 3, now=13) is None     # 현재와 같으면(유지) 초기화
