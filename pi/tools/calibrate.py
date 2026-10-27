"""단계별 조도 측정 및 룩업테이블(LUT) 생성 스크립트.

값 순서 기준 (0 ~ 5단계):
    0단계: 꺼짐/꺼짐 (off / off)
    1단계: 45V/꺼짐 (low / off)
    2단계: 45V/45V  (low / low)
    3단계: 100V/꺼짐 (high / off)
    4단계: 100V/45V  (high / low)
    5단계: 100V/100V (high / high)

Pi(또는 시뮬레이션 모드)에서 실행하여 0~5단계를 차례로 적용하고,
각 단계에서 3초간 안정화 대기 후 조도(lux)를 10번 측정하여 평균을 계산한다.
결과는 pi/data/lut.json에 저장된다.

사용법:
    python pi/tools/calibrate.py --sim                  # 시뮬레이션 모드로 가짜 측정 및 lut.json 생성
    python pi/tools/calibrate.py --lamp-step 7          # 실제 Pi에서 실행 (스탠드 밝기 7단계)
    python pi/tools/calibrate.py --sim --settle 0.1     # 빠른 시뮬레이션 시험
"""
import argparse
from datetime import datetime
import json
import os
import sys
import time

# 저장소 루트를 sys.path에 추가하여 어디서든 실행 가능하게 설정
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_OUT = os.path.join(REPO_ROOT, "pi", "data", "lut.json")

# 단계별 필름 조합 (A 필름, B 필름)
LEVEL_COMBOS = [
    ("off", "off"),   # 0단계: 꺼짐/꺼짐
    ("low", "off"),   # 1단계: 45V/꺼짐
    ("low", "low"),   # 2단계: 45V/45V
    ("high", "off"),  # 3단계: 100V/꺼짐
    ("high", "low"),  # 4단계: 100V/45V
    ("high", "high"), # 5단계: 100V/100V
]

COMBO_NAMES = [
    "꺼짐/꺼짐",
    "45V/꺼짐",
    "45V/45V",
    "100V/꺼짐",
    "100V/45V",
    "100V/100V",
]


def get_devices(sim: bool):
    """센서, 릴레이, 레벨 드라이버를 로드한다."""
    if sim:
        from pi.devices.sim import SimRelays, SimSensor
        from pi.control.loop import LevelDriver

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

    try:
        from pi.control.loop import LevelDriver
    except ImportError:
        try:
            from pi.control.levels import LevelDriver
        except ImportError:
            from pi.control.placeholders import LevelDriver

    driver = LevelDriver(relays)
    return sensor, relays, driver


def run_calibration(sim: bool, settle_s: float, samples: int, lamp_step: int, out_path: str):
    sensor, relays, driver = get_devices(sim)

    num_levels = len(LEVEL_COMBOS)
    lux_list = []

    print("=" * 65)
    print("           단계별 조도 캘리브레이션 측정 (0~5단계)           ")
    print("=" * 65)
    print(f"동작 모드       : {'시뮬레이션 (--sim)' if sim else '실제 하드웨어'}")
    print(f"스탠드 밝기 단계: {lamp_step} 단계")
    print(f"단계별 대기 시간: {settle_s:.1f} 초")
    print(f"단계별 샘플 수  : {samples} 회")
    print(f"측정 조합 순서  : {', '.join(COMBO_NAMES)}")
    print(f"결과 저장 경로  : {out_path}")
    print("-" * 65)

    try:
        for lv in range(num_levels):
            combo_label = f"{lv}단계 [{COMBO_NAMES[lv]}]"
            print(f"[{combo_label} 적용 중...] 릴레이 설정 및 {settle_s:.1f}초 안정화 대기...", end="", flush=True)
            driver.apply(lv)
            time.sleep(settle_s)

            readings = []
            for _ in range(samples):
                val = sensor.read_lux()
                if val is not None:
                    readings.append(val)
                time.sleep(0.1)

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

        # ratio 계산 (각 단계 lux / 5단계 lux)
        top_lux = lux_list[5] if lux_list[5] > 0 else 1.0
        ratio_list = [round(x / top_lux, 2) for x in lux_list]

        measured_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
        result = {
            "levels": num_levels,
            "combos": [list(x) for x in LEVEL_COMBOS],
            "combinations": COMBO_NAMES,
            "lux": lux_list,
            "ratio": ratio_list,
            "lamp_step": lamp_step,
            "measured_at": measured_at,
        }

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print("\n[저장 완료]")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n성공적으로 '{out_path}'에 룩업테이블이 저장되었습니다.")

        return result

    finally:
        # 안전 복구: 0단계로 초기화 후 릴레이 및 센서 종료
        try:
            driver.apply(0)
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
    args = parser.parse_args()

    run_calibration(
        sim=args.sim,
        settle_s=args.settle,
        samples=args.samples,
        lamp_step=args.lamp_step,
        out_path=args.out,
    )


if __name__ == "__main__":
    main()
