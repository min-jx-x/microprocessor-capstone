"""릴레이 드라이버 동작 시험 스크립트.

각 릴레이(SA, PA, SB, PB)를 순서대로 켰다 끄며 동작을 확인한다.
Pi 실기에서는 교류(220V/100V) 플러그를 뽑은 상태에서 'python -m pi.tests.try_relays'로 실행한다.
노트북 환경에서는 '--mock' 옵션으로 가짜 핀 모의 시험을 수행할 수 있다.
"""
import argparse
import os
import time

from pi import config
from pi.devices.relays import GpioRelays


def main() -> None:
    parser = argparse.ArgumentParser(description="릴레이 드라이버 동작 시험")
    parser.add_argument("--mock", action="store_true", help="gpiozero mock 핀 팩토리로 시험")
    parser.add_argument("--hold", type=float, default=config.SAMPLE_PERIOD_S, help="릴레이 켜짐 유지 시간(초)")
    args = parser.parse_args()

    if args.mock:
        os.environ["GPIOZERO_PIN_FACTORY"] = "mock"

    relays = GpioRelays()
    print("릴레이 동작 시험을 시작합니다. (주의: 반드시 교류 전원 미연결 상태에서 시험)")
    print("릴레이 순서: SA -> PA -> SB -> PB\n")

    try:
        for name, pin in config.GPIO_PINS.items():
            print(f"[{name}] 켜짐 (GPIO {pin})...")
            relays.set(name, True)
            time.sleep(args.hold)
            print(f"[{name}] 꺼짐")
            relays.set(name, False)
            time.sleep(config.RELAY_SETTLE_S)
        print("\n모든 릴레이 순차 시험 완료 (전체 꺼짐 상태 확인).")
    except KeyboardInterrupt:
        print("\n시험을 중단했습니다.")
    finally:
        relays.close()


if __name__ == "__main__":
    main()
