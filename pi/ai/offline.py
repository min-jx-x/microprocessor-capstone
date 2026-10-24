"""실시간을 기다리지 않고 하루를 빠르게 돌리는 오프라인 시뮬레이션.

웹과 같은 부품(가짜 센서·릴레이, 단계 전환기, 안정화기)을 그대로 쓰고,
판단(policy)만 바꿔 끼운다. 학습 데이터 만들기와 규칙 대 AI 비교에 같이 쓴다.
같은 seed면 바깥 빛·구름·직사광·센서 잡음이 똑같아서 공정하게 비교할 수 있다.
"""
import random
from typing import Dict, List, Optional, Sequence, Tuple

from pi import config
from pi.control.decide import schedule
from pi.control.loop import LevelDriver, Stabilizer
from pi.devices.sim import FILM_T, SimRelays, SimSensor
from pi.sim.outdoor import OutdoorLight

AMBIENT_LUX = 5.0


def sim_transmittance(level: int) -> float:
    a, b = config.LEVELS[level]
    return FILM_T[a] * FILM_T[b]


def run_day(policy, profile: Optional[Sequence[float]] = None, dt_s: float = 720.0,
            seed: int = 0, wake_hour: float = 7.5, bursts: int = 6,
            explore: float = 0.0) -> Tuple[List[Dict], List[int]]:
    """하루(0~24시)를 돌린다.

    dt_s    : 1회(실제 1초)마다 흐르는 가상 시간(초). 720이면 하루가 120회
    bursts  : 낮 동안 평균 직사광 횟수
    explore : 이 확률로 임의 단계를 강제로 넣는다 (학습 데이터 다양화, 사람이 수동 조작한 셈)
    반환    : 회차별 기록, 직사광 시작 회차 목록
    """
    rng = random.Random(seed)
    clock = {"h": 0.0}
    outdoor = OutdoorLight(lambda: clock["h"], peak_lux=rng.uniform(1500, 2500),
                           seed=seed, profile=profile)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor, ambient_lux=AMBIENT_LUX, seed=seed + 1)
    driver = LevelDriver(relays, settle_s=0)
    stab = Stabilizer()
    policy.reset()
    driver.apply(0)

    steps = int(24 * 3600 / dt_s)
    p_burst = bursts / (steps * 11 / 24)        # 낮(약 11시간) 동안 bursts번 정도
    level, rows, burst_starts = 0, [], []
    for i in range(steps):
        h = i * dt_s / 3600
        clock["h"] = h
        _, target = schedule(h, wake_hour)
        r_burst, r_explore = rng.random(), rng.random()
        if target is not None and r_burst < p_burst and outdoor.burst < 50:
            outdoor.trigger_burst(rng.uniform(800, 2500), rise_steps=rng.randint(4, 12),
                                  hold_steps=rng.randint(5, 20))
            burst_starts.append(i)
        lux = sensor.read_lux()
        cand, _ = policy.decide(lux, h, level, wake_hour)
        rows.append({"i": i, "hour": h, "lux": lux, "target": target, "level": level,
                     "outdoor": outdoor.last, "cand": cand})
        now = i * config.SAMPLE_PERIOD_S
        if explore and target is not None and r_explore < explore:
            level = rng.randrange(config.NUM_LEVELS)     # 수동 조작처럼 바로 적용
            driver.apply(level)
            stab.reset()
            continue
        nxt = stab.propose(cand, level, now)
        if nxt is not None:
            driver.apply(nxt)
            stab.mark_switched(now)
            level = nxt
    return rows, burst_starts
