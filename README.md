# Kiwoom Auto Rebalancer

키움 **REST API** 기반 **외국인·기관 순매수 수급 강도 지표** 활용 2주 자동 리밸런싱 모의투자 시스템

---

## 과목 정보

**2026-1학기 증권시장의이해와실제** 중간·기말 과제인 모의투자 중 **자유 투자 방식**을 다음과 같이 진행하였습니다.

- 투자 전략: 외국인·기관 순매수 수급 강도 지표 기반 종목 선정 + 2주 단위 자동 리밸런싱
- 모의투자 기간: **2026.03.04 ~ 2026.06.16** (수업 시작일 ~ 종강 전일)
- 투자 도구: 키움증권 REST API **상시모의투자** 서버 (`https://mockapi.kiwoom.com`)
- 운용 방식: 상시모의투자 계좌(1천만원)로 자동 주문 실행 → `logs/order_report_YYYYMMDD.md` 생성 → 대학그룹모의투자 계좌에 수동 미러링
- 리밸런싱 방식: 사전 정의된 그룹 기간표에 따라 GN 기간 종목 선정 → GN+1 기간 투자 실행

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
   GN 기간에 선정된 종목을 GN+1 기간에 매수 실행
```

---

## 2주 리밸런싱 그룹 기간표

연간 스케줄을 2주 단위 그룹으로 분할하고, 공휴일·연휴를 고려해 그룹 경계를 조정합니다.

> **GN 기간에 선정된 종목은 GN+1 기간에 투자를 실행합니다.**

아래 표에서 **굵은 글씨**가 수업 기간 중 활성 그룹입니다.

| 그룹 | 기간 (시작일 ~ 종료일) | 비고 | 역할 |
|---|---|---|---|
| G1 | 01/02(금) ~ 01/15(목) | 1/1(신정) | |
| G2 | 01/16(금) ~ 01/29(목) | | |
| G3 | 01/30(금) ~ 02/13(금) | 2/16~18(설 연휴) | |
| **G4** | **02/19(목) ~ 03/04(수)** | **3/2(삼일절 대체공휴일)** | **첫 시그널** |
| **G5** | **03/05(목) ~ 03/18(수)** | | **투자 (1차)** |
| **G6** | **03/19(목) ~ 04/01(수)** | | **투자** |
| **G7** | **04/02(목) ~ 04/15(수)** | | **투자** |
| **G8** | **04/16(목) ~ 04/30(목)** | **5/1(근로자의 날)** | **투자** |
| **G9** | **05/04(월) ~ 05/15(금)** | **5/5(어린이날)** | **투자** |
| **G10** | **05/18(월) ~ 05/29(금)** | **5/25(석가탄신일 대체공휴일)** | **투자** |
| **G11** | **06/01(월) ~ 06/12(금)** | | **투자** |
| **G12** | **06/15(월) ~ 06/26(금)** | | **마지막 투자 (06/16 전량 매도)** |
| G13 | 06/29(월) ~ 07/10(금) | | |
| G14 | 07/13(월) ~ 07/24(금) | | |
| G15 | 07/27(월) ~ 08/07(금) | | |
| G16 | 08/10(월) ~ 08/25(화) | 8/15(광복절), 8/17(대체공휴일) | |
| G17 | 08/26(수) ~ 09/08(화) | | |
| G18 | 09/09(수) ~ 09/22(화) | | |
| G19 | 09/23(수) ~ 10/08(목) | 10/3(개천절), 10/5~6(추석 연휴/대체공휴일) | |
| G20 | 10/12(월) ~ 10/23(금) | 10/9(한글날) | |
| G21 | 10/26(월) ~ 11/06(금) | | |
| G22 | 11/09(월) ~ 11/20(금) | | |
| G23 | 11/23(월) ~ 12/04(금) | | |
| G24 | 12/07(월) ~ 12/22(화) | 12/25(성탄절) | |
| G25 | 12/23(수) ~ 01/07(목) | 12/25(성탄절), 1/1(신정) | |

- G4 시그널로 선정된 종목을 G5에서 첫 매수 (총 8회 리밸런싱)
- G12 기간 중 **06/16에 전량 매도**하여 모의투자 종료

그룹 기간표는 `config/rebalancing_groups.yaml`에서 정의됩니다.

---

## 디렉토리 구조

```
simul-stock/
│
├── README.md
├── requirements.txt
│
├── config/
│   ├── config.yaml                 # 계좌번호, 필터 조건, 연도 설정
│   ├── config.yaml.example         # 설정 파일 템플릿
│   └── rebalancing_groups.yaml     # 2주 리밸런싱 그룹 기간표
│
├── data/
│   └── supply_demand/              # pykrx 수집 수급 데이터 저장 (YYYYMMDD.csv)
│
├── src/
│   ├── collector.py                # pykrx 수급 데이터 수집
│   ├── selector.py                 # 수급 강도 지표 산출 및 종목 선정
│   ├── schedule_groups.py          # 리밸런싱 그룹 기간표 관리
│   ├── kiwoom_api.py               # 키움 REST API 연결 및 주문 실행
│   ├── rebalancer.py               # 리밸런싱 로직 (편입·편출 계산 및 주문)
│   └── scheduler.py                # 그룹 기간표 기반 자동 실행 스케줄러
│
├── data/
│   ├── supply_demand/              # pykrx 수집 수급 데이터 저장 (YYYYMMDD.csv)
│   └── kiwoom_keys/                # API 앱키·시크릿키 파일 (.gitignore 제외)
│
└── logs/
    ├── rebalance_history.csv       # 리밸런싱 이력 기록
    ├── order_report_YYYYMMDD.md    # 리밸런싱 주문서 (대학그룹모의투자 미러링용)
    ├── last_rebalancing_group.txt  # 마지막 실행 그룹 추적
    └── scheduler.log               # 스케줄러 실행 로그
