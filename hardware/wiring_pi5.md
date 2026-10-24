# 배선 (저전압 쪽, Raspberry Pi 5)

GPIO 번호는 BCM 기준이고, 괄호 안은 40핀 헤더의 물리 핀 번호입니다. 번호는 `pi/config.py`의 `GPIO_PINS`와 같아야 합니다.

## 조도센서 BH1750 (GY-302)

| 센서 핀 | Pi 5 |
|---|---|
| VCC | 3.3V (1번 핀) |
| GND | GND (6번 핀) |
| SDA | GPIO2 / SDA1 (3번 핀) |
| SCL | GPIO3 / SCL1 (5번 핀) |
| ADDR | 연결 안 함 → 주소 0x23 |

확인: `sudo raspi-config`에서 I2C 켜기 → `i2cdetect -y 1`에 `23`이 보여야 합니다.

## 릴레이 모듈 6개

| 신호 | GPIO (물리 핀) | 연결할 릴레이 | 역할 |
|---|---|---|---|
| SA | GPIO17 (11번) | SA1, SA2 두 개의 IN | 필름 A 전압 선택 (꺼짐 = 45V, 켜짐 = 100V) |
| PA | GPIO27 (13번) | PA의 IN | 필름 A 전원 |
| SB | GPIO22 (15번) | SB1, SB2 두 개의 IN | 필름 B 전압 선택 |
| PB | GPIO23 (16번) | PB의 IN | 필름 B 전원 |

- 릴레이 모듈 VCC → 5V (2번 또는 4번 핀), GND → GND (9·14·20번 등)
- 선택 릴레이는 변압기 두 출력이 서로 다른 회로라 **두 선을 함께** 바꿔야 해서 필름마다 2개를 같은 GPIO에 연결합니다.
- 접점: 선택 릴레이 NC = 45V(T2), NO = 100V(T1)

## 확인 필요

- 5V 릴레이 모듈이 Pi의 3.3V 신호로 확실히 켜지고 꺼지는지. 저레벨 트리거 모듈은 3.3V에서 완전히 꺼지지 않는 경우가 있습니다. **220V 없이** 릴레이만 연결해 딸깍 소리와 LED로 먼저 시험합니다.
- 저레벨 트리거인지 고레벨 트리거인지 → `pi/config.py`의 `RELAY_ACTIVE_LOW`
- GPIO 하나에 릴레이 IN 2개를 연결했을 때 전류가 충분한지 (광커플러 입력 기준이면 대체로 문제없음)

## 시험 순서

1. 센서만 연결 → `i2cdetect -y 1` → `python -m pi.tools.check_sensor`
2. 릴레이만 연결 (교류 연결 없음) → `python -m pi.tools.check_relays --each`, `--levels` → 웹 `--real` 수동 모드로 0~5단계
3. 멀티미터로 T1·T2 출력 전압 측정 (필름 연결 전)
4. [safety_checklist.md](safety_checklist.md) 확인 후 교류 연결, 3단계(필름 1장)부터
