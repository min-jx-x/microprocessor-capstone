# firmware

아두이노 우노(ATmega328P) 스케치 코드. 센서 읽기, 인터럽트 처리, 서버와의 통신, 액추에이터 제어를 담당합니다.

`sketches/` 아래에 스케치별 폴더를 만들어 관리하세요 (예: `sketches/seat_sensor_v1/seat_sensor_v1.ino`).

## dimming_control_v1 테스트 방법 (부품 미도착 상태 — 시뮬레이션 버전)

BH1750 조도센서/릴레이 모듈이 아직 없어도 아두이노 우노 보드 하나로 판단 로직을 미리 테스트할 수 있게 만든 버전. 조도센서 자리는 시리얼 입력으로, 릴레이 자리는 보드 내장 LED로 대체함.

**필요한 것**: 아두이노 우노 R3, USB 케이블. 그 외 부품·라이브러리 설치 불필요.

**절차**
1. Arduino IDE에서 `firmware/sketches/dimming_control_v1/dimming_control_v1.ino` 열기
2. 보드/포트 설정(Arduino Uno) 확인 후 업로드
3. 시리얼모니터 열기 — 통신속도 9600bps, 줄바꿈 옵션은 "새 줄(Newline)"로 설정
4. 입력창에 조도값(숫자, 예: `50`, `300`) 입력 후 엔터
5. 확인할 내용
   - 입력한 값이 "현재 조도"로 반영되는지 (`>> 입력받은 조도값으로 갱신: N` 로그)
   - 시간대(`daytime` 고정, 목표 500lux)와 비교해서 "더 밝게 필요" / "더 어둡게 필요" / "목표 도달" 판단이 값에 따라 올바르게 바뀌는지
   - `controlLevel`이 아직 0으로 고정이라 보드 내장 LED는 계속 꺼져있는 게 정상 (캘리브레이션 테이블이 비어있기 때문 — 필름 실측 전까지는 정상 동작)

**부품 도착 시 교체할 부분** (파일 상단 주석 및 코드 내 TODO 참고)
- BH1750 도착 → `readCurrentLux()`를 실제 센서 읽기 코드로 교체 (Wire.h + BH1750 라이브러리 설치 필요)
- 릴레이 모듈 도착 → `ACTUATOR_INDICATOR_PIN`을 릴레이 연결 핀 번호로 교체
- 필름/파워서플라이 도착 + 제어방식 확정 → `controlActuator()` 실제 구현 (`docs/actuator-control-notes.md` 참고)
- 필름 실측 완료 → `calibrationTable` 채우고 `lookupControlLevel()` 구현 (`docs/quantitative-metrics.md` 참고)
