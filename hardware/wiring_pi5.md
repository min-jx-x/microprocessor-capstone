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

## 부팅 중 릴레이 상태

서비스(`lightq`)가 뜨기 전에는 GPIO가 입력 상태라, 저레벨 트리거 모듈은 부팅 동안 릴레이가 켜질 수도 있습니다.
`deploy/setup_pi.sh`가 `/boot/firmware/config.txt`에 아래 줄을 넣어 부팅 직후부터 릴레이 핀을 "꺼짐" 레벨로 고정합니다.

```
gpio=17,27,22,23=op,dh  # LightQ relay off at boot
```

- `dh` = HIGH 출력(저레벨 트리거 모듈에서 꺼짐). 고레벨 트리거면 `dl`. `pi/config.py`의 `RELAY_ACTIVE_LOW`를 따라 자동으로 정해집니다.
- 핀 번호나 `RELAY_ACTIVE_LOW`를 바꾸면 `bash deploy/setup_pi.sh`를 다시 실행하고 재부팅합니다.
- 확인: 220V 없이 재부팅하면서 릴레이 LED가 한 번도 켜지지 않는지 봅니다.

## 시각

핫스팟에는 인터넷이 없어서 Pi가 시각을 맞추지 못합니다. Pi 5의 RTC는 배터리(J5 단자, ML-2020 충전식)가 없으면 전원이 꺼지는 동안 시각을 유지하지 못합니다.

- 웹 대시보드를 휴대폰으로 열면 휴대폰 시각을 보내서, 30초 넘게 차이 나면 프로그램 시계를 맞춥니다 (`/api/time`). 단, `--start`나 `--speed`로 시각을 정한 시연 모드에서는 맞추지 않습니다.
- 프로그램을 다시 시작하면 Pi 시스템 시각으로 돌아가므로, 오래 켜 둘 거라면 RTC 배터리를 다는 것이 확실합니다.

## 확인 필요

- 5V 릴레이 모듈이 Pi의 3.3V 신호로 확실히 켜지고 꺼지는지. 저레벨 트리거 모듈은 3.3V에서 완전히 꺼지지 않는 경우가 있습니다. **220V 없이** 릴레이만 연결해 딸깍 소리와 LED로 먼저 시험합니다.
- 저레벨 트리거인지 고레벨 트리거인지 → `pi/config.py`의 `RELAY_ACTIVE_LOW`
- GPIO 하나에 릴레이 IN 2개를 연결했을 때 전류가 충분한지 (광커플러 입력 기준이면 대체로 문제없음)

## 시험 순서

1. 센서만 연결 → `i2cdetect -y 1` → `python -m pi.tools.check_sensor`
2. 릴레이만 연결 (교류 연결 없음) → `python -m pi.tools.check_relays --each`, `--levels` → 웹 `--real` 수동 모드로 0~5단계
3. 멀티미터로 T1·T2 출력 전압 측정 (필름 연결 전)
4. [safety_checklist.md](safety_checklist.md) 확인 후 교류 연결, 3단계(필름 1장)부터
