"""개인 선호 보정 검증: 선호가 다른 가상 사용자 3명을 2주 동안 시뮬레이션.

실행 (레포 최상위): python -m pi.ai.eval_preference
결과: 날마다 수동 조작 횟수와 배운 목표 조도 표, docs/images/preference_learning.png

가상 사용자 행동 (단순화한 가정)
  - 실내 조도가 자기 선호에서 25% 넘게 벗어난 상태가 3회 이어지면, 70% 확률로 직접 단계를 바꾼다
  - 자기 선호에 가장 가까운 단계를 고르고, 30분 동안 수동으로 두었다가 자동으로 되돌린다
  - 지금 단계보다 나은 단계가 없으면(예: 이미 가장 밝음) 손대지 않는다
학습이 잘 되면 날이 갈수록 수동 조작이 줄고, 배운 목표가 각자 선호에 가까워져야 한다.
"""
import argparse
import os
import random
import statistics

from pi import config
from pi.ai.kma import load_profiles, pick
from pi.ai.offline import AMBIENT_LUX
from pi.control.decide import RulePolicy, load_lut
from pi.control.loop import LevelDriver, Stabilizer
from pi.control.preference import GROUP, PreferenceStore
from pi.devices.sim import SimRelays, SimSensor
from pi.sim.outdoor import OutdoorLight

USERS = {"밝게 선호": {"morning": 260, "day": 650},
         "기본에 가까움": {"morning": 200, "day": 520},
         "어둡게 선호": {"morning": 150, "day": 380}}
UNHAPPY, PATIENCE, P_ACT, HOLD_MIN = 0.25, 3, 0.7, 30


def make_policy(lut):
    if os.path.exists("pi/data/ai_tree.json"):
        from pi.ai.policy import AIPolicy
        return AIPolicy(lut)
    return RulePolicy(lut)


def run_user_day(policy, pref, user, seed, profile, dt_s=300.0, wake_hour=7.5):
    """하루 동안 가상 사용자가 몇 번 수동 조작했는지 돌려준다."""
    rng = random.Random(seed)
    lut = policy.lut
    clock = {"h": 0.0}
    outdoor = OutdoorLight(lambda: clock["h"], peak_lux=rng.uniform(1600, 2400), seed=seed, profile=profile)
    relays = SimRelays()
    sensor = SimSensor(relays, outdoor, ambient_lux=AMBIENT_LUX, seed=seed + 1)
    driver, stab = LevelDriver(relays, settle_s=0), Stabilizer()
    policy.reset()
    driver.apply(0)
    level, mode, unhappy, hold, samples, actions = 0, "auto", 0, 0, None, 0
    hold_steps = int(HOLD_MIN * 60 / dt_s)
    for i in range(int(24 * 3600 / dt_s)):
        h = i * dt_s / 3600
        clock["h"] = h
        lux = sensor.read_lux()
        cand, info = policy.decide(lux, h, level, wake_hour, pref.scale())
        g = GROUP.get(info["period"])

        if mode == "manual":
            if samples is not None:             # 제어 루프와 같은 방식으로 선호 조도 수집
                samples.append(lux)
                if len(samples) >= config.PREF_SETTLE:
                    pref.learn(info["period"], info["base_target"], statistics.median(samples))
                    samples = None
            hold -= 1
            if hold <= 0:
                mode = "auto"
                stab.reset()
            continue

        nxt = stab.propose(cand, level, float(i))
        if nxt is not None:
            driver.apply(nxt)
            stab.mark_switched(float(i))
            level = nxt
            continue

        if g is None:                           # 저녁·취침에는 손대지 않음
            unhappy = 0
            continue
        want = user[g]
        unhappy = unhappy + 1 if abs(lux - want) / want > UNHAPPY else 0
        if unhappy >= PATIENCE and rng.random() < P_ACT:
            incident = lux / lut[level]
            best = min(range(len(lut)), key=lambda k: abs(incident * lut[k] - want))
            unhappy = 0
            if best != level:
                driver.apply(best)
                level, mode, hold, samples = best, "manual", hold_steps, []
                stab.reset()
                actions += 1
    return actions


class NoLearning(PreferenceStore):
    """비교용: 수동 조작을 해도 배우지 않는 저장소."""
    def learn(self, *args, **kwargs):
        return None


