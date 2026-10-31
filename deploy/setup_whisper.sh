#!/usr/bin/env bash
# LightQ: Pi 안에서 도는 오프라인 음성 인식(whisper.cpp) 설치
# 사용법 (레포 최상위, 인터넷 연결 상태):
#   bash deploy/setup_whisper.sh              기본 모델 base-q8_0 (한국어 정확도·속도 중간)
#   bash deploy/setup_whisper.sh tiny-q8_0    더 빠르지만 덜 정확
#   bash deploy/setup_whisper.sh small-q5_1   더 정확하지만 느림 (Pi에서 속도 확인 필요)
# 하는 일: 빌드 도구 설치 → ~/whisper.cpp 받아서 whisper-server 빌드 → 모델 받기
#          → systemd 서비스 lightq-whisper 등록 (부팅하면 127.0.0.1:8178에서 자동 실행)
# 확인: systemctl status lightq-whisper / 로그: journalctl -u lightq-whisper -f
set -euo pipefail
MODEL="${1:-base-q8_0}"
DIR="$HOME/whisper.cpp"
PORT=8178

sudo apt-get update
sudo apt-get install -y cmake build-essential git curl

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$DIR"
fi
echo "whisper.cpp 버전: $(git -C "$DIR" log --oneline -1)"

cmake -S "$DIR" -B "$DIR/build" -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
cmake --build "$DIR/build" -j"$(nproc)" --config Release --target whisper-server whisper-cli

bash "$DIR/models/download-ggml-model.sh" "$MODEL" "$DIR/models"
MODEL_PATH="$DIR/models/ggml-$MODEL.bin"
test -f "$MODEL_PATH" || { echo "모델 파일 없음: $MODEL_PATH"; exit 1; }

sudo tee /etc/systemd/system/lightq-whisper.service >/dev/null <<UNIT
[Unit]
Description=LightQ offline speech recognition (whisper.cpp server)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DIR
# 127.0.0.1에서만 받는다 (밖에서 직접 접근 불가, LightQ 웹 서버만 사용)
ExecStart=$DIR/build/bin/whisper-server -m $MODEL_PATH --host 127.0.0.1 --port $PORT -l ko -nt -t $(nproc)
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now lightq-whisper
sleep 3
systemctl --no-pager status lightq-whisper | head -8
echo
echo "모델 바꾸기: bash deploy/setup_whisper.sh 다른모델   (빌드는 다시 하지 않고 모델·서비스만 바뀜)"
echo "속도 확인:   .venv/bin/python -m pi.voice.stt_check 녹음파일.wav"
