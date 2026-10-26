"""BH1750 조도센서 동작 시험 스크립트.

1초마다 lux를 출력한다. 센서를 손으로 가리면 값이 내려가야 한다.
Pi 실기에서는 'python -m pi.tests.try_sensor'로 실행한다.
노트북 등 비-Pi 환경에서는 '--sim' 옵션으로 가짜 센서 흐름을 시험할 수 있다.
"""
import argparse
import time

from pi import config
from pi.devices.sensor import BH1750Sensor


def make_sensor(sim: bool):
    if sim:
        from pi.devices.sim import SimRelays, SimSensor
        return SimSensor(SimRelays(), lambda: config.TARGET_DAY_LUX)
    return BH1750Sensor()


def main() -> None:
    parser = argparse.ArgumentParser(description="BH1750 조도센서 시험 (1초마다 lux 출력)")
    parser.add_argument("--sim", action="store_true", help="가짜 센서로 시험")
    parser.add_argument("-n", type=int, default=0, help="읽을 횟수 (기본 0: 무한 반복, Ctrl+C로 종료)")
    args = parser.parse_args()

    sensor = make_sensor(args.sim)
    print("BH1750 조도센서 시험을 시작합니다. (종료: Ctrl+C)")
    print("센서를 손으로 가렸을 때 lux 값이 정상적으로 내려가는지 확인하세요.\n")

    count = 0
    try:
        while args.n == 0 or count < args.n:
            lux = sensor.read_lux()
            count += 1
            if lux is None:
                print(f"[{count:04d}] 읽기 실패 (None)")
            else:
                bar = "#" * min(int(lux / config.TARGET_WAKE_START_LUX), 50)
                print(f"[{count:04d}] {lux:7.1f} lux  |{bar}")
            time.sleep(config.SAMPLE_PERIOD_S)
    except KeyboardInterrupt:
        print("\n시험을 중단했습니다.")
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
