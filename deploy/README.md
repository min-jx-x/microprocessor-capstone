# Raspberry Pi 5 설치와 시험 순서

Pi를 받은 날 이 순서대로 하면 됩니다. 명령은 복사해서 붙여넣기만 하면 됩니다.
**교류(변압기)는 7단계 전까지 절대 연결하지 않습니다.**

## 0. 준비물

- Raspberry Pi 5, microSD 카드(32GB 이상), USB-C 전원 어댑터(5V 5A 27W 권장)
- 노트북 (SD 카드 슬롯 또는 USB 카드 리더)
- 인터넷 되는 Wi-Fi 하나. 학교 Wi-Fi가 로그인 방식이면 **휴대폰 핫스팟**이 편합니다.
- 조도센서 BH1750, 릴레이 모듈 6개, 점퍼선 (배선은 [../hardware/wiring_pi5.md](../hardware/wiring_pi5.md))

## 1. microSD에 OS 설치 (노트북에서)

1. Raspberry Pi Imager 설치: https://www.raspberrypi.com/software/
2. 장치 **Raspberry Pi 5**, OS **Raspberry Pi OS (64-bit)**, 저장소 **microSD 카드**
3. "OS 사용자 지정"(설정 편집)에서 미리 입력합니다. 이걸 해 두면 모니터·키보드 없이 노트북에서 접속할 수 있습니다.
   - 호스트 이름: `lightq`
   - 사용자 이름 / 비밀번호: 팀이 정한 값 (잊지 않게 기록)
   - 무선 LAN: 위의 인터넷 되는 Wi-Fi 이름과 비밀번호, 국가 `KR`
   - 로케일: 시간대 `Asia/Seoul`
   - 서비스 탭: **SSH 사용**, 비밀번호 인증
4. 쓰기 → 끝나면 카드를 Pi에 꽂고 전원 연결. 첫 부팅은 1~2분 걸립니다.

## 2. 노트북에서 Pi 접속

노트북도 **같은 Wi-Fi**에 연결한 뒤 cmd에서:

```
ssh 사용자이름@lightq.local
```

처음 물어보는 질문에는 `yes`, 그다음 비밀번호. 안 되면 문제 해결 표 참고.

## 3. 코드 받기와 설치 (Pi에서)

```bash
git clone https://github.com/min-jx-x/microprocessor-capstone.git
cd microprocessor-capstone
bash deploy/setup_pi.sh
sudo reboot
```

`setup_pi.sh`가 패키지 설치, I2C 켜기, 권한, 가상환경(`.venv`), 자동 테스트까지 합니다. 마지막에 `passed`가 나오면 정상입니다.
재부팅 후 다시 `ssh`로 접속하고 `cd microprocessor-capstone`.

## 4. 장치 없이 웹 확인 (Pi에서)

```bash
.venv/bin/python -m pi.app --speed 720 --start 06:30
```

노트북 브라우저에서 `http://lightq.local:5000` → 노트북에서 보던 화면이 그대로 나오면 Pi 쪽 설치는 끝입니다. Ctrl+C로 끄기.

## 5. 조도센서 (전원 끄고 연결 → 켜고 확인)

```bash
i2cdetect -y 1                              # 표에 23 이 보여야 함
.venv/bin/python -m pi.tools.check_sensor   # 1초마다 lux 출력
```

손으로 센서를 가리면 숫자가 줄고, 스탠드를 비추면 늘어야 합니다.

## 6. 릴레이 (교류 연결 없이)

```bash
.venv/bin/python -m pi.tools.check_relays --each     # SA → PA → SB → PB 순서 (3단계 모드: SA·SB는 연결 안 함)
.venv/bin/python -m pi.tools.check_relays --levels   # 모든 단계(3단계 모드 0~2), Enter로 다음
.venv/bin/python -m pi.app --real                    # 웹 수동 버튼으로 단계 바꾸며 LED 확인
```

