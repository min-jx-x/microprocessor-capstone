"""단계별 조도 측정 및 룩업테이블(LUT) 생성 스크립트.

값 순서 기준은 pi/calib.py의 단계 구성을 따른다 (환경변수 LIGHTQ_LEVELS, 기본 3).
    3단계 모드(기본): 꺼짐/꺼짐, 45V/꺼짐, 45V/45V
    6단계 모드      : 위 3개 + 100V/꺼짐, 100V/45V, 100V/100V

Pi(또는 시뮬레이션 모드)에서 실행하여 모든 단계를 차례로 적용하고,
각 단계에서 3초간 안정화 대기 후 조도(lux)를 10번 측정하여 평균을 계산한다.
측정 전에 광원을 끄고 실내 잡광도 잰다 (--ambient 로 값을 직접 줄 수도 있음).
결과는 pi/data/lut.json에 저장된다.

릴레이는 단계 번호가 아니라 필름 조합으로 직접 켠다. lut.json이 이미 있으면
config.LEVELS가 실측 밝기 순으로 바뀌어 있어서, 단계 번호로 켜면 조합이 어긋나기 때문이다.

사용법:
    python pi/tools/calibrate.py --sim                  # 시뮬레이션 모드로 가짜 측정 및 lut.json 생성
    python pi/tools/calibrate.py --lamp-step 7          # 실제 Pi에서 실행 (스탠드 밝기 7단계)
    python pi/tools/calibrate.py --sim --settle 0.1     # 빠른 시뮬레이션 시험
    python pi/tools/calibrate.py --ambient 5            # 잡광을 이미 알면 광원 끄기 단계 생략
"""
import argparse
import json
import os
import sys
import time

# 저장소 루트를 sys.path에 추가하여 어디서든 실행 가능하게 설정
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_OUT = os.path.join(REPO_ROOT, "pi", "data", "lut.json")

from pi import calib as _calib  # noqa: E402  (sys.path 설정 뒤에 불러온다)

# 단계별 필름 조합 (A 필름, B 필름). 3단계 모드면 3개, 6단계 모드면 6개
LEVEL_COMBOS = list(_calib.DEFAULT_LEVELS)
COMBO_NAMES = [_calib.combo_name(a, b) for a, b in LEVEL_COMBOS]


def get_devices(sim: bool):
    """센서, 릴레이, 레벨 드라이버를 로드한다."""
    if sim:
        from pi.devices.sim import SimRelays, SimSensor
        from pi.control.levels import LevelDriver

        relays = SimRelays()
        # 1000 lux 외부 광원 가정 (노이즈 최소화)
        sensor = SimSensor(relays, outdoor_lux=lambda: 1000.0, ambient_lux=5.0, noise=0.01)
        driver = LevelDriver(relays, settle_s=0.0)
        return sensor, relays, driver

    # 실제 장치 로드 시도
    sensor = None
    relays = None
    driver = None

    try:
        from pi.devices.bh1750 import BH1750Sensor
        sensor = BH1750Sensor()
    except (ImportError, Exception) as e:
        print(f"[calibrate] 실제 센서(BH1750Sensor) 로드 실패: {e}")
        print("  --> 대현의 드라이버가 준비되지 않았으면 --sim 옵션을 사용하세요.")
        sys.exit(1)

    try:
        from pi.devices.relays import GpioRelays
        relays = GpioRelays()
    except (ImportError, Exception) as e:
        print(f"[calibrate] 실제 릴레이(GpioRelays) 로드 실패: {e}")
        print("  --> 대현의 드라이버가 준비되지 않았으면 --sim 옵션을 사용하세요.")
        sensor.close()
        sys.exit(1)

    from pi.control.levels import LevelDriver
    driver = LevelDriver(relays)
    return sensor, relays, driver


def measure(sensor, samples: int) -> list:
    readings = []
    for _ in range(samples):
        val = sensor.read_lux()
        if val is not None:
            readings.append(val)
        time.sleep(0.1)
    return readings


def measure_ambient(sensor, driver, sim: bool, settle_s: float, samples: int,
                    lamp_step: int) -> float:
    """광원을 끈 상태의 실내 잡광. 필름과 무관한 빛이라 투과율 계산에서 뺀다."""
    driver.apply_combo("off", "off")
    if sim:
        outdoor = sensor.outdoor_lux
        sensor.outdoor_lux = lambda: 0.0        # 시뮬레이션: 광원을 끈 것처럼
    else:
        input("광원(스탠드)을 끄고 Enter를 누르세요...")
    try:
        time.sleep(settle_s)
        readings = measure(sensor, samples)
    finally:
        if sim:
            sensor.outdoor_lux = outdoor
    if not readings:
        raise RuntimeError("잡광 측정에서 유효한 조도 값을 읽지 못했습니다.")
    ambient = round(sum(readings) / len(readings), 1)
    print(f"[잡광] {ambient:.1f} lux (표본 {len(readings)}개)")
    if not sim:
        input(f"광원을 다시 켜고(밝기 {lamp_step}단계) Enter를 누르세요...")
    return ambient


