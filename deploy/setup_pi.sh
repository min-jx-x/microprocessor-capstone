#!/usr/bin/env bash
# LightQ: Raspberry Pi 5 처음 설치
# 실행 (레포 최상위에서):  bash deploy/setup_pi.sh
# 하는 일: 패키지 설치 → I2C 켜기 → 권한 그룹 → 파이썬 가상환경과 라이브러리 → 테스트
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

echo "== 1/5 시스템 패키지"
sudo apt-get update
# python3-lgpio: Pi 5 GPIO 라이브러리 (pip보다 apt 버전이 안정적)
sudo apt-get install -y git python3-venv python3-pip i2c-tools python3-lgpio python3-gpiozero

echo "== 2/5 I2C 켜기 (조도센서)"
sudo raspi-config nonint do_i2c 0

echo "== 3/5 권한 그룹 (sudo 없이 GPIO·I2C 사용)"
sudo usermod -aG gpio,i2c "$USER"

echo "== 4/5 가상환경 .venv"
# --system-site-packages: apt로 설치한 lgpio·gpiozero를 가상환경에서도 쓰기 위해
if [ ! -d .venv ]; then
  python3 -m venv --system-site-packages .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r pi/requirements.txt

echo "== 5/5 자동 테스트 (장치 없이)"
.venv/bin/python -m pytest pi/tests -q

echo
echo "설치 완료: $REPO"
echo "권한 그룹을 적용하려면 한 번 재부팅하세요:  sudo reboot"
echo "다음: deploy/README.md 의 3단계(센서 확인)부터"
