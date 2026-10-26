"""Stabilizer 단위 테스트."""
import pytest

from pi import config
from pi.control.stabilizer import Stabilizer


def test_stabilizer_propose_needs_stable_count():
    stab = Stabilizer(stable_count=3, min_interval_s=5.0)
    now = 100.0

    # 1회차: None
    assert stab.propose(candidate=2, current=0, now=now) is None
    # 2회차 (같은 방향: 밝게): None
    assert stab.propose(candidate=3, current=0, now=now + 1.0) is None
    # 3회차 (같은 방향: 밝게): 조건 만족 -> candidate 반환
    assert stab.propose(candidate=3, current=0, now=now + 2.0) == 3


def test_stabilizer_same_level_resets():
    stab = Stabilizer(stable_count=3, min_interval_s=5.0)
    now = 100.0

    # 2회 연속 밝게
    assert stab.propose(candidate=2, current=0, now=now) is None
    assert stab.propose(candidate=2, current=0, now=now + 1.0) is None

    # 현재와 같은 단계 입력 -> 리셋
    assert stab.propose(candidate=0, current=0, now=now + 2.0) is None
    assert stab.count == 0
    assert stab.direction == 0


def test_stabilizer_direction_change_resets_count():
    stab = Stabilizer(stable_count=3, min_interval_s=5.0)
    now = 100.0

    # 2회 밝게
    assert stab.propose(candidate=3, current=2, now=now) is None
    assert stab.propose(candidate=4, current=2, now=now + 1.0) is None

    # 갑자기 어둡게 변경 -> 카운트가 1로 리셋
    assert stab.propose(candidate=1, current=2, now=now + 2.0) is None
    assert stab.count == 1
    assert stab.direction == -1


def test_stabilizer_respects_min_interval():
    stab = Stabilizer(stable_count=3, min_interval_s=5.0)
    now = 100.0

    # 전환 성공 후 mark_switched
    assert stab.propose(candidate=2, current=0, now=now) is None
    assert stab.propose(candidate=2, current=0, now=now + 1.0) is None
    assert stab.propose(candidate=2, current=0, now=now + 2.0) == 2
    stab.mark_switched(now=now + 2.0)

    # 마지막 전환 후 5초가 안 지난 상태 (now + 4.0)에서 3회 연속 요청
    assert stab.propose(candidate=4, current=2, now=now + 3.0) is None
    assert stab.propose(candidate=4, current=2, now=now + 3.5) is None
    assert stab.propose(candidate=4, current=2, now=now + 4.0) is None  # 아직 2초 경과

    # 5초 이상 경과 (now + 7.5 -> 5.5초 경과) -> candidate 반환
    assert stab.propose(candidate=4, current=2, now=now + 7.5) == 4


def test_stabilizer_reset():
    stab = Stabilizer(stable_count=3, min_interval_s=5.0)
    stab.propose(candidate=2, current=0, now=100.0)
    assert stab.count == 1
    stab.reset()
    assert stab.count == 0
    assert stab.direction == 0