def run_calibration(sim: bool, settle_s: float, samples: int, lamp_step: int, out_path: str,
                    ambient=None):
    from pi import calib

    sensor, relays, driver = get_devices(sim)

    num_levels = len(LEVEL_COMBOS)
    lux_list = []

    print("=" * 65)
    print(f"           단계별 조도 캘리브레이션 측정 (0~{num_levels - 1}단계)           ")
    print("=" * 65)
    print(f"동작 모드       : {'시뮬레이션 (--sim)' if sim else '실제 하드웨어'}")
    print(f"스탠드 밝기 단계: {lamp_step} 단계")
    print(f"단계별 대기 시간: {settle_s:.1f} 초")
    print(f"단계별 샘플 수  : {samples} 회")
    print(f"측정 조합 순서  : {', '.join(COMBO_NAMES)}")
    print(f"결과 저장 경로  : {out_path}")
    print("-" * 65)

    try:
        if ambient is None:
            ambient = measure_ambient(sensor, driver, sim, settle_s, samples, lamp_step)
        else:
            print(f"[잡광] 입력값 {ambient:.1f} lux 사용")

        for lv in range(num_levels):
            combo_label = f"{lv}단계 [{COMBO_NAMES[lv]}]"
            print(f"[{combo_label} 적용 중...] 릴레이 설정 및 {settle_s:.1f}초 안정화 대기...", end="", flush=True)
            driver.apply_combo(*LEVEL_COMBOS[lv])
            time.sleep(settle_s)

            readings = measure(sensor, samples)

            if not readings:
                raise RuntimeError(f"{combo_label}에서 유효한 조도 값을 읽지 못했습니다.")

            avg_lux = round(sum(readings) / len(readings), 1)
            lux_list.append(avg_lux)
            print(f" 측정 완료 -> 평균: {avg_lux:.1f} lux (표본 {len(readings)}개)")

        print("-" * 65)

        # 단계 순서 검증 (밝기가 순차적으로 증가해야 함)
        for i in range(len(lux_list) - 1):
            if lux_list[i] > lux_list[i + 1]:
                print(f"[경고] {i}단계({COMBO_NAMES[i]}: {lux_list[i]:.1f} lux)가 {i + 1}단계({COMBO_NAMES[i + 1]}: {lux_list[i + 1]:.1f} lux)보다 밝습니다! 단계 순서가 실측과 다릅니다.")

        # 잡광을 빼고 밝기 순으로 정렬해 저장 (형식은 pi/calib.py와 같음)
        calib.save(out_path, lux_list, ambient, levels=LEVEL_COMBOS, lamp_step=lamp_step)
        with open(out_path, encoding="utf-8") as f:
            result = json.load(f)

        print("\n[저장 완료]")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n성공적으로 '{out_path}'에 룩업테이블이 저장되었습니다.")

        return result

    finally:
        # 안전 복구: 0단계로 초기화 후 릴레이 및 센서 종료
        try:
            driver.apply_combo("off", "off")
            relays.all_off()
            relays.close()
            sensor.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="단계별 조도 측정 및 lut.json 생성 도구")
    parser.add_argument("--sim", action="store_true", help="가짜 장치(시뮬레이터)를 사용하여 측정 실행")
    parser.add_argument("--lamp-step", type=int, default=7, help="측정 시 광원(스탠드) 밝기 단계 (기본값: 7)")
    parser.add_argument("--settle", type=float, default=3.0, help="각 단계 전환 후 대기 시간(초, 기본값: 3.0)")
    parser.add_argument("--samples", type=int, default=10, help="각 단계별 조도 측정 횟수 (기본값: 10)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="결과 json 저장 경로 (기본값: pi/data/lut.json)")
    parser.add_argument("--ambient", type=float, default=None,
                        help="실내 잡광(lux)을 직접 입력. 없으면 광원을 끄고 측정")
    args = parser.parse_args()

    run_calibration(
        sim=args.sim,
        settle_s=args.settle,
        samples=args.samples,
        lamp_step=args.lamp_step,
        out_path=args.out,
        ambient=args.ambient,
    )


if __name__ == "__main__":
    main()
