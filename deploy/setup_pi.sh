#!/usr/bin/env bash
# LightQ: Raspberry Pi 5 처음 설치
# 실행 (레포 최상위에서):  bash deploy/setup_pi.sh
# 하는 일: 패키지 설치 → I2C 켜기 → 릴레이 핀 부팅 상태 → 권한 그룹 → 파이썬 가상환경과 라이브러리 → 테스트
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

echo "== 1/6 시스템 패키지"
sudo apt-get update
# python3-lgpio: Pi 5 GPIO 라이브러리 (pip보다 apt 버전이 안정적)
sudo apt-get install -y git python3-venv python3-pip i2c-tools python3-lgpio python3-gpiozero

echo "== 2/6 I2C 켜기 (조도센서)"
sudo raspi-config nonint do_i2c 0

echo "== 3/6 릴레이 핀을 부팅 직후부터 '꺼짐'으로 고정"
# 서비스가 뜨기 전(부팅 중)에는 GPIO가 입력 상태라 릴레이가 어떻게 될지 알 수 없다.
# config.txt에 출력 레벨을 정해 두면 펌웨어가 부팅 초기에 바로 그 레벨로 둔다.
# 핀 번호와 릴레이별 저레벨 트리거 여부는 pi/config.py 값을 그대로 쓴다 (바꾸면 이 스크립트를 다시 실행)
# 저레벨 트리거(PA·PB)는 HIGH, 고레벨 트리거(SA·SB)는 LOW가 꺼짐이라 줄이 두 개 생긴다.
BOOT_CFG=/boot/firmware/config.txt
GPIO_LINES="$(python3 -c 'from pi import config; print("\n".join(config.boot_gpio_lines()))')"
sudo sed -i '/# LightQ relay off at boot$/d' "$BOOT_CFG"
while read -r line; do
  echo "$line  # LightQ relay off at boot" | sudo tee -a "$BOOT_CFG" >/dev/null
  echo "  $BOOT_CFG 에 추가: $line"
done <<< "$GPIO_LINES"

echo "== 4/6 권한 그룹 (sudo 없이 GPIO·I2C 사용)"
sudo usermod -aG gpio,i2c "$USER"

echo "== 5/6 가상환경 .venv"
# --system-site-packages: apt로 설치한 lgpio·gpiozero를 가상환경에서도 쓰기 위해
if [ ! -d .venv ]; then
  python3 -m venv --system-site-packages .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r pi/requirements.txt

echo "== 6/6 자동 테스트 (장치 없이)"
.venv/bin/python -m pytest pi/tests -q

echo
echo "설치 완료: $REPO"
echo "권한 그룹과 릴레이 부팅 설정을 적용하려면 한 번 재부팅하세요:  sudo reboot"
echo "다음: deploy/README.md 의 3단계(센서 확인)부터"
