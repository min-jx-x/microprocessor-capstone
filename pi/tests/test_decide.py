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
    # 입사광 = 주간 목표 / 0.40 → 필요 투과율 0.40 → 3단계(0.38) (목표 320이면 입사광 800)
    incident = config.TARGET_DAY_LUX / 0.40
    level, info = decide_rule(incident * LUT[5], 12.0, 5, LUT, 7.5)
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


# 11/1 실측 (잡광 140 lux, lut.json). 단계별 센서 조도 [0단계, 1단계, 2단계]
MEASURED_LUT = [0.6473, 0.7563, 1.0]
MEASURED_LUX = {2: [170.8, 187.5, 222.5], 5: [225.8, 240.8, 280.0], 7: [280.0, 316.7, 361.7],
                8: [270.8, 289.2, 334.2], 10: [352.5, 388.3, 468.3]}


def _settle(lux_by_level, start, max_steps=10):
    """decide_rule을 반복 적용해 더 이상 안 바뀌는 단계. 단계를 바꾸면 센서 값은 그 단계의 실측값이 된다."""
    cur = start
    for _ in range(max_steps):
        nxt, _ = decide_rule(lux_by_level[cur], 12.0, cur, MEASURED_LUT, 7.5)
        if nxt == cur:
            return cur
        cur = nxt
    raise AssertionError(f"{max_steps}번 안에 수렴하지 않음 (시작 {start}단계)")


@pytest.mark.parametrize("stand, expected", [(2, 2), (5, 2), (10, 0)])
@pytest.mark.parametrize("start", [0, 1, 2])
def test_measured_lux_converges(stand, expected, start):
    # 주간 목표(TARGET_DAY_LUX)로 스탠드 2·5는 2단계(투명), 10은 0단계(뿌옇게)에 시작 단계와 무관하게 멈춰야 한다
    assert _settle(MEASURED_LUX[stand], start) == expected


@pytest.mark.parametrize("start", [0, 1, 2])
def test_demo_sequence_2_10_7_2(start):
    # 시연 순서: 스탠드 2 → 10 → 7 → 2. 스탠드를 바꿔도 단계는 이어진다 → 2, 0, 1, 2단계
    cur, got = start, []
    for stand in (2, 10, 7, 2):
        cur = _settle(MEASURED_LUX[stand], cur)
        got.append(cur)
    assert got == [2, 0, 1, 2]
