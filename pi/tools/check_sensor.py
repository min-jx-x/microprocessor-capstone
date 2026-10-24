"""조도센서 확인 (Pi에서 실행).

실행 (레포 최상위):
  python -m pi.tools.check_sensor            실제 BH1750을 1초마다 10번 읽기
  python -m pi.tools.check_sensor -n 0       멈출 때까지 계속 (Ctrl+C)
  python -m pi.tools.check_sensor --sim      장치 없이 동작만 확인 (노트북)

확인할 것: 값이 나오는지 / 손으로 가리면 줄고 스탠드를 켜면 느는지 / None이 섞이지 않는지
"""
import argparse
import time


def make_sensor(sim: bool):
    if sim:
        from pi.devices.sim import SimRelays, SimSensor
        return SimSensor(SimRelays(), lambda: 1000.0)
    try:
        from pi.devices.bh1750 import BH1750Sensor
    except ImportError as e:
        raise SystemExit(f"pi/devices/bh1750.py 를 불러올 수 없음 (대현 작업 파일): {e}")
    return BH1750Sensor()


def main() -> None:
    ap = argparse.ArgumentParser(description="BH1750 조도센서 확인")
    ap.add_argument("-n", type=int, default=10, help="읽을 횟수 (0이면 계속)")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--sim", action="store_true", help="가짜 센서로 실행")
    args = ap.parse_args()

    sensor = make_sensor(args.sim)
    ok = fail = 0
    i = 0
    try:
        while args.n == 0 or i < args.n:
            try:
                lux = sensor.read_lux()
            except Exception as e:          # 드라이버가 예외를 그대로 던지는 경우도 잡는다
                lux = None
                print(f"  예외: {e}")
            i += 1
            if lux is None:
                fail += 1
                print(f"{i:3d}  읽기 실패")
            else:
                ok += 1
                print(f"{i:3d}  {lux:8.1f} lux  {'#' * min(int(lux / 20), 50)}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
    print(f"\n성공 {ok}회, 실패 {fail}회")
    if fail and not args.sim:
        print("실패가 있으면: ① i2cdetect -y 1 에 23이 보이는지 ② SDA=3번 핀, SCL=5번 핀, VCC=3.3V(1번)"
              " ③ sudo raspi-config 에서 I2C 켜짐 ④ 점퍼선 접촉")


if __name__ == "__main__":
    main()
