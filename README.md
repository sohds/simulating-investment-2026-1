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

---

## 종목 선정 로직

```
1. 유니버스 구성
   외국인 순매수 상위 100 ∩ 기관 순매수 상위 100 → 교집합 추출 (장기 20일 기준)

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
│   ├── config.yaml              # 계좌번호, 필터 조건, 리밸런싱 주기 설정 (git 제외)
│   └── config.yaml.example     # 설정 파일 템플릿
│
├── data/
│   └── supply_demand/           # pykrx 수집 수급 데이터 저장 (YYYYMMDD.csv)
│
├── src/
│   ├── collector.py             # pykrx 수급 데이터 수집
│   ├── selector.py              # 수급 강도 지표 산출 및 종목 선정
│   ├── kiwoom_api.py            # 키움 OpenAPI 연결 및 주문 실행 (Windows 전용)
│   ├── rebalancer.py            # 리밸런싱 로직 (편입·편출 계산 및 주문)
│   └── scheduler.py             # 2주 간격 자동 실행 스케줄러
│
└── logs/
    ├── rebalance_history.csv    # 리밸런싱 이력 기록
    └── scheduler.log            # 스케줄러 실행 로그
```

---

## 환경 설정

### 요구 사항

- **Windows OS 필수** (키움 OpenAPI는 Windows 전용 ActiveX 기반)
- Python 3.9 이상
- 키움증권 계좌 및 OpenAPI+ 사용 신청
- 모의투자 서버 별도 신청 필요

> 키움 OpenAPI 신청: 키움증권 홈페이지 → 트레이딩채널 → Open API → 서비스 사용 등록
> 모의투자 신청: 키움증권 홈페이지 → 모의/실전투자 → 상시모의투자 → 신청

### 설치

```bash
pip install -r requirements.txt
```

### 설정 파일 준비

```bash
# 템플릿을 복사해 config.yaml 생성
cp config/config.yaml.example config/config.yaml
```

`config/config.yaml` 을 열어 계좌번호를 입력합니다.

```yaml
account:
  number: "1234567890"   # ← 모의투자 계좌번호로 변경
  mock: true             # 반드시 true 유지
```

> `config/config.yaml` 은 계좌번호 보호를 위해 `.gitignore`에 등록되어 있습니다.

---

## 실행 방법

> **참고**: `collector.py` · `selector.py`는 pykrx만 사용하므로 **Mac에서도 실행 가능**합니다.
> `kiwoom_api.py` · `rebalancer.py` · `scheduler.py`는 **Windows 전용**입니다.

### Step 1. 수급 데이터 수집

```bash
# 오늘 기준 수집 → data/supply_demand/YYYYMMDD.csv 저장 (약 40초 소요)
python src/collector.py

# 특정 날짜 기준 수집
python src/collector.py 20250301
```

### Step 2. 종목 선정 확인

```bash
# 오늘 기준 선정 결과 출력
python src/selector.py

# 특정 날짜 기준
python src/selector.py 20250301
```

출력 예시:
```
[선정 시작] 기준일: 20250301
  전체 종목 수: 2847
  유니버스 (외국인∩기관 상위 100): 23개
  필터 후 (시총·거래대금): 18개

[선정 결과] 14개 종목
         종목명  단기_수급강도  장기_수급강도       시가총액  선정_가중치
005930  삼성전자     0.0312     0.0289  ...              2
...
```

### Step 3. 키움 API 연결 테스트 (Windows)

```bash
python src/kiwoom_api.py
# 팝업 로그인 창에서 '모의투자 서버' 체크 후 로그인
# → 예수금 및 보유 종목 출력
```

### Step 4. 리밸런싱 수동 실행 (Windows)

```bash
# 오늘 기준 데이터로 리밸런싱 즉시 실행
python src/rebalancer.py
```

### Step 5. 자동 스케줄러 실행 (Windows)

```bash
# 스케줄러 시작 (매 영업일 09:30 자동 체크)
python src/scheduler.py

# 예정일 무관하게 즉시 전체 파이프라인 실행
python src/scheduler.py --now
```

스케줄러는 마지막 실행일로부터 2주가 경과한 영업일에 자동으로 전체 파이프라인을 실행합니다.

---

## 리밸런싱 흐름

```
[스케줄러 트리거 - 2주 1회]
        │
        ▼
[collector] pykrx 수급 데이터 수집 → data/supply_demand/YYYYMMDD.csv
        │
        ▼
[selector] 유니버스 구성 → 필터 → 수급 강도 산출 → 상위 종목 선정
        │
        ▼
[rebalancer] 보유 종목 비교 → 편출 매도 → 조건 매도 → 편입 매수
        │
        ▼
[logger] logs/rebalance_history.csv 이력 저장
```

---

## 매도 기준

| 조건 | 기준 | 처리 |
|---|---|---|
| 목표 수익률 도달 | 개별주 +15% | 보유 수량 50% 분할 매도 |
| 손절 | 매입가 대비 -8% | 즉시 전량 매도 |
| 리밸런싱 편출 | 2주 기준 수급 강도 하위 | 다음 리밸런싱 시 자동 전량 매도 |

---

## 주의 사항

- 키움 OpenAPI는 **Windows 전용**입니다. Mac / Linux 환경에서는 동작하지 않습니다.
- 모의투자 서버에서는 **지정가·시장가 주문만** 지원됩니다.
- OpenAPI 중복 로그인이 불가하므로 영웅문 등 다른 HTS와 동시 실행 시 주의가 필요합니다.
- 과도한 데이터 조회는 서버 부하로 접속이 차단될 수 있습니다 (collector에 딜레이 적용됨).

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
