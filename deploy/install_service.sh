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
# /etc/default/lightq는 LIGHTQ_ARGS 줄만 바꾸고 나머지 줄(LIGHTQ_POLICY, LIGHTQ_TARGET_DAY_LUX 등 현장 설정)은 남긴다
TMP="$(mktemp)"
if [ -f /etc/default/lightq ]; then
  grep -v '^LIGHTQ_ARGS=' /etc/default/lightq > "$TMP" || true
fi
echo "LIGHTQ_ARGS=$ARGS" >> "$TMP"
sudo install -m 644 "$TMP" /etc/default/lightq
rm -f "$TMP"
echo "/etc/default/lightq:"; sed 's/^/  /' /etc/default/lightq
sudo systemctl daemon-reload
sudo systemctl enable lightq
sudo systemctl restart lightq   # 이미 켜져 있어도 새 설정으로 다시 시작 (enable --now는 켜진 서비스를 재시작하지 않음)
sleep 2
systemctl --no-pager status lightq | head -12
echo
echo "옵션 바꾸기: bash deploy/install_service.sh \"새 옵션\"   (LIGHTQ_ARGS만 바뀌고 다른 줄은 유지)"
