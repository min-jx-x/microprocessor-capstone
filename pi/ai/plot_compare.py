"""규칙 대 AI 비교 그래프 (발표·포스터·README용 PNG).

실행 (레포 최상위): python -m pi.ai.plot_compare
결과:
  docs/images/compare_burst.png    직사광 한 번이 들어올 때 규칙과 AI의 반응 (실제 시간 1배속)
  docs/images/compare_metrics.png  40일 비교 지표 (720배속)
실측 lut.json으로 재학습한 뒤 다시 실행하면 그래프도 실측 기준으로 바뀐다.
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from pi import config  # noqa: E402
from pi.ai.evaluate import compare  # noqa: E402
from pi.ai.offline import BURST_AT, burst_stats, first_darker, run_scene  # noqa: E402
from pi.ai.policy import AIPolicy  # noqa: E402
from pi.control.decide import RulePolicy, load_lut  # noqa: E402

RULE, AI = "#eb6834", "#2a78d6"        # 규칙 주황, AI 파랑 (색약에서도 구분되는 조합)
INK, MUTED, GRID = "#1b1b1a", "#6b6a66", "#e4e3df"


def setup_font() -> None:
    """한글 글꼴: Windows 맑은 고딕 → macOS 애플고딕 → 나눔고딕 → Noto CJK 순으로 찾는다."""
    names = sorted({f.name for f in font_manager.fontManager.ttflist})
    pick = next((n for n in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR")
                 if n in names), None)
    pick = pick or next((n for n in names if "CJK" in n and "Sans" in n), None)
    if pick:
        plt.rcParams["font.family"] = pick
    else:
        print("주의: 한글 글꼴을 찾지 못해 글자가 깨질 수 있음")
    plt.rcParams.update({"axes.unicode_minus": False, "axes.edgecolor": GRID,
                         "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False})


def plot_burst(out: str, seed: int, n_avg: int) -> None:
    lut = load_lut()
    rule, ai = RulePolicy(lut), AIPolicy(lut)
    r, a = run_scene(rule, seed=seed, burst_at=BURST_AT), run_scene(ai, seed=seed, burst_at=BURST_AT)
    # 대표 장면 하나만 보여주면 '고른 결과'일 수 있으므로 n_avg번 평균도 같이 적는다
    sr, sa = burst_stats(rule, n_avg), burst_stats(ai, n_avg)
    m = {"dr": sr["delay"], "da": sa["delay"], "gr": sr["glare"], "ga": sa["glare"]}

    skip = 5                       # 시작 직후 0단계에서 올라가는 몇 초는 잘라낸다
    r, a = r[skip:], a[skip:]
    t = [x["i"] - BURST_AT for x in r]
    b0 = BURST_AT - skip           # 잘라낸 뒤 직사광 시작 위치
    fig, axes = plt.subplots(3, 1, figsize=(12.8, 7.6), dpi=150, sharex=True,
                             gridspec_kw={"height_ratios": [1.1, 2.2, 1.3], "hspace": 0.18})
    ax0, ax1, ax2 = axes

    ax0.plot(t, [x["outdoor"] for x in r], color=MUTED, lw=2)
    ax0.set_ylabel("바깥 빛 (lux)")
    ax0.text(0.5, 0.82, "직사광 시작", transform=ax0.get_xaxis_transform(), color=MUTED, fontsize=10)

    target = r[0]["target"]
    ax1.axhspan(target * 1.3, max(max(x["lux"] for x in r), max(x["lux"] for x in a)) * 1.08,
                color="#fbe3da", lw=0)
    ax1.text(t[-1], target * 1.3 + 8, "눈부심 (목표의 1.3배 초과)", ha="right", va="bottom",
             color=MUTED, fontsize=10)
    ax1.axhline(target, color=INK, lw=1.2, ls=(0, (5, 4)))
    ax1.text(t[0] + 0.3, target + 6, f"목표 {target:.0f} lux", va="bottom", color=INK, fontsize=10)
    ax1.plot(t, [x["lux"] for x in r], color=RULE, lw=2, label="규칙")
    ax1.plot(t, [x["lux"] for x in a], color=AI, lw=2, label="AI")
    ax1.set_ylabel("실내 조도 (lux)")
    ax1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, ncol=2, fontsize=11,
               borderaxespad=0.2)

    ax2.step(t, [x["level"] for x in r], where="post", color=RULE, lw=2)
    ax2.step(t, [x["level"] for x in a], where="post", color=AI, lw=2)
    ax2.set_ylabel("단계")
    top = config.NUM_LEVELS - 1        # 3단계 모드 0~2, 6단계 모드 0~5
    ax2.set_yticks(range(0, top + 1))
    ax2.set_ylim(-0.3, top + 0.3)
    ax2.set_xlabel("직사광 시작 후 시간 (초)")
    dr, da = first_darker(r, b0), first_darker(a, b0)
    lv0 = r[b0]["level"]
    # AI 글자는 선 왼쪽, 규칙 글자는 선 오른쪽에 두어 겹치지 않게
    for d, c, name, tx, ha in ((da, AI, "AI", -0.8, "right"), (dr, RULE, "규칙", dr + 0.4, "left")):
        ax2.annotate(f"{name} {d}초 만에 어둡게", xy=(d, lv0 - 0.5), xytext=(tx, top - 0.5),
                     color=c, fontsize=11, fontweight="bold", ha=ha,
                     arrowprops={"arrowstyle": "-", "color": c, "lw": 1})

    for ax in axes:
        ax.axvline(0, color=MUTED, lw=1, ls=":")
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
    ax2.set_xlim(t[0], t[-1])

    fig.suptitle("직사광이 들어올 때: AI는 빛이 오르는 속도를 보고 먼저 어둡게 한다",
                 x=0.07, ha="left", fontsize=15, fontweight="bold", color=INK, y=0.985)
    fig.text(0.07, 0.925,
             f"직사광 {n_avg}회 평균  반응 시간 규칙 {m['dr']:.1f}초 → AI {m['da']:.1f}초  ·  "
             f"눈부심 시간 규칙 {m['gr']:.1f}초 → AI {m['ga']:.1f}초   (시뮬레이션, 필름 투과율 가정값)",
             fontsize=11, color=MUTED)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.89, bottom=0.08)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print(f"저장: {out}  (대표 장면 seed {seed}: 규칙 {dr}초, AI {da}초)")
    print(f"  {n_avg}회 평균 반응 {m['dr']:.2f} → {m['da']:.2f}초, 눈부심 {m['gr']:.2f} → {m['ga']:.2f}초")


def plot_metrics(out: str, days: int) -> None:
    res = compare(days=days)
    items = (("acc", "정확도", "목표 ±20% 안에 든 비율", "{:.0%}", True),
             ("mape", "평균 오차율", "MAPE", "{:.0%}", False),
             ("glare", "눈부심", "회차/일", "{:.1f}", False),
             ("delay", "반응 지연", "초", "{:.1f}", False),
             ("switches", "단계 전환", "회/일", "{:.1f}", False))
    fig, axes = plt.subplots(1, len(items), figsize=(12.8, 4.6), dpi=150)
    for ax, (k, title, unit, fmt, higher) in zip(axes, items):
        vals = [res["rule"][k], res["ai"][k]]
        bars = ax.bar([0, 1], vals, width=0.62, color=[RULE, AI])
        top = max(vals) * 1.25
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + top * 0.02, fmt.format(v),
                    ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK)
        ax.set_ylim(0, top)
        ax.set_xticks([0, 1], ["규칙", "AI"], fontsize=11, color=INK)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_title(title, fontsize=13, fontweight="bold", color=INK, loc="left", pad=24)
        ax.text(0, 1.02, f"{unit} · {'높을수록' if higher else '낮을수록'} 좋음",
                transform=ax.transAxes, fontsize=9.5, color=MUTED, va="bottom")
    fig.suptitle(f"규칙 대 AI, 같은 날씨 {days}일 비교", x=0.03, ha="left",
                 fontsize=15, fontweight="bold", color=INK)
    fig.text(0.03, 0.02, "시뮬레이션 (기상청 일사 곡선 + 하루 직사광 4~10번, 720배속), 필름 투과율 가정값 기준",
             fontsize=10, color=MUTED)
    fig.subplots_adjust(left=0.03, right=0.99, top=0.74, bottom=0.14, wspace=0.35)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print(f"저장: {out}")
    for k, *_ in items:
        print(f"  {k}: 규칙 {res['rule'][k]:.3f}  AI {res['ai'][k]:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="docs/images")
    ap.add_argument("--seed", type=int, default=9, help="대표 장면 seed (3단계 기준 40회 평균에 가장 가까운 장면)")
    ap.add_argument("--bursts", type=int, default=40, help="직사광 평균에 쓸 횟수")
    ap.add_argument("--days", type=int, default=40)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    setup_font()
    plot_burst(os.path.join(args.outdir, "compare_burst.png"), args.seed, args.bursts)
    plot_metrics(os.path.join(args.outdir, "compare_metrics.png"), args.days)


if __name__ == "__main__":
    main()
