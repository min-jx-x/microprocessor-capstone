# firmware (참고용)

초기에 Arduino Uno로 센서 읽기와 단계 판단을 하던 프로토타입입니다.
메인 보드를 Raspberry Pi 5로 바꾸면서 실제 실행 코드는 `pi/`로 옮겼습니다.

- `sketches/capstone_main/decision.h`: 단계 판단 규칙의 원형. `pi/control/decide.py`로 옮김
- `sketches/capstone_main/params.h`: 초기 설정값. `tools/`의 일부 스크립트가 아직 읽고 있어 남겨 둠