- 이름과 다른 릴레이가 켜지면: 배선 또는 `pi/config.py`의 `GPIO_PINS`
- 켜짐/꺼짐이 반대면: `pi/config.py`의 `RELAY_ACTIVE_LOW`에서 그 릴레이 값을 반대로 바꾼 뒤 `bash deploy/setup_pi.sh` 다시 실행, 재부팅 (부팅 중 꺼짐 레벨도 같이 바뀜)
- PA·PA2(PB·PB2) 중 하나만 반대로 움직이면: 모듈 트리거 방식이 다른 것. H/L 점퍼를 PA·PB와 같게 맞추거나 같은 타입 모듈로 교체 (코드로는 못 고침)
- 3단계 모드: PA는 PA·PA2, PB는 PB·PB2 두 개가 같이 움직여야 정상 (6단계 모드: SA, SB도 릴레이 2개씩)

## 7. 교류 연결 (팀 자체 점검표 확인 후)

1. 변압기만 꽂고 멀티미터로 T1(약 100V), T2(약 45V) 출력 측정 → T2가 필름 구동 전압 60~70V 이하인지. 3단계 모드에서는 T1 100V를 필름에 쓰지 않음
2. [../hardware/safety_checklist.md](../hardware/safety_checklist.md) 전부 체크
3. 필름 A만 연결 → 웹 수동 모드로 0·1단계 확인
4. 필름 B 연결 → 0~2단계 전체 확인

## 8. 단계별 실측과 재학습

1. LED 스탠드 밝기·거리를 고정하고, 웹 수동 모드로 0~2단계를 하나씩 켜서 화면의 실내 조도를 기록
2. 스탠드를 끄고 잡광도 한 번 기록
3. **노트북에서** (Pi에서 git push 설정을 하지 않아도 되도록):

```
python -m pi.calib --lux 0단계 1단계 2단계 --ambient 잡광 --note "스탠드 밝기·거리"
python -m pi.ai.retrain
python -m pi.ai.plot_compare
```

값 순서는 단계표 기본 순서(꺼짐/꺼짐, 45V/꺼짐, 45V/45V)입니다. 6단계 모드는 명령 앞에 `LIGHTQ_LEVELS=6`을 붙이고 값 6개를 넣습니다(서비스로 돌릴 때는 systemd 파일에 `Environment=LIGHTQ_LEVELS=6`).
결과(`pi/data/lut.json`, `pi/data/ai_tree.json`, `docs/images/`)를 커밋·PR → Pi에서 `git pull`.

## 9. 시연 준비: 핫스팟과 자동 실행

```bash
bash deploy/hotspot.sh on 비밀번호8자이상            # Pi가 Wi-Fi 'LightQ'를 만든다
bash deploy/install_service.sh "--real --start 11:00 --speed 0"   # 부팅하면 서버 자동 실행, 시각 11:00 고정
```

- 휴대폰: Wi-Fi `LightQ` 접속 → `http://10.42.0.1:5000` (주소는 `hotspot.sh`가 출력, 확인 필요)
- 핫스팟을 켜면 Pi의 인터넷이 끊깁니다. 코드 업데이트는 `bash deploy/hotspot.sh off` → `git pull` → `bash deploy/hotspot.sh on 비밀번호`
- 상태: `systemctl status lightq`, 로그: `journalctl -u lightq -f`, 해제: `bash deploy/install_service.sh remove`

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `lightq.local`을 못 찾음 | 노트북과 Pi가 같은 Wi-Fi인지. 휴대폰 핫스팟의 연결된 기기 목록에서 Pi IP를 보고 `ssh 사용자@IP` |
| 첫 부팅 후 Wi-Fi에 안 붙음 | Imager에서 Wi-Fi 이름·비밀번호·국가(KR) 다시 확인. 5GHz 전용이면 2.4GHz 겸용으로 |
| `i2cdetect`에 23이 없음 | SDA=3번, SCL=5번, VCC=3.3V(1번) 핀, `sudo raspi-config` → Interface → I2C |
| GPIO 권한 오류 | `setup_pi.sh` 후 재부팅했는지 (`groups`에 gpio, i2c가 보여야 함) |
| 저전압 경고, 갑자기 재부팅 | 전원 어댑터가 5V 5A인지 |
| 웹은 뜨는데 단계가 안 바뀜 | 화면 빨간 경고(센서 실패) 확인 → 5단계 다시 |

