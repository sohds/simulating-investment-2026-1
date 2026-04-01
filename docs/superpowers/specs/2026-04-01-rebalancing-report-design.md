# 설계 문서 — 리밸런싱 리포트 기능

**작성일:** 2026-04-01
**상태:** 승인됨

---

## 개요

종목선정(리밸런싱 시그널) 실행 시, 현재 포트폴리오 손익 요약과 GPT 기반 시장 흐름 분석 리포트를 자동 생성하는 기능.
최종 보고서 작성 시 참고 자료로 활용하는 것이 주목적.

---

## 요구사항

- 종목선정(`selector.py`) 실행 시 기본값으로 함께 실행 (`--no-report` 플래그로 비활성화 가능)
- `src/reporter.py`로 독립 모듈화 (직접 실행도 가능)
- 결과를 `logs/final-report/report_{YYYYMMDD}.md`로 저장
- 대시보드(`dashboard.py`)에 "리포트" 탭 추가 → 최신 파일 마크다운 렌더링
- GPT API 사용 (모델: `gpt-5.4-mini`)

---

## 아키텍처 & 데이터 흐름

```
selector.py (--no-report 없이 실행)
    │
    ├── [기존] 수급 데이터 수집 → 종목 선정 → selected DataFrame 반환
    │
    └── reporter.run(selected, signal_date, config)
            │
            ├── [데이터 수집]
            │   ├── KiwoomAPI.get_holdings()  ← 보유종목 + 매수단가 + 수익률
            │   ├── KiwoomAPI.get_deposit()   ← 예수금 (총 평가금액 계산)
            │   ├── pykrx: KOSPI/KOSDAQ 지수 (직전 그룹 시작일 ~ 오늘)
            │   ├── pykrx: 섹터별 등락
            │   └── data/supply_demand/{prev_signal_date}.csv  ← 직전 그룹 수급 (비교용)
            │
            ├── [GPT 호출]
            │   └── 수집 데이터를 구조화된 프롬프트로 전달 → 서술형 분석 반환
            │
            └── [저장]
                └── logs/final-report/report_{date}.md
```

**`selector.py` 변경 최소화:** argparse에 `--no-report` 플래그 추가 후, 마지막에 `if not args.no_report: reporter.run(...)` 호출.

---

## `reporter.py` 컴포넌트

```python
def collect_portfolio_pnl(api: KiwoomAPI) -> dict:
    """보유 종목 손익 요약.
    KiwoomAPI.get_holdings() 우선 사용, 실패 시 logs/ 파싱 fallback.
    """

def collect_market_data(start_date: str, end_date: str) -> dict:
    """pykrx로 KOSPI/KOSDAQ 지수 변화, 섹터별 등락 수집."""

def collect_supply_change(prev_date: str, curr_date: str) -> dict:
    """직전 그룹 vs 현재 그룹 수급 강도 변화 비교.
    data/supply_demand/{prev_date}.csv, {curr_date}.csv 활용.
    """

def build_prompt(portfolio: dict, market: dict,
                 supply_change: dict, selected: pd.DataFrame) -> str:
    """GPT에 전달할 구조화 프롬프트 생성."""

def call_gpt(prompt: str, config: dict) -> str:
    """OpenAI API 호출 → 서술형 분석 반환."""

def save_report(content: str, date: str) -> str:
    """logs/final-report/report_{date}.md 저장, 경로 반환."""

def run(selected: pd.DataFrame, signal_date: str,
        config_path: str = "config/config.yaml") -> None:
    """selector.py에서 호출하는 메인 진입점."""
```

---

## `config.yaml` 추가 항목

```yaml
report:
  openai_api_key: "YOUR_OPENAI_KEY"
  model: "gpt-5.4-mini"
  enabled: true
```

---

## 리포트 출력 형식

`logs/final-report/report_YYYYMMDD.md`:

```markdown
# 리밸런싱 리포트 — GN (YYYY-MM-DD)

## 1. 포트폴리오 손익 요약
| 종목명 | 매수단가 | 현재가 | 수익률 | 평가손익 |
|---|---:|---:|---:|---:|
| 삼성전자 | 72,000원 | 78,300원 | +8.75% | +126,000원 |
| ...합계 | | | +X.XX% | +X,XXX,XXX원 |

## 2. 시장 흐름 요약 (GN 기간)
- KOSPI: X,XXX → X,XXX (+X.XX%)
- KOSDAQ: XXX → XXX (+X.XX%)
- 섹터별 등락: 반도체 +X.X% / 2차전지 -X.X% / ...

## 3. 수급 강도 변화 (GN-1 → GN)
| 종목명 | 직전 수급강도 | 현재 수급강도 | 변화 |
|---|---:|---:|---:|

## 4. 신규 편입 / 편출 종목
- **편입**: ...
- **편출**: ...

## 5. GPT 분석 (GPT-5.4-mini)
[GPT가 생성한 서술형 시장 분석 및 수급 흐름 해설]
```

---

## 대시보드 변경

- `dashboard.py`에 "리포트" 탭 추가
- `logs/final-report/` 디렉토리에서 최신 `report_*.md` 파일을 읽어 마크다운 렌더링
- 리포트 생성 버튼 없음 — CLI 실행 후 저장된 파일을 표시만 함

---

## 제약 및 예외 처리

- KiwoomAPI 연결 실패 시: `logs/rebalance_history.csv` + `order_report_*.md` 파싱으로 fallback
- 직전 그룹 수급 CSV 없는 경우 (G5가 첫 투자): 수급 강도 변화 섹션 생략
- GPT API 오류 시: 분석 섹션에 오류 메시지 기록 후 나머지 섹션은 정상 저장
- `report.enabled: false`이면 reporter 호출 자체를 건너뜀

---

## 파일 변경 목록

| 파일 | 변경 내용 |
|---|---|
| `src/reporter.py` | 신규 생성 |
| `src/selector.py` | argparse `--no-report` 플래그 추가, 마지막에 `reporter.run()` 호출 |
| `src/dashboard.py` | "리포트" 탭 추가 |
| `config/config.yaml` | `report:` 섹션 추가 |
| `config/config.yaml.example` | 동일하게 `report:` 섹션 추가 |
| `requirements.txt` | `openai` 패키지 추가 |
