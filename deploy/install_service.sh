#!/usr/bin/env bash
# LightQ: 부팅하면 웹 서버가 자동으로 켜지게 설치
# 사용법:
#   bash deploy/install_service.sh                         기본: --real (실제 시각)
#   bash deploy/install_service.sh "--real --start 11:00 --speed 0"   시연: 시각 11:00 고정
#   bash deploy/install_service.sh remove                  자동 실행 해제
# 확인:  systemctl status lightq     로그:  journalctl -u lightq -f
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

if [ "${1:-}" = "remove" ]; then
  sudo systemctl disable --now lightq || true
  sudo rm -f /etc/systemd/system/lightq.service /etc/default/lightq
  sudo systemctl daemon-reload
  echo "자동 실행 해제됨"; exit 0
fi

ARGS="${1:---real}"
sed -e "s|__USER__|$USER|g" -e "s|__REPO__|$REPO|g" deploy/lightq.service \
  | sudo tee /etc/systemd/system/lightq.service >/dev/null
echo "LIGHTQ_ARGS=$ARGS" | sudo tee /etc/default/lightq >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now lightq
sleep 2
systemctl --no-pager status lightq | head -12
echo
echo "옵션 바꾸기: bash deploy/install_service.sh \"새 옵션\"   (다시 실행하면 덮어씀)"
