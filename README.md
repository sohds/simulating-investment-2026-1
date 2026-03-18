# 📈 Kiwoom Auto Rebalancer

키움 OpenAPI 기반 **외국인·기관 순매수 수급 강도 지표** 활용 2주 자동 리밸런싱 모의투자 시스템

---

## 프로젝트 개요

한국 주식시장에서 외국인·기관의 순매수 패턴이 단기 주가 흐름의 선행지표가 될 수 있다는 가설을 바탕으로, 수급 강도 지표 상위 종목을 자동 선정하고 키움 OpenAPI 모의투자 서버에 2주 간격으로 매수·매도 주문을 자동 실행하는 시스템입니다.

---

## 핵심 기능

- **수급 데이터 수집**: `pykrx`로 외국인·기관 일별 순매수 데이터 자동 수집
- **종목 선정 로직**: 수급 강도 지표 기반 상위 종목 필터링 및 선정
- **자동 리밸런싱**: 키움 OpenAPI 연동, 2주 간격 편입·편출 주문 자동 실행
- **모의투자 연동**: 키움 모의투자 서버 전용 연결 (실계좌 영향 없음)
- **텔레그램 알림** *(선택)*: 리밸런싱 실행 결과 실시간 알림

---

## 종목 선정 로직

```
1. 유니버스 구성
   외국인 순매수 상위 100 ∩ 기관 순매수 상위 100 → 교집합 추출

2. 필터링
   시가총액 ≥ 5,000억 원
   60일 평균 거래대금 ≥ 100억 원

3. 수급 강도 지표 산출
   수급 강도 = 누적 순매수 금액 / 유동 시가총액 (유동비율 0.5)

4. 종목 선정
   단기(10일) 수급 강도 상위 10종목
   장기(20일) 수급 강도 상위 10종목
   → 합산 최대 16종목 (중복 시 가중치 2배)

5. 투자 실행
   선정 기간의 다음 2주 기간에 매수 실행
```

---

## 디렉토리 구조

```
kiwoom-auto-rebalancer/
│
├── README.md
├── requirements.txt
│
├── config/
│   └── config.yaml              # 계좌번호, 필터 조건, 리밸런싱 주기 설정
│
├── data/
│   └── supply_demand/           # pykrx 수집 수급 데이터 저장
│
├── src/
│   ├── collector.py             # pykrx 수급 데이터 수집
│   ├── selector.py              # 수급 강도 지표 산출 및 종목 선정
│   ├── kiwoom_api.py            # 키움 OpenAPI 연결 및 주문 실행
│   ├── rebalancer.py            # 리밸런싱 로직 (편입·편출 계산)
│   └── scheduler.py             # 2주 간격 자동 실행 스케줄러
│
└── logs/
    └── rebalance_history.csv    # 리밸런싱 이력 기록
```

---

## 환경 설정

### 요구 사항

- **Windows OS 필수** (키움 OpenAPI는 Windows 전용)
- Python 3.9 이상
- 키움증권 계좌 및 OpenAPI+ 사용 신청
- 모의투자 서버 별도 신청 필요

> 키움 OpenAPI 신청: 키움증권 홈페이지 → 트레이딩채널 → Open API → 서비스 사용 등록  
> 모의투자 신청: 키움증권 홈페이지 → 모의/실전투자 → 상시모의투자 → 신청

### 설치

```bash
pip install -r requirements.txt
```

### requirements.txt

```
pykrx
pykiwoom
PyQt5
pandas
numpy
pyyaml
schedule
FinanceDataReader
```

### config/config.yaml 설정

```yaml
account:
  number: "모의투자 계좌번호"   # 모의투자 전용 계좌번호 입력
  mock: true                    # true = 모의투자 서버 접속

filter:
  min_market_cap: 500000000000  # 시가총액 5,000억 원 이상
  min_avg_volume: 10000000000   # 60일 평균 거래대금 100억 원 이상
  float_ratio: 0.5              # 유동비율

selection:
  short_period: 10              # 단기 수급 강도 기간 (일)
  long_period: 20               # 장기 수급 강도 기간 (일)
  top_n: 10                     # 각 기간별 상위 종목 수
  max_stocks: 16                # 최대 편입 종목 수

rebalancing:
  interval_weeks: 2             # 리밸런싱 주기 (2주)
  order_type: "시장가"           # 주문 유형 (모의투자: 지정가/시장가만 가능)
```

---

## 사용법

### 1. 수급 데이터 수집 및 종목 선정 (수동 확인)

```bash
python src/collector.py        # 오늘 기준 수급 데이터 수집
python src/selector.py         # 수급 강도 지표 산출 및 종목 선정 결과 출력
```

### 2. 키움 OpenAPI 로그인 및 연결 테스트

```bash
python src/kiwoom_api.py
# 실행 후 팝업 로그인 창에서 모의투자 접속 체크 후 로그인
```

### 3. 자동 리밸런싱 실행

```bash
python src/scheduler.py
# 2주 간격으로 종목 선정 → 편출 매도 → 편입 매수 자동 실행
```

---

## 리밸런싱 흐름

```
[스케줄러 트리거 - 2주 1회]
        │
        ▼
[pykrx] 수급 데이터 수집
        │
        ▼
[selector] 수급 강도 지표 산출 → 상위 종목 선정
        │
        ▼
[rebalancer] 현재 보유 종목과 비교 → 편출/편입 목록 계산
        │
        ▼
[kiwoom_api] 편출 종목 매도 주문 → 편입 종목 매수 주문
        │
        ▼
[logger] 리밸런싱 이력 CSV 저장
```

---

## 매도 기준

자동 리밸런싱 외에도 아래 규칙 기반 매도 조건을 적용합니다.

| 조건 | 기준 | 처리 |
|---|---|---|
| 목표 수익률 도달 | 개별주 +15% | 보유 수량 50% 분할 매도 |
| 손절 | 매입가 대비 -8% | 즉시 전량 매도 |
| 수급 악화 | 순매도 전환 2주 연속 | 보유 여부 재검토 후 매도 |
| 리밸런싱 편출 | 2주 기준 수급 강도 하위 | 다음 리밸런싱 시 자동 매도 |

---

## 주의 사항

- 키움 OpenAPI는 **Windows 전용**입니다. Mac / Linux 환경에서는 동작하지 않습니다.
- 모의투자 서버에서는 **지정가·시장가 주문만** 지원됩니다.
- OpenAPI 중복 로그인이 불가하므로 영웅문 등 다른 프로그램과 동시 실행 시 주의가 필요합니다.
- 과도한 데이터 조회는 서버 부하로 접속이 차단될 수 있습니다.

---

## 기술 스택

| 분류 | 라이브러리 |
|---|---|
| 수급 데이터 수집 | `pykrx`, `FinanceDataReader` |
| OpenAPI 연동 | `pykiwoom`, `PyQt5` |
| 데이터 처리 | `pandas`, `numpy` |
| 스케줄링 | `schedule` |
| 설정 관리 | `pyyaml` |

---

## 참고

- [키움 OpenAPI+ 공식 다운로드](https://www.kiwoom.com/h/customer/download/VOpenApiInfoView)
- [pykiwoom 문서](https://wikidocs.net/book/1173)
- [pykrx 문서](https://github.com/sharebook-kr/pykrx)
