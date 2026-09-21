/*
  단계조광 스마트 블라인드 - 초기 스켈레톤
  부품 확정 전이라 액추에이터 제어부(controlActuator)는 방식 미정 상태의 자리표시자.
  docs/actuator-control-notes.md 에서 방식 확정되면 이 파일도 갱신.

  구성:
    - BH1750 조도센서로 실내 조도(lux) 측정
    - 시간대별 목표조도 테이블과 비교
    - 액추에이터 제어신호 출력 (방식 미정: 릴레이 조합 or PWM-to-0-10V)

  TODO:
    - [ ] BH1750 라이브러리 연동 (Wire.h + BH1750.h)
    - [ ] 시간대 판단 로직 (ESP8266 NTP 연동 또는 RTC 모듈)
    - [ ] 캘리브레이션 룩업테이블 반영 (docs/quantitative-metrics.md)
    - [ ] 액추에이터 제어 방식 확정 후 controlActuator() 구현
*/

// ---- 시간대별 목표 조도 (lux) - 임시값, 실측/문헌 기반으로 조정 예정 ----
struct TargetProfile {
  const char* label;
  int targetLux;
};

TargetProfile profiles[] = {
  {"sleep",   10},   // 취침: 저조도
  {"wake",    200},  // 기상: 점진적 증가 목표
  {"daytime", 500},  // 주간: 일반 실내조도
};

// ---- 캘리브레이션 룩업테이블 자리표시자 ----
// 실측 후 {제어값(전압 또는 릴레이 조합 코드), 실측 lux} 쌍으로 채운다.
struct CalibrationPoint {
  int controlLevel; // 0~N (방식 확정 전 임시 정수 레벨)
  int measuredLux;
};

CalibrationPoint calibrationTable[] = {
  // { 0, 0 },   // 예시: 완전 차단 상태 실측값
  // { 1, 0 },   // TODO: 실측 후 채우기
};

void setup() {
  Serial.begin(9600);
  // TODO: BH1750 초기화 (Wire.begin(); lightMeter.begin();)
}

int readCurrentLux() {
  // TODO: BH1750에서 실제 lux 값 읽기
  return 0; // placeholder
}

int decideTargetLux(const char* timeLabel) {
  for (auto &p : profiles) {
    if (strcmp(p.label, timeLabel) == 0) return p.targetLux;
  }
  return profiles[2].targetLux; // 기본값: daytime
}

int lookupControlLevel(int targetLux) {
  // TODO: calibrationTable을 순회하며 targetLux에 가장 가까운 controlLevel 반환
  // 캘리브레이션 데이터 채워지기 전까지는 임시로 0 반환
  return 0;
}

void controlActuator(int controlLevel) {
  // TODO: 액추에이터 제어 방식 확정 후 구현
  // - 방식 A(0-10V): PWM-to-0-10V 모듈에 아날로그 출력
  // - 방식 B(다단 변압기+릴레이): controlLevel을 릴레이 ON/OFF 조합으로 변환해 출력
  Serial.print("controlActuator called with level=");
  Serial.println(controlLevel);
}

void loop() {
  int currentLux = readCurrentLux();
  const char* currentTimeLabel = "daytime"; // TODO: 시간대 판단 로직으로 대체

  int targetLux = decideTargetLux(currentTimeLabel);
  int controlLevel = lookupControlLevel(targetLux);
  controlActuator(controlLevel);

  delay(1000);
}
