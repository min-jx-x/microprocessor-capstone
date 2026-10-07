"""시리얼로 들어오는 CSV 로그를 파일로 저장한다.

사용법:
    pip install pyserial
    python tools/logger.py --port COM3
    python tools/logger.py --port /dev/ttyUSB0 --out data/raw/test1.csv

펌웨어가 보내는 형식: ms,hour,lux,level
'#'로 시작하는 줄(펌웨어 메시지)은 화면에만 표시하고 파일에는 저장하지 않는다.
"""
import argparse
import os
import sys
import time

import serial  # pip install pyserial

HEADER = "ms,hour,lux,level"


def valid_line(line: str) -> bool:
    parts = line.split(",")
    if len(parts) != 4 or not parts[0].isdigit():
        return False
    try:
        int(parts[1])
        float(parts[2])
        int(parts[3])
    except ValueError:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="예: COM3, /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = args.out or time.strftime("data/raw/log_%Y%m%d_%H%M%S.csv")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    count = 0
    with serial.Serial(args.port, args.baud, timeout=1) as ser, open(out, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write(HEADER + "\n")
        print(f"logging to {out} (Ctrl+C로 종료)")
        try:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("#"):
                    print(line)
                    continue
                if valid_line(line):
                    f.write(line + "\n")
                    f.flush()
                    count += 1
                    if count % 30 == 0:
                        print(f"{count} rows")
        except KeyboardInterrupt:
            print(f"\n종료: {count} rows saved to {out}")
            sys.exit(0)


if __name__ == "__main__":
    main()