## 10. 음성 명령 LLM 키 (선택)

키가 없어도 음성 명령은 분류기만으로 동작합니다. 키를 넣으면 분류기가 애매한 문장만 Gemini에 묻습니다 (인터넷 필요).

```bash
sudo nano /etc/default/lightq-secrets
```

```
LIGHTQ_LLM_KEY=여기에키
# 예비 키: 위 줄 앞에 #을 붙이고 아래 줄의 #을 지운 뒤 재시작
# LIGHTQ_LLM_KEY=예비키
```

```bash
sudo chmod 600 /etc/default/lightq-secrets
bash deploy/install_service.sh "--real --start 11:00 --speed 0"   # 서비스 파일을 새로 써서 이 파일을 읽게 함
```

- 키는 레포·카톡·채팅에 올리지 않습니다. `install_service.sh`는 `/etc/default/lightq`만 덮어쓰고 이 파일은 건드리지 않습니다.
- 모델 바꾸기: 같은 파일에 `LIGHTQ_LLM_MODEL=모델이름` (기본 `gemini-3.1-flash-lite`)
- 키 확인(노트북 cmd): `set LIGHTQ_LLM_KEY=키` → `python -m pi.voice.evaluate --llm --extra "영화 볼 거야"`
- 웹 음성 카드 오른쪽 위가 "분류기 + Gemini"면 키가 적용된 것. 괄호 안에 LLM 오류가 보이면 인터넷이나 키 확인

## 11. Pi 음성 인식 (whisper.cpp, 인터넷 없이)

휴대폰·노트북 웹의 마이크 버튼으로 말하면 Pi가 직접 글자로 바꿉니다. 설치할 때만 인터넷이 필요합니다.

```bash
bash deploy/hotspot.sh off                      # 설치하는 동안 인터넷 Wi-Fi 사용
bash deploy/setup_whisper.sh                    # 빌드 + base-q8_0 모델 + 서비스 lightq-whisper (5~15분, 확인 필요)
bash deploy/make_cert.sh                        # 휴대폰 마이크용 HTTPS 인증서
bash deploy/install_service.sh "--real --start 11:00 --speed 0 --no-learn"   # --no-learn: 재부팅해도 수동 조절 학습 꺼진 채 시작
.venv/bin/python -m pi.voice.stt_check          # "whisper 서버 ...: 켜짐" 확인
bash deploy/hotspot.sh on 비밀번호
```

- 휴대폰: Wi-Fi `LightQ` → `https://10.42.0.1:5443` → "안전하지 않음" 경고에서 고급 → 계속 → 마이크 허용. http 주소로 들어오면 화면에 이 주소가 안내됩니다
- 부스 QR은 `https://10.42.0.1:5443`으로 만들고, 옆에 "경고가 뜨면 고급 → 계속"을 적어 두세요
- 느리면 작은 모델: `bash deploy/setup_whisper.sh tiny-q8_0`, 정확도가 부족하면 큰 모델: `bash deploy/setup_whisper.sh small-q5_1` (속도 확인 필요)
- 정확도 확인: `/etc/default/lightq`에 `LIGHTQ_VOICE_KEEP=20` 한 줄을 추가하고 재시작 → 말해 본 뒤 `.venv/bin/python -m pi.voice.stt_check pi/data/voice_audio/*.wav`. 확인 후 그 줄은 지우기 (관람객 목소리 저장 방지)
- 상태: `systemctl status lightq-whisper`, 로그: `journalctl -u lightq-whisper -f`
