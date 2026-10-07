# 팀 인터페이스 약속

> 기존 README는 건드리지 않았다. 필요하면 README에서 이 문서로 링크만 걸어도 된다.

## 1. 단계 결정 함수 (AI/판단 <-> 펌웨어)

```cpp
// 입력: lux (BH1750 측정값, 필름 뒤쪽 = 실내), hour (0~23), cur (현재 단계)
// 출력: 다음 단계 (0 = 가장 불투명 ... NUM_LEVELS-1 = 가장 투명)
int decide(float lux, int hour, int cur);
```

- 구현: `firmware/sketches/capstone_main/decision.h`
- 기본 구현은 룩업테이블 기반 규칙이다.
  1. 입사광 추정: `incident = lux / T[cur]`
  2. 필요 투과율: `T_need = 목표 lux / incident`
  3. `T`가 `T_need`에 가장 가까운 단계를 선택. 현재 단계의 오차가 최적 단계 오차 + `DEADBAND_T` 이하면 유지
- AI 모델을 쓰려면 `server/ai/train.py`가 만든 `model.h`(`ml_predict(lux, hour, cur)`)를 두고 `USE_ML_MODEL`을 정의한다.
  입력 순서(lux, hour, cur)를 바꾸지 않는다.
- 우노는 SRAM이 2KB뿐이라 모델은 작게(결정트리 깊이 6 안팎) 유지한다.

## 2. 튜닝 값: `params.h` 한 곳에서만 관리

`firmware/sketches/capstone_main/params.h` 에 단계 수, 시간대별 목표 lux, 시간대 경계, 데드밴드, 룩업테이블이 있다.
`server/ai` 의 파이썬이 이 파일을 읽으므로 형식(`#define 이름 숫자`, 배열 한 줄)을 바꾸지 않는다.
**현재 값은 모두 임시값이다.** 특히 `LUT_T`, `LUT_PWM`, `LUT_TAP`은 필름과 드라이버를 받아 실측한 뒤 교체해야 한다.

## 3. 로그 CSV (펌웨어 -> 데이터 수집 -> AI)

```
ms,hour,lux,level
12034,14,356.2,3
```

| 컬럼 | 의미 |
|---|---|
| ms | 보드 부팅 후 경과 시간 (ms) |
| hour | 판단에 사용한 시각 (0~23) |
| lux | BH1750 측정값 |
| level | 현재 단계 |

- `#`로 시작하는 줄은 펌웨어 메시지이며 로거가 파일에 저장하지 않는다.
- 학습용으로 쓸 때 `cur`(직전 단계) 컬럼이 필요하다. 로그에서는 직전 행의 `level`로 만들 수 있다. (AI 담당이 변환 스크립트를 추가)
- 로그의 `level`은 "그 시점 규칙이 낸 결과"이므로 라벨로 바로 쓰면 규칙을 그대로 학습한다. 라벨을 무엇으로 할지는 AI 담당이 팀과 정해서 이 문서에 추가한다.

## 4. 룩업테이블 만들기 (곽재우)

1. 필름과 드라이버가 준비되면 `hardware/tests/calibration_sweep` 스케치로 구동값별 lux를 측정한다.
2. 출력된 `drive,lux` 줄을 CSV로 저장 (`data/raw/sweep.csv`).
3. `python tools/make_lut.py data/raw/sweep.csv --levels 5` 로 투과율 기준 균등 분할 결과를 얻는다.
4. 출력된 `LUT_T`, `LUT_PWM` 을 `params.h`에 붙여넣는다.

측정 팁: 광원/센서/필름 위치를 고정하고, 구동값을 바꾼 뒤 필름이 안정될 시간을 두고, 가능하면 3회 반복해서 평균을 쓴다.
필름을 치우고 같은 위치에서 잰 기준 lux가 있으면 `--ref-lux` 로 절대 투과율을 얻는다.

## 5. 역할

| 담당 | 폴더 | 내용 |
|---|---|---|
| 강민재 | `server/ai/` | 학습 데이터 설계, 모델 학습, 모델을 C 코드로 내보내기, AI 역할 정의 |
| 김대현 | `firmware/sketches/capstone_main/` | 센서 읽기, 단계 결정 호출, 출력 제어, CSV 로깅 |
| 곽재우 | `hardware/`, `tools/`, `data/` | 드라이버(컨트롤러) 조달, 배선/안전, 부품 점검, 캘리브레이션, 데이터 수집 |
