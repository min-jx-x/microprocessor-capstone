"""실시간을 기다리지 않고 하루를 빠르게 돌리는 오프라인 시뮬레이션.

웹과 같은 부품(가짜 센서·릴레이, 단계 전환기, 안정화기)을 그대로 쓰고,
판단(policy)만 바꿔 끼운다. 학습 데이터 만들기와 규칙 대 AI 비교에 같이 쓴다.
같은 seed면 바깥 빛·구름·직사광·센서 잡음이 똑같아서 공정하게 비교할 수 있다.
"""
import random
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from pi import config
from pi.control.decide import schedule
from pi.control.loop import LevelDriver, Stabilizer
from pi.devices.sim import SimRelays, SimSensor, default_ambient, level_transmittance
from pi.sim.outdoor import OutdoorLight

AMBIENT_LUX = default_ambient()
BURST_AT = 20          # 직사광 장면에서 직사광이 시작되는 회차
GLARE = 1.3            # 목표의 1.3배를 넘으면 눈부심


def sim_transmittance(level: int) -> float:
    """시뮬레이터가 쓰는 단계별 절대 투과율 (실측 lut.json이 있으면 실측 기준)."""
    return level_transmittance(level)


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


def run_scene(policy, seed: int = 0, hour: float = 12.0, steps: int = 70,
              burst_at: int = 20, extra_lux: float = 1500.0, rise_steps: int = 8,
              hold_steps: int = 12, wake_hour: float = 7.5) -> List[Dict]:
    """직사광 한 번만 들어오는 짧은 장면 (그래프용). 1회 = 실제 1초, 가상 시계도 1배속."""
    clock = {"h": hour}
    outdoor = OutdoorLight(lambda: clock["h"], peak_lux=2000.0, seed=seed)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor, ambient_lux=AMBIENT_LUX, seed=seed + 1)
    driver = LevelDriver(relays, settle_s=0)
    stab = Stabilizer()
    policy.reset()
    driver.apply(0)
    level, rows = 0, []
    for i in range(steps):
        clock["h"] = hour + i / 3600
        if i == burst_at:
            outdoor.trigger_burst(extra_lux, rise_steps=rise_steps, hold_steps=hold_steps)
        _, target = schedule(clock["h"], wake_hour)
        lux = sensor.read_lux()
        cand, _ = policy.decide(lux, clock["h"], level, wake_hour)
        rows.append({"i": i, "lux": lux, "target": target, "level": level,
                     "outdoor": outdoor.last, "cand": cand})
        nxt = stab.propose(cand, level, float(i))
        if nxt is not None:
            driver.apply(nxt)
            stab.mark_switched(float(i))
            level = nxt
    return rows


def first_darker(rows, b: int = BURST_AT) -> int:
    """직사광 시작(b) 뒤 처음으로 더 어두운 단계로 바꿀 때까지 걸린 회차(초)."""
    lv0 = rows[b]["level"]
    return next((k - b for k in range(b + 1, len(rows)) if rows[k]["level"] < lv0), len(rows) - b)


def glare_secs(rows, b: int = BURST_AT) -> int:
    """직사광 시작 뒤 실내 조도가 목표의 GLARE배를 넘은 회차(초) 수."""
    return sum(r["lux"] > r["target"] * GLARE for r in rows[b:])


def burst_stats(policy, n: int = 40) -> Dict[str, float]:
    """직사광 장면 n번(seed 0 ~ n-1) 평균. delay: 어둡게 바꿀 때까지(초), glare: 눈부심 시간(초)"""
    scenes = [run_scene(policy, seed=s, burst_at=BURST_AT) for s in range(n)]
    return {"delay": statistics.mean(first_darker(r) for r in scenes),
            "glare": statistics.mean(glare_secs(r) for r in scenes)}