def simulate(user, days, seed, learn=True):
    lut = load_lut()
    profiles = load_profiles()
    pref = PreferenceStore(path=None) if learn else NoLearning(path=None)
    policy = make_policy(lut)
    acts, day_targets = [], []
    for d in range(days):
        acts.append(run_user_day(policy, pref, user, seed * 100 + d,
                                 pick(profiles, seed + d) if profiles else None))
        off = pref.snapshot()["offset"]
        day_targets.append({"morning": config.TARGET_WAKE_LUX * (1 + off["morning"]),
                            "day": config.TARGET_DAY_LUX * (1 + off["day"])})
    return acts, day_targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--reps", type=int, default=10, help="사용자마다 반복 횟수 (날씨를 바꿔 평균)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default="docs/images/preference_learning.png")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    mean = lambda xs: statistics.mean(xs)  # noqa: E731
    result = {}
    for name, user in USERS.items():
        runs_on = [simulate(user, args.days, args.seed + r * 7, True) for r in range(args.reps)]
        runs_off = [simulate(user, args.days, args.seed + r * 7, False) for r in range(args.reps)]
        acts_on = [mean([run[0][d] for run in runs_on]) for d in range(args.days)]
        acts_off = [mean([run[0][d] for run in runs_off]) for d in range(args.days)]
        tgt = [mean([run[1][d]["day"] for run in runs_on]) for d in range(args.days)]
        result[name] = {"on": acts_on, "off": acts_off, "target": tgt}
        print(f"{name:<8} 선호 주간 {user['day']} lux (기본 {config.TARGET_DAY_LUX:.0f})")
        print(f"   수동 조작/일 (마지막 7일 평균): 학습 없음 {mean(acts_off[-7:]):.2f} → 학습 {mean(acts_on[-7:]):.2f}")
        print(f"   배운 주간 목표 (14일 뒤 평균): {tgt[-1]:.0f} lux")
    all_on = [mean([result[n]["on"][d] for n in result]) for d in range(args.days)]
    all_off = [mean([result[n]["off"][d] for n in result]) for d in range(args.days)]
    print(f"전체 평균 수동 조작/일 (마지막 7일): 학습 없음 {mean(all_off[-7:]):.2f} → 학습 {mean(all_on[-7:]):.2f}")
    if not args.no_plot:
        plot(result, all_on, all_off, args.days, args.reps, args.out)


def plot(result, all_on, all_off, days, reps, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pi.ai.plot_compare import INK, MUTED, GRID, setup_font
    setup_font()
    colors = ["#2a78d6", "#eb6834", "#1baf7a"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.8), dpi=150)
    x = list(range(1, days + 1))
    ax1.plot(x, all_off, color=MUTED, lw=2, ls=(0, (5, 3)), label="학습 없음")
    ax1.plot(x, all_on, color="#2a78d6", lw=2.2, marker="o", ms=5, label="선호 보정")
    ax1.text(days + 0.3, all_off[-1], "학습 없음", color=MUTED, va="center", fontsize=10)
    ax1.text(days + 0.3, all_on[-1], "선호 보정", color="#2a78d6", va="center", fontsize=10, fontweight="bold")
    for (name, r), c in zip(result.items(), colors):
        want = USERS[name]["day"]
        ax2.hlines(want, 0.6, days + 0.2, color=c, lw=1, linestyles=(0, (4, 3)))
        ax2.plot(x, r["target"], color=c, lw=2, marker="o", ms=5)
        ax2.text(days + 0.4, want, f"{name} (선호 {want})", color=c, va="center", fontsize=10)
    ax2.hlines(config.TARGET_DAY_LUX, 0.6, days + 0.2, color=MUTED, lw=1)
    ax2.text(days + 0.4, config.TARGET_DAY_LUX - 14, f"기본 목표 {config.TARGET_DAY_LUX:.0f}", color=MUTED,
             va="center", fontsize=10)
    ax1.set_title("하루 수동 조작 횟수 (사용자 3명 평균)", loc="left", fontsize=13, fontweight="bold", color=INK)
    ax2.set_title("배운 주간 목표 조도 (lux)", loc="left", fontsize=13, fontweight="bold", color=INK)
    for ax in (ax1, ax2):
        ax.set_xlabel("사용 일수")
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.set_xticks(x)
    ax1.set_ylim(bottom=0)
    ax1.set_xlim(0.5, days + 2.3)
    ax2.set_xlim(0.5, days + 4.2)
    fig.suptitle("개인 선호 보정: 쓸수록 직접 조작이 줄고 목표가 사용자에게 맞춰진다", x=0.03, ha="left",
                 fontsize=15, fontweight="bold", color=INK)
    fig.text(0.03, 0.01, f"가상 사용자 3명 × 날씨 {reps}가지 평균. 선호에서 25% 넘게 벗어나면 70% 확률로 직접 조작, 30분 뒤 자동 복귀",
             fontsize=10, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.98, top=0.84, bottom=0.17, wspace=0.16)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("저장:", out)


if __name__ == "__main__":
    main()
