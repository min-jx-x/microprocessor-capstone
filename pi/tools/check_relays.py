"""릴레이 확인 (Pi에서 실행, 반드시 교류 220V를 연결하지 않은 상태에서).

실행 (레포 최상위):
  python -m pi.tools.check_relays --each      릴레이 신호를 하나씩 켰다 끄기 (SA → PA → SB → PB)
  python -m pi.tools.check_relays --levels    0~5단계를 차례로 적용 (Enter로 다음 단계)
  python -m pi.tools.check_relays --mock ...  Pi 없이 노트북에서 실제 GpioRelays 코드 시험 (gpiozero 가짜 핀)
  python -m pi.tools.check_relays --sim ...   GpioRelays 없이 가짜 릴레이로 흐름만 확인

확인할 것
  --each   : 이름과 다른 릴레이가 켜지면 배선이나 GPIO 번호(config.GPIO_PINS) 문제
             '켜짐'인데 LED가 꺼지고 '꺼짐'인데 켜지면 RELAY_ACTIVE_LOW 를 반대로
             SA, SB는 릴레이 2개가 같이 딸깍해야 정상 (두 선 동시 전환)
  --levels : 화면의 '예상 상태'와 릴레이 LED가 같은지
끝날 때와 Ctrl+C 때 항상 모든 릴레이를 끈다.
"""
import argparse
import os
import sys
import time

NAMES = ("SA", "PA", "SB", "PB")
ROLE = {"SA": "필름 A 전압 선택 (켜짐=100V, 꺼짐=45V)", "PA": "필름 A 전원",
        "SB": "필름 B 전압 선택 (켜짐=100V, 꺼짐=45V)", "PB": "필름 B 전원"}
FILM = {"off": "꺼짐", "low": "45V", "high": "100V"}


def make_relays(sim: bool, mock: bool):
    if sim:
        from pi.devices.sim import SimRelays
        return SimRelays()
    if mock:
        # gpiozero의 가짜 핀: 실제 GPIO 없이 GpioRelays 코드가 맞는지 확인할 수 있다
        os.environ["GPIOZERO_PIN_FACTORY"] = "mock"
    try:
        from pi.devices.relays import GpioRelays
    except ImportError as e:
        raise SystemExit(f"pi/devices/relays.py 를 불러올 수 없음 (대현 작업 파일): {e}")
    return GpioRelays()


def pin_levels(relays) -> str:
    """mock 모드일 때 실제 핀 전압(0/1)을 보여준다. 다른 모드에서는 빈 문자열."""
    if os.environ.get("GPIOZERO_PIN_FACTORY") != "mock":
        return ""
    try:
        from gpiozero import Device
        from pi import config
        f = Device.pin_factory
        return "  핀 전압(저레벨 트리거면 0이 켜짐): " + " ".join(f"{n}=GPIO{p}:{int(f.pin(p).state)}" for n, p in config.GPIO_PINS.items())
    except Exception:
        return ""


def confirm_no_ac() -> None:
    print("주의: 변압기 플러그를 뽑아 교류(220V/100V)가 연결되지 않은 상태에서만 실행하세요.")
    if input("교류 연결이 없나요? (y 입력): ").strip().lower() != "y":
        raise SystemExit("중단")


def each(relays, hold: float) -> None:
    for name in NAMES:
        print(f"\n{name} 켜짐  ← {ROLE[name]}{pin_levels(relays)}")
        relays.set(name, True)
        time.sleep(hold)
        relays.set(name, False)
        print(f"{name} 꺼짐{pin_levels(relays)}")
        time.sleep(0.5)


def levels(relays, auto: bool) -> None:
    from pi import config
    from pi.control.loop import LevelDriver
    from pi.control.placeholders import relay_plan
    drv = LevelDriver(relays)
    for lv in range(config.NUM_LEVELS):
        a, b = config.LEVELS[lv]
        drv.apply(lv)
        plan = relay_plan(lv)
        on = [n for n in NAMES if plan[n]] or ["없음"]
        print(f"\n{lv}단계  필름 A {FILM[a]} / B {FILM[b]}   예상 켜짐: {', '.join(on)}{pin_levels(relays)}")
        if auto:
            time.sleep(1.0)
        else:
            input("  릴레이 LED가 예상과 같으면 Enter")


def main() -> None:
    ap = argparse.ArgumentParser(description="릴레이 확인 (교류 연결 없이)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--each", action="store_true", help="신호 하나씩 켰다 끄기")
    g.add_argument("--levels", action="store_true", help="0~5단계 차례로 적용")
    ap.add_argument("--hold", type=float, default=1.5, help="--each 에서 켜 두는 시간(초)")
    ap.add_argument("--sim", action="store_true", help="가짜 릴레이")
    ap.add_argument("--mock", action="store_true", help="gpiozero 가짜 핀으로 실제 GpioRelays 시험")
    ap.add_argument("--yes", action="store_true", help="확인 질문 건너뛰기 (자동 시험용)")
    args = ap.parse_args()

    if not (args.sim or args.mock or args.yes):
        confirm_no_ac()
    relays = make_relays(args.sim, args.mock)
    try:
        relays.all_off()
        if args.each:
            each(relays, args.hold)
        else:
            levels(relays, auto=args.yes or args.sim or args.mock)
    except KeyboardInterrupt:
        print("\n중단")
    finally:
        relays.all_off()
        relays.close()
        print("\n모든 릴레이 꺼짐")
    sys.exit(0)


if __name__ == "__main__":
    main()
