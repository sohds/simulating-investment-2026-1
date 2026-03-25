# src/ 모듈 설명

프로젝트 루트에서 실행하는 것을 전제로 합니다.

---

## collector.py

**pykrx를 이용한 수급 데이터 수집 모듈.**

KRX에서 외국인·기관 일별 순매수 데이터와 시가총액·거래대금을 수집해 CSV로 저장한다.
KRX 세션이 필요한 API는 `config.yaml`의 `krx_session.jsessionid` 쿠키를 주입해 인증한다.

```bash
python src/collector.py 20260401   # 특정 날짜 수집
python src/collector.py            # 오늘 날짜 기준 수집
```

- **출력**: `data/supply_demand/YYYYMMDD.csv`
- **주요 함수**: `collect_all(end_date, config_path, force)`

> 쿠키 만료 시 `config.yaml`의 `krx_session.jsessionid` 값을 갱신해야 한다.
> 대시보드의 **수집·선정 탭**에서 브라우저 없이 바로 갱신 가능.

---

## selector.py

**수급 강도 지표 산출 및 종목 선정 모듈.**

`collector.py`가 저장한 CSV를 읽어 수급 강도를 계산하고 투자 종목을 선정한다.

선정 알고리즘:
1. 외국인 순매수 상위 100 ∩ 기관 순매수 상위 100 → 교집합
2. 시가총액 ≥ 5,000억, 60일 평균 거래대금 ≥ 100억 필터
3. 수급 강도 = 누적 순매수 / (시가총액 × 유동비율 0.5)
4. 단기(10일) 상위 10 + 장기(20일) 상위 10 → 최대 16종목

```bash
python src/selector.py 20260401
```

- **출력**: `data/supply_demand/selected_YYYYMMDD.csv`
- **주요 함수**: `run(date, config_path)`

---

## schedule_groups.py

**2주 리밸런싱 그룹 기간표 관리 모듈.**

`config/rebalancing_groups.yaml`에 정의된 연간 그룹 기간표(G1~G25)를 로드하고,
오늘 날짜가 어느 그룹에 속하는지, 시그널 그룹이 무엇인지 조회한다.

```bash
python src/schedule_groups.py 2026   # 전체 기간표 출력
```

- **주요 클래스**: `RebalancingSchedule`, `Group`
- **주요 메서드**: `find_group()`, `get_signal_group()`, `get_next_group()`

---

## kiwoom_api.py

**키움 REST API 연결, 계좌 조회, 주문 실행 모듈.**

모의투자 서버(`mockapi.kiwoom.com`)에 OAuth2 토큰을 발급받아 REST API로 통신한다.
pykiwoom/PyQt5 없이 Mac에서 직접 실행 가능하다.

```bash
python src/kiwoom_api.py   # 연결 테스트 (예수금·보유 종목 출력)
```

- **주요 클래스**: `KiwoomAPI`
- **주요 메서드**: `get_deposit()`, `get_holdings()`, `get_current_price()`, `buy()`, `sell()`

> **주의**: `get_holdings()` 응답의 `stk_cd` 필드는 `A017960` 형태로 마켓 접두사가 붙어 반환된다.
> 내부에서 `lstrip("AQ")`으로 제거하므로 외부에서는 순수 숫자 코드로 사용한다.

---

## rebalancer.py

**리밸런싱 로직 모듈.**

선정 종목을 기반으로 편출(기존 종목 매도) → 조건 매도(손절·익절) → 편입(신규 종목 매수) 순서로 주문을 실행한다.
예산은 예수금 + 보유 종목 평가금액을 종목 수로 균등 분배한다.

```bash
python src/rebalancer.py 20260318   # 시그널 날짜 기준 리밸런싱 실행 (장 시간 중 실행)
```

- **출력**: `logs/rebalance_history.csv`, `logs/order_report_YYYYMMDD.md`
- **주요 함수**: `run(signal_date, group_name, config_path)`

---

## scheduler.py

**그룹 기간표 기반 자동 실행 스케줄러.**

매 영업일 09:30에 현재 날짜가 새 그룹 시작일인지 확인하고, 맞으면 수집→선정→주문 파이프라인을 자동 실행한다.

```bash
python src/scheduler.py --schedule   # 기간표 출력
python src/scheduler.py --now        # 즉시 파이프라인 실행
python src/scheduler.py              # 상시 스케줄러 시작 (09:30 자동 체크)
```

- **주요 함수**: `run_pipeline()`, `check_and_run()`, `start_scheduler()`

---

## dashboard.py

**Dash 기반 웹 대시보드.**

브라우저에서 포트폴리오 확인, 리밸런싱 실행, 수급 데이터 수집·선정, KRX 쿠키 갱신을 모두 처리할 수 있다.
영웅문 앱이나 터미널 없이 주요 작업을 한 화면에서 수행하기 위해 만들었다.

```bash
python src/dashboard.py   # 실행 후 http://localhost:8050 접속
```

### 탭 구성

| 탭 | 주요 기능 |
|---|---|
| 포트폴리오 | 보유 종목별 수익률 바 차트, 예수금·총평가금액·손익 카드 |
| 리밸런싱 | 현재 그룹·시그널 날짜 표시, 선정 종목 테이블, 주문 실행 버튼 + 실시간 로그 |
| 수집·선정 | KRX 세션 쿠키 입력 및 `config.yaml` 저장, 수집/선정/수집+선정 버튼 + 실시간 로그 |
| 설정 | 계좌 정보 및 현재 KRX 세션 상태 확인 |

### Streamlit 대신 Dash를 선택한 이유

Streamlit은 버튼 클릭 등 이벤트가 발생할 때마다 **Python 파일 전체를 재실행**한다.
상태 관리도 `session_state` 직렬화를 거치기 때문에, API 호출이 포함된 화면에서는 불필요한 재호출이 발생한다.

Dash는 **콜백 함수 단위로만 실행**되는 구조(Flask + React)라,
변경이 필요한 컴포넌트만 JSON으로 교환한다. 결과적으로 API 호출 횟수가 줄고 체감 반응 속도가 빠르다.
키움 REST API처럼 호출당 딜레이가 있는 환경에서 특히 효과적이다.