```

---

## 환경 설정

### 요구 사항

- **Mac / Linux / Windows 모두 실행 가능** (REST API 기반, ActiveX 불필요)
- Python 3.9 이상
- 키움증권 계좌 및 REST API 사용 신청
  - 신청: [https://openapi.kiwoom.com](https://openapi.kiwoom.com) → 앱키 발급
- 모의투자 서버 별도 신청 필요
  - 신청: 키움증권 홈페이지 → 모의/실전투자 → 상시모의투자 → 신청

### 설치

```bash
pip install -r requirements.txt
```

### 설정 파일 준비

`config/config.yaml`을 열어 계좌번호·앱키·시크릿키를 입력합니다.

```yaml
account:
  number: "1234567890"              # ← 모의투자 계좌번호로 변경
  mock: true                        # 반드시 true 유지
  appkey: "YOUR_APP_KEY_HERE"       # ← openapi.kiwoom.com에서 발급한 앱키
  secretkey: "YOUR_SECRET_KEY_HERE" # ← 시크릿키

rebalancing:
  groups_file: "config/rebalancing_groups.yaml"
  year: 2026             # 사용할 그룹 기간표 연도
```

> `config/config.yaml` 은 계좌번호·API 키 보호를 위해 `.gitignore`에 등록되어 있습니다.

---

## 실행 방법

> **모든 모듈이 Mac / Linux / Windows에서 실행 가능합니다.**
> 단, `kiwoom_api.py` 관련 기능은 `config.yaml`에 REST API 앱키 입력 후 사용 가능합니다.

### 그룹 기간표 확인

```bash
python src/schedule_groups.py
python src/scheduler.py --schedule
```

### Step 1. 수급 데이터 수집

```bash
# 오늘 기준 수집 → data/supply_demand/YYYYMMDD.csv 저장 (약 40초 소요)
python src/collector.py

# 시그널 그룹 마감일 기준 수집 (예: G5 마감일)
python src/collector.py 20260318
```

### Step 2. 종목 선정 확인

```bash
python src/selector.py
python src/selector.py 20260318
```

### Step 3. REST API 연결 테스트

```bash
# config.yaml에 appkey / secretkey 입력 후 실행
python src/kiwoom_api.py
# → 토큰 발급 후 예수금·보유 종목 출력
```

### Step 4. 리밸런싱 수동 실행

```bash
python src/rebalancer.py 20260318
```

### Step 5. 자동 스케줄러 실행

```bash
# 스케줄러 시작 (매 영업일 09:30 자동 체크)
python src/scheduler.py

