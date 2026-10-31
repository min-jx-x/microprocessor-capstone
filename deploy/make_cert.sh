#!/usr/bin/env bash
# LightQ: 휴대폰 웹에서 마이크를 쓰기 위한 자체 서명 HTTPS 인증서 (브라우저는 HTTPS에서만 마이크 허용)
# 사용법 (레포 최상위): bash deploy/make_cert.sh
# 결과: pi/data/certs/cert.pem, key.pem (git에 올리지 않음). 웹 서버가 있으면 https://10.42.0.1:5443 도 연다
# 휴대폰에서는 처음 한 번 "안전하지 않음" 경고 → 고급 → 계속(방문)을 눌러야 한다.
set -euo pipefail
OUT="pi/data/certs"
mkdir -p "$OUT"
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -subj "/CN=lightq.local" \
  -addext "subjectAltName=IP:10.42.0.1,DNS:lightq.local,DNS:localhost,IP:127.0.0.1" \
  -keyout "$OUT/key.pem" -out "$OUT/cert.pem"
chmod 600 "$OUT/key.pem"
echo "인증서 만듦: $OUT/cert.pem (서비스 재시작: sudo systemctl restart lightq)"
