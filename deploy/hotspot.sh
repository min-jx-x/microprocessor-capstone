#!/usr/bin/env bash
# LightQ: Pi 자체 Wi-Fi 핫스팟 (인터넷 없이 휴대폰이 접속)
# 사용법:
#   bash deploy/hotspot.sh on  비밀번호8자이상   핫스팟 만들기 (부팅할 때도 자동으로 켜짐)
#   bash deploy/hotspot.sh off                   핫스팟 끄기 (원래 Wi-Fi로 돌아감)
#   bash deploy/hotspot.sh status                상태와 Pi 주소 확인
# 주의: 핫스팟을 켜면 Pi의 Wi-Fi(wlan0)가 핫스팟 전용이 되어 인터넷이 끊긴다.
#       코드 업데이트(git pull)는 핫스팟을 끄거나 유선 랜으로 한다.
set -euo pipefail
NAME="LightQ"
SSID="${LIGHTQ_SSID:-LightQ}"

case "${1:-status}" in
  on)
    PW="${2:-}"
    if [ "${#PW}" -lt 8 ]; then
      echo "비밀번호는 8자 이상:  bash deploy/hotspot.sh on 비밀번호"; exit 1
    fi
    sudo nmcli connection delete "$NAME" >/dev/null 2>&1 || true
    sudo nmcli connection add type wifi ifname wlan0 con-name "$NAME" autoconnect yes ssid "$SSID" \
      802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PW"
    sudo nmcli connection modify "$NAME" connection.autoconnect-priority 100
    sudo nmcli connection up "$NAME"
    ;;
  off)
    sudo nmcli connection down "$NAME" || true
    sudo nmcli connection modify "$NAME" connection.autoconnect no || true
    ;;
  status)
    nmcli -f NAME,TYPE,DEVICE,STATE connection show --active || true
    ;;
  *)
    echo "사용법: bash deploy/hotspot.sh on 비밀번호 | off | status"; exit 1 ;;
esac

# 핫스팟(공유 모드) 기본 주소는 보통 10.42.0.1 (확인 필요 → 아래 출력으로 확인)
echo
echo "Pi 주소:"
ip -4 addr show wlan0 | awk '/inet /{print "  " $2}' || true
echo "휴대폰: Wi-Fi '$SSID' 접속 → 브라우저에서 http://위주소(슬래시 앞부분):5000"