# 현재 그룹 즉시 실행
python src/scheduler.py --now
```

---

## 리밸런싱 흐름

```
[스케줄러 — 새 그룹(GN+1) 감지]
        │
        ▼
[시그널 그룹(GN) 확인] → 시그널 마감일 = GN의 종료일
        │
        ▼
[collector] pykrx 수급 데이터 수집 → data/supply_demand/{시그널마감일}.csv
        │
        ▼
[selector] 유니버스 구성 → 필터 → 수급 강도 산출 → 상위 종목 선정
        │
        ▼
[rebalancer] 보유 종목 비교 → 편출 매도 → 조건 매도 → 편입 매수
        │
        ▼
[logger] logs/rebalance_history.csv 이력 저장 + logs/order_report_YYYYMMDD.md 주문서 생성
        │
        ▼
[수동] 주문서를 참고해 대학그룹모의투자 계좌에 동일 주문 입력
```

---

## 매도 기준

| 조건 | 기준 | 처리 |
|---|---|---|
| 목표 수익률 도달 | 개별주 +15% | 보유 수량 50% 분할 매도 |
| 손절 | 매입가 대비 -8% | 즉시 전량 매도 |
| 리밸런싱 편출 | 다음 그룹 시그널에서 미선정 | 그룹 전환 시 자동 전량 매도 |

---

## 주의 사항

- REST API는 **상시모의투자 전용 앱키**가 필요합니다. 실전투자 앱키로는 `mockapi.kiwoom.com` 접속이 차단됩니다.
  - 상시모의투자 신청: 키움증권 홈페이지 → 모의/실전투자 → 상시모의투자 → 신청
  - 앱키 발급: [https://openapi.kiwoom.com](https://openapi.kiwoom.com) → **모의투자** 선택 후 발급
- 앱키 발급 시 **IP 화이트리스트** 등록이 필요합니다 (호출 IP를 포털에서 등록).
- 토큰 유효기간은 **24시간**입니다. 코드에서 자동 재발급되지만 장애 시 수동 확인 필요.
- 모의투자 서버에서는 **시장가 주문만** 사용합니다.
- 과도한 API 호출은 서버 부하로 차단될 수 있습니다 (collector에 딜레이 적용됨).
- **kiwoom_api.py의 API 엔드포인트 경로는 앱키 발급 후 공식 문서에서 확인·수정 필요합니다.**
  - 참고: [https://openapi.kiwoom.com/guide/apiguide](https://openapi.kiwoom.com/guide/apiguide)
- 2026년 그룹 기간표의 공휴일은 추정치입니다. 실제 시장 휴장일 확정 시 `config/rebalancing_groups.yaml`을 검증하세요.

---

## 기술 스택

| 분류 | 라이브러리 | 버전 |
|---|---|---|
| 수급 데이터 수집 | `pykrx` | 1.2.4 |
| 수급 데이터 수집 | `finance-datareader` | 0.9.110 |
| REST API 연동 | `requests` | 2.x |
| 데이터 처리 | `pandas` | 2.3.3 |
| 데이터 처리 | `numpy` | 1.26.4 |
| 스케줄링 | `schedule` | 1.2.2 |
| 설정 관리 | `pyyaml` | 6.0.3 |

### Python 버전

Python 3.9 이상 (Mac / Linux / Windows 모두 동일 환경 사용 가능)

---

## 참고

- [Ko-ActiveETF (그룹 기간표 참조)](https://github.com/sohds/Ko-ActiveETF)
- [키움 REST API 공식 포털](https://openapi.kiwoom.com)
- [키움 REST API 가이드](https://openapi.kiwoom.com/guide/apiguide)
- [pykrx 문서](https://github.com/sharebook-kr/pykrx)
