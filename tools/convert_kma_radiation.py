"""기상청 ASOS 시별 일사량(MJ/m2) 데이터를 조도(lux)로 변환하여 로그 CSV로 저장한다.

사용법:
    python tools/convert_kma_radiation.py
    python tools/convert_kma_radiation.py --station 177 --out data/sample_log.csv
    python tools/convert_kma_radiation.py --station 129 --out data/sample_log_seosan.csv

단위 변환 원리:
    1) 기상청 일사량 단위는 1시간 누적 일사량(MJ/m^2).
    2) 1시간(3600초) 동안의 평균 일사강도(Irradiance, W/m^2):
       Irradiance (W/m^2) = (일사량 * 1,000,000 J) / 3600 s = 일사량 * 277.778
    3) 태양광 발광효율(Luminous Efficacy):
       자연광 기준 1 W/m^2 ≈ 110 ~ 120 lux (기본값: 116 lm/W)
       lux = Irradiance * 116 ≈ 일사량(MJ/m^2) * 32,222.22
"""
import argparse
import csv
import glob
import os
import sys

# params_loader 임포트
ai_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "ai"))
if ai_dir not in sys.path:
    sys.path.insert(0, ai_dir)

try:
    from params_loader import load_params, target_lux
except ImportError:
    load_params = None
    target_lux = None


def find_default_kma_csv() -> str:
    matches = glob.glob("data/OBS_ASOS*.csv")
    if matches:
        return matches[0]
    return "data/OBS_ASOS_TIM_20261022222346.csv"


def read_kma_csv(path: str):
    encodings = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.reader(f)
                header = next(reader)
                rows = list(reader)
            return header, rows
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"파일 인코딩을 인식할 수 없습니다: {path}")


def decide_level_from_incident(p: dict, incident_lux: float, hour: int, cur: int) -> int:
    """입사 조도(외부 일사)를 바탕으로 목표 조도를 맞추기 위한 최적 블라인드 단계를 결정한다."""
    if p is None or target_lux is None:
        return 0

    t_targets = p["LUT_T"]
    num_levels = p["NUM_LEVELS"]
    deadband = float(p.get("DEADBAND_T", 0.05))

    target = float(target_lux(p, hour))
    denom = max(float(incident_lux), 1.0)
    t_need = target / denom

    best = 0
    best_err = abs(float(t_targets[0]) - t_need)
    for i in range(1, num_levels):
        err = abs(float(t_targets[i]) - t_need)
        if err < best_err:
            best, best_err = i, err

    cur_err = abs(float(t_targets[cur]) - t_need)
    if cur_err <= best_err + deadband:
        return cur
    return best


def main():
    parser = argparse.ArgumentParser(description="기상청 일사량 데이터를 lux로 변환 (6단계 제어 연동)")
    parser.add_argument("--input", default=None, help="기상청 CSV 경로 (미지정 시 data/OBS_ASOS*.csv 자동 검색)")
    parser.add_argument("--station", default="177", help="관측 지점 번호 (177: 홍성, 129: 서산, 235: 보령 등)")
    parser.add_argument("--out", default="data/sample_log.csv", help="출력 로그 CSV 경로")
    parser.add_argument("--efficacy", type=float, default=116.0, help="태양광 발광효율 (lm/W, 기본값 116.0)")
    parser.add_argument("--step-ms", type=int, default=1000, help="로그 ms 간격 (기본값 1000ms)")
    parser.add_argument("--indoor", action="store_true", help="필름 투과율을 적용한 실내 조도로 저장")
    args = parser.parse_args()

    input_path = args.input or find_default_kma_csv()
    if not os.path.exists(input_path):
        print(f"Error: 입력 파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    header, raw_rows = read_kma_csv(input_path)

    # 지점 컬럼 및 일사 컬럼 인덱스 탐색
    station_idx = None
    name_idx = None
    time_idx = None
    solar_idx = None

    for i, h in enumerate(header):
        h_clean = h.strip()
        if "지점" in h_clean and "명" not in h_clean:
            station_idx = i
        elif "지점명" in h_clean:
            name_idx = i
        elif "일시" in h_clean or "시간" in h_clean:
            time_idx = i
        elif "일사" in h_clean:
            solar_idx = i

    if station_idx is None or time_idx is None or solar_idx is None:
        # fallback by position: 0=지점, 1=지점명, 2=일시, 3=일사
        station_idx, name_idx, time_idx, solar_idx = 0, 1, 2, 3

    # 필터링
    filtered = []
    station_name = ""
    for r in raw_rows:
        if len(r) <= max(station_idx, time_idx, solar_idx):
            continue
        if r[station_idx].strip() == str(args.station).strip():
            if name_idx is not None and len(r) > name_idx:
                station_name = r[name_idx].strip()
            filtered.append(r)

    if not filtered:
        print(f"Error: 지점 코드 {args.station}에 해당하는 데이터가 없습니다.")
        sys.exit(1)

    # 파라미터 로드
    params = None
    if load_params is not None:
        try:
            params = load_params()
        except Exception as e:
            print(f"Warning: params.h 로드 실패 ({e}), 기본 단계 로직 적용")

    # 변환 계수: 1 MJ/m^2 = (1e6 / 3600) W/m^2 * efficacy (lux)
    conversion_factor = (1e6 / 3600.0) * args.efficacy

    output_rows = []
    current_level = int(params["NUM_LEVELS"] - 1) if params else 5
    ms = 0

    print("=" * 60)
    print(f"기상청 일사량 -> 조도(lux) 변환 (6단계 기준)")
    print(f"입력 파일: {input_path}")
    print(f"선택 지점: {args.station} ({station_name})")
    print(f"발광 효율: {args.efficacy} lm/W (1 MJ/m² = {conversion_factor:.1f} lux)")
    print("=" * 60)

    for r in filtered:
        time_str = r[time_idx].strip()
        solar_val_str = r[solar_idx].strip()
        solar_mj = float(solar_val_str) if solar_val_str else 0.0

        # 시간 파싱 (예: '2026-10-20 07:00' -> 7)
        try:
            hour = int(time_str.split()[1].split(":")[0])
        except Exception:
            hour = int(time_str.split(":")[0])

        lux = round(solar_mj * conversion_factor, 1)

        # 다음 블라인드 단계 결정
        next_level = decide_level_from_incident(params, lux, hour, current_level)
        save_lux = lux
        if args.indoor and params and "LUT_T" in params:
            t = float(params["LUT_T"][next_level])
            save_lux = round(lux * t, 1)

        output_rows.append((ms, hour, save_lux, next_level, time_str, solar_mj, lux))

        current_level = next_level
        ms += args.step_ms

    # CSV 파일 작성
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ms", "hour", "lux", "level"])
        for r in output_rows:
            writer.writerow([r[0], r[1], r[2], r[3]])

    print(f"{'시간':^6} | {'일사(MJ/m²)':^11} | {'야외 조도(lux)':^15} | {'저장 lux':^12} | {'결정 단계':^10}")
    print("-" * 65)
    for r in output_rows:
        print(f"{r[1]:02d}시   | {r[5]:>10.2f} | {r[6]:>14.1f} | {r[2]:>11.1f} | {r[3]:>8}")
    print("-" * 65)
    print(f"성공적으로 {len(output_rows)}행이 '{args.out}'에 저장되었습니다.\n")


if __name__ == "__main__":
    main()
