# 리밸런싱 리포트 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목선정 실행 시 현재 포트폴리오 손익·시장 흐름·수급 변화를 자동 분석해 `logs/final-report/report_YYYYMMDD.md`로 저장하고 대시보드에 표시한다.

**Architecture:** `reporter.py`가 KiwoomAPI·pykrx로 데이터 수집 → GPT-5.4-mini 호출 → 마크다운 저장. `selector.py`가 `--no-report` 플래그 없으면 종목선정 후 `reporter.run()` 호출. `dashboard.py`는 저장된 파일을 읽어 "리포트" 탭에 렌더링.

**Tech Stack:** `openai` (GPT-5.4-mini), `pykrx` (지수 데이터), `KiwoomAPI` (포트폴리오 손익), `dash` + `dcc.Markdown` (렌더링)

---

## 파일 변경 목록

| 파일 | 변경 내용 |
|---|---|
| `requirements.txt` | `openai` 추가 |
| `config/config.yaml` | `report:` 섹션 추가 |
| `config/config.yaml.example` | `report:` 섹션 추가 |
| `src/reporter.py` | 신규 생성 (핵심 모듈) |
| `src/selector.py` | `argparse` 추가 + `reporter.run()` 호출 |
| `src/dashboard.py` | "리포트" 탭 + 콜백 추가 |
| `tests/test_reporter.py` | 신규 생성 (순수 함수 단위 테스트) |

---

## Task 1: 환경 설정

**Files:**
- Modify: `requirements.txt`
- Modify: `config/config.yaml`
- Modify: `config/config.yaml.example`

- [ ] **Step 1: requirements.txt에 openai 추가**

`requirements.txt` 파일 끝에 한 줄 추가:
```
openai
```

- [ ] **Step 2: openai 설치 확인**

```bash
pip install openai
python -c "import openai; print(openai.__version__)"
```
Expected: 버전 번호 출력 (예: `1.x.x`)

- [ ] **Step 3: config/config.yaml에 report 섹션 추가**

파일 끝에 추가:
```yaml
report:
  openai_api_key: "YOUR_OPENAI_KEY"   # platform.openai.com에서 발급
  model: "gpt-5.4-mini"
  enabled: true
```

- [ ] **Step 4: config/config.yaml.example에 동일하게 추가**

파일 끝에 추가:
```yaml
report:
  openai_api_key: "YOUR_OPENAI_KEY"   # platform.openai.com에서 발급
  model: "gpt-5.4-mini"
  enabled: true
```

- [ ] **Step 5: 커밋**

```bash
git add requirements.txt config/config.yaml config/config.yaml.example
git commit -m "chore: openai 의존성 및 report 설정 섹션 추가"
```

---

## Task 2: reporter.py — 포트폴리오 손익 수집

**Files:**
- Create: `src/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: tests/ 디렉토리 및 빈 test 파일 생성**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_reporter.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
from reporter import collect_portfolio_pnl


def test_collect_portfolio_pnl_api_error_returns_error_dict():
    """API 연결 실패 시 error 키를 가진 dict 반환."""
    # config에 잘못된 키를 넣어 의도적으로 실패 유도
    bad_config = {
        "account": {
            "number": "0000000000",
            "appkey": "INVALID",
            "secretkey": "INVALID",
            "mock": True,
        }
    }
    result = collect_portfolio_pnl(bad_config)
    assert "error" in result
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_reporter.py::test_collect_portfolio_pnl_api_error_returns_error_dict -v
```
Expected: `ERROR` 또는 `FAILED` (reporter 모듈 없음)

- [ ] **Step 4: src/reporter.py 생성 — collect_portfolio_pnl 구현**

```python
"""
reporter.py

리밸런싱 시그널 날에 포트폴리오 손익·시장 흐름·수급 변화를
GPT-5.4-mini로 분석해 logs/final-report/report_{date}.md 로 저장.

실행:
    python src/reporter.py              # 오늘 기준 (선정 종목 CSV 필요)
    python src/reporter.py 20260401    # 특정 날짜 기준
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kiwoom_api import KiwoomAPI


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_portfolio_pnl(config: dict) -> dict:
    """보유 종목 손익 수집.

    KiwoomAPI.get_holdings() 로 매입단가·현재가·수익률 조회.
    API 실패 시 {"error": str} 반환.

    Returns:
        {
          "holdings": [{"종목명", "매입단가", "현재가", "수익률", "평가손익", "보유수량"}, ...],
          "deposit": int,
          "total_eval": int,
          "total_pnl": int,
        }
        또는 {"error": "..."}
    """
    try:
        api = KiwoomAPI.__new__(KiwoomAPI)
        api.config = config
        api.acc_no    = str(config["account"]["number"])
        api.appkey    = config["account"]["appkey"]
        api.secretkey = config["account"]["secretkey"]
        api.mock      = config["account"].get("mock", True)

        from kiwoom_api import MOCK_BASE_URL, REAL_BASE_URL
        api.base_url = MOCK_BASE_URL if api.mock else REAL_BASE_URL
        api._token = None
        api._token_expires = None

        api.connect()
        holdings = api.get_holdings()
        deposit   = api.get_deposit()

        if holdings.empty:
            return {"holdings": [], "deposit": deposit, "total_eval": deposit, "total_pnl": 0}

        rows = []
        for _, row in holdings.iterrows():
            rows.append({
                "종목명":   row["종목명"],
                "매입단가": int(row["매입단가"]),
                "현재가":   int(row["현재가"]),
                "수익률":   float(row["수익률"]),
                "평가손익": int(row["평가손익"]),
                "보유수량": int(row["보유수량"]),
            })

        total_eval = deposit + int((holdings["현재가"] * holdings["보유수량"]).sum())
        total_pnl  = int(holdings["평가손익"].sum())

        return {
            "holdings": rows,
            "deposit":  deposit,
            "total_eval": total_eval,
            "total_pnl":  total_pnl,
        }

    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_reporter.py::test_collect_portfolio_pnl_api_error_returns_error_dict -v
```
Expected: `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add src/reporter.py tests/test_reporter.py tests/__init__.py
git commit -m "feat: reporter.py 생성 및 포트폴리오 손익 수집 구현"
```

---

## Task 3: reporter.py — 시장 지수 데이터 수집

**Files:**
- Modify: `src/reporter.py`
- Modify: `tests/test_reporter.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_reporter.py` 끝에 추가:
```python
from reporter import collect_market_data


def test_collect_market_data_returns_kospi_kosdaq():
    """반환 dict에 kospi, kosdaq 키가 존재하는지 확인."""
    result = collect_market_data("20260319", "20260401")
    assert "kospi" in result
    assert "kosdaq" in result
    assert "change_pct" in result["kospi"]
    assert "change_pct" in result["kosdaq"]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_reporter.py::test_collect_market_data_returns_kospi_kosdaq -v
```
Expected: `FAILED` (함수 미정의)

- [ ] **Step 3: collect_market_data 구현 추가**

`src/reporter.py`의 `collect_portfolio_pnl` 함수 뒤에 추가:
```python
def collect_market_data(start_date: str, end_date: str) -> dict:
    """pykrx로 KOSPI/KOSDAQ 지수 변화 수집.

    Args:
        start_date: 그룹 시작일 "YYYYMMDD"
        end_date:   그룹 종료일(시그널 날) "YYYYMMDD"

    Returns:
        {
          "kospi":  {"start": float, "end": float, "change_pct": float},
          "kosdaq": {"start": float, "end": float, "change_pct": float},
          "start_date": str,
          "end_date":   str,
        }
        또는 {"error": str}
    """
    try:
        from pykrx import stock

        def _index_change(ticker: str) -> dict:
            df = stock.get_index_ohlcv_by_date(start_date, end_date, ticker)
            if df.empty:
                return {"start": 0.0, "end": 0.0, "change_pct": 0.0}
            start_val = float(df.iloc[0]["종가"])
            end_val   = float(df.iloc[-1]["종가"])
            change    = round((end_val - start_val) / start_val * 100, 2) if start_val else 0.0
            return {"start": start_val, "end": end_val, "change_pct": change}

        return {
            "kospi":      _index_change("1001"),
            "kosdaq":     _index_change("2001"),
            "start_date": start_date,
            "end_date":   end_date,
        }

    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_reporter.py::test_collect_market_data_returns_kospi_kosdaq -v
```
Expected: `PASSED` (pykrx가 실제 네트워크 호출을 하므로 인터넷 연결 필요)

- [ ] **Step 5: 커밋**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: 시장 지수 데이터 수집 구현 (pykrx KOSPI/KOSDAQ)"
```

---

## Task 4: reporter.py — 수급 강도 변화 비교

**Files:**
- Modify: `src/reporter.py`
- Modify: `tests/test_reporter.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_reporter.py` 끝에 추가:
```python
import tempfile, csv
from reporter import collect_supply_change


def test_collect_supply_change_no_prev_returns_empty():
    """직전 CSV가 없으면 빈 dict 반환."""
    result = collect_supply_change("19000101", "19000102")
    assert result == {}


def test_collect_supply_change_computes_delta():
    """두 CSV가 있으면 수급 강도 변화를 계산."""
    # 임시 CSV 두 개 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        prev_path = os.path.join(tmpdir, "20260318.csv")
        curr_path = os.path.join(tmpdir, "20260401.csv")

        for path, short, long_ in [(prev_path, 100, 200), (curr_path, 150, 250)]:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "티커", "종목명", "외국인_단기_순매수", "외국인_장기_순매수",
                    "기관_단기_순매수", "기관_장기_순매수", "시가총액", "거래대금", "평균거래대금",
                ])
                writer.writeheader()
                writer.writerow({
                    "티커": "005930", "종목명": "삼성전자",
                    "외국인_단기_순매수": short, "외국인_장기_순매수": long_,
                    "기관_단기_순매수": short, "기관_장기_순매수": long_,
                    "시가총액": 400_000_000_000, "거래대금": 0, "평균거래대금": 0,
                })

        result = collect_supply_change("20260318", "20260401", data_dir=tmpdir)
        assert "005930" in result
        assert "prev_strength" in result["005930"]
        assert "curr_strength" in result["005930"]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_reporter.py -k "supply_change" -v
```
Expected: `FAILED`

- [ ] **Step 3: collect_supply_change 구현 추가**

`src/reporter.py`의 `collect_market_data` 함수 뒤에 추가:
```python
def collect_supply_change(
    prev_date: str,
    curr_date: str,
    data_dir: str = "data/supply_demand",
    float_ratio: float = 0.5,
) -> dict:
    """직전 그룹 vs 현재 그룹 수급 강도 변화 비교.

    두 CSV 파일 모두 없으면 빈 dict 반환 (G5 첫 투자 등 엣지케이스).

    Args:
        prev_date: 직전 시그널 마감일 "YYYYMMDD"
        curr_date: 현재 시그널 마감일 "YYYYMMDD"
        data_dir:  supply_demand CSV 디렉토리 경로
        float_ratio: 유동비율 (config에서 전달)

    Returns:
        {
          ticker: {
            "종목명": str,
            "prev_strength": float,
            "curr_strength": float,
            "change_pct": float,
          }, ...
        }
    """
    prev_path = os.path.join(data_dir, f"{prev_date}.csv")
    curr_path = os.path.join(data_dir, f"{curr_date}.csv")

    if not os.path.exists(prev_path) or not os.path.exists(curr_path):
        return {}

    prev_df = pd.read_csv(prev_path, index_col="티커", encoding="utf-8-sig")
    curr_df = pd.read_csv(curr_path, index_col="티커", encoding="utf-8-sig")

    common = prev_df.index.intersection(curr_df.index)
    if common.empty:
        return {}

    result = {}
    for ticker in common:
        prev_row = prev_df.loc[ticker]
        curr_row = curr_df.loc[ticker]

        def _strength(row: pd.Series) -> float:
            net = float(row["외국인_단기_순매수"]) + float(row["기관_단기_순매수"])
            cap = float(row["시가총액"]) * float_ratio
            return round(net / cap, 6) if cap > 0 else 0.0

        prev_s = _strength(prev_row)
        curr_s = _strength(curr_row)
        change = round((curr_s - prev_s) / abs(prev_s) * 100, 2) if prev_s != 0 else 0.0

        result[ticker] = {
            "종목명":        str(curr_row.get("종목명", ticker)),
            "prev_strength": prev_s,
            "curr_strength": curr_s,
            "change_pct":    change,
        }

    return result
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_reporter.py -k "supply_change" -v
```
Expected: 2개 모두 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: 수급 강도 변화 비교 구현"
```

---

## Task 5: reporter.py — GPT 호출, 리포트 저장, run()

**Files:**
- Modify: `src/reporter.py`
- Modify: `tests/test_reporter.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_reporter.py` 끝에 추가:
```python
from reporter import save_report, build_prompt


def test_save_report_creates_file():
    """save_report가 파일을 생성하는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = save_report("# 테스트 리포트\n내용", "20260401", report_dir=tmpdir)
        assert os.path.exists(path)
        assert open(path, encoding="utf-8").read() == "# 테스트 리포트\n내용"


def test_build_prompt_contains_key_sections():
    """build_prompt 결과에 필수 섹션이 포함되는지 확인."""
    portfolio = {
        "holdings": [{"종목명": "삼성전자", "매입단가": 70000, "현재가": 78000,
                      "수익률": 11.4, "평가손익": 800000, "보유수량": 100}],
        "total_eval": 10800000,
        "total_pnl":  800000,
        "deposit":    200000,
    }
    market = {
        "kospi":  {"start": 2800.0, "end": 2923.5, "change_pct": 4.41},
        "kosdaq": {"start": 840.0,  "end": 871.3,  "change_pct": 3.73},
        "start_date": "20260319",
        "end_date":   "20260401",
    }
    supply = {
        "005930": {"종목명": "삼성전자", "prev_strength": 0.03, "curr_strength": 0.045, "change_pct": 50.0}
    }
    selected = pd.DataFrame(
        [{"종목명": "삼성전자", "선정_가중치": 2}],
        index=["005930"],
    )
    prompt = build_prompt(portfolio, market, supply, selected, group_name="G6")
    assert "삼성전자" in prompt
    assert "KOSPI" in prompt
    assert "G6" in prompt
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_reporter.py -k "save_report or build_prompt" -v
```
Expected: `FAILED`

- [ ] **Step 3: build_prompt, call_gpt, save_report, run 구현 추가**

`src/reporter.py`의 `collect_supply_change` 뒤에 추가:
```python
def build_prompt(
    portfolio: dict,
    market: dict,
    supply_change: dict,
    selected: pd.DataFrame,
    group_name: str = "",
) -> str:
    """GPT에 전달할 구조화 프롬프트 생성.

    Args:
        portfolio:    collect_portfolio_pnl() 반환값
        market:       collect_market_data() 반환값
        supply_change: collect_supply_change() 반환값
        selected:     selector.run() 반환 DataFrame
        group_name:   현재 시그널 그룹 이름 (예: "G6")

    Returns:
        GPT system+user 프롬프트 문자열
    """
    lines = []
    lines.append(f"당신은 한국 주식시장 전문 분석가입니다.")
    lines.append(f"아래 데이터를 바탕으로 {group_name} 리밸런싱 기간의 시장 흐름과 수급 변화를 분석해 주세요.")
    lines.append("")

    # ── 포트폴리오 손익 ──────────────────────────────────────────────
    lines.append("## 포트폴리오 손익")
    if "error" in portfolio:
        lines.append(f"(API 연결 실패: {portfolio['error']})")
    else:
        lines.append(f"- 총 평가금액: {portfolio['total_eval']:,}원")
        lines.append(f"- 총 평가손익: {portfolio['total_pnl']:,}원")
        lines.append(f"- 예수금: {portfolio['deposit']:,}원")
        lines.append("")
        lines.append("| 종목명 | 매입단가 | 현재가 | 수익률 | 평가손익 |")
        lines.append("|---|---:|---:|---:|---:|")
        for h in portfolio["holdings"]:
            sign = "+" if h["평가손익"] >= 0 else ""
            lines.append(
                f"| {h['종목명']} | {h['매입단가']:,}원 | {h['현재가']:,}원 "
                f"| {sign}{h['수익률']:.2f}% | {sign}{h['평가손익']:,}원 |"
            )
    lines.append("")

    # ── 시장 지수 ────────────────────────────────────────────────────
    lines.append("## 시장 지수 변화")
    if "error" in market:
        lines.append(f"(수집 실패: {market['error']})")
    else:
        kospi  = market["kospi"]
        kosdaq = market["kosdaq"]
        sign_k  = "+" if kospi["change_pct"]  >= 0 else ""
        sign_kq = "+" if kosdaq["change_pct"] >= 0 else ""
        lines.append(
            f"- KOSPI:  {kospi['start']:,.2f} → {kospi['end']:,.2f} "
            f"({sign_k}{kospi['change_pct']}%)"
        )
        lines.append(
            f"- KOSDAQ: {kosdaq['start']:,.2f} → {kosdaq['end']:,.2f} "
            f"({sign_kq}{kosdaq['change_pct']}%)"
        )
        lines.append(f"- 기간: {market['start_date']} ~ {market['end_date']}")
    lines.append("")

    # ── 수급 강도 변화 ───────────────────────────────────────────────
    lines.append("## 수급 강도 변화 (직전 그룹 → 현재 그룹)")
    if supply_change:
        lines.append("| 종목명 | 직전 수급강도 | 현재 수급강도 | 변화율 |")
        lines.append("|---|---:|---:|---:|")
        for ticker, info in supply_change.items():
            arrow = "▲" if info["change_pct"] >= 0 else "▼"
            lines.append(
                f"| {info['종목명']} | {info['prev_strength']:.5f} "
                f"| {info['curr_strength']:.5f} | {arrow} {info['change_pct']:+.1f}% |"
            )
    else:
        lines.append("(직전 그룹 데이터 없음 — 첫 시그널이거나 CSV 파일 누락)")
    lines.append("")

    # ── 신규 편입/편출 ───────────────────────────────────────────────
    lines.append("## 신규 선정 종목")
    if not selected.empty:
        lines.append("| 종목명 | 단기_수급강도 | 장기_수급강도 | 선정_가중치 |")
        lines.append("|---|---:|---:|---:|")
        for ticker, row in selected.iterrows():
            lines.append(
                f"| {row.get('종목명', ticker)} "
                f"| {row.get('단기_수급강도', 0):.5f} "
                f"| {row.get('장기_수급강도', 0):.5f} "
                f"| {int(row.get('선정_가중치', 1))} |"
            )
    lines.append("")

    # ── 분석 요청 ────────────────────────────────────────────────────
    lines.append("---")
    lines.append("위 데이터를 바탕으로 다음 항목을 한국어 서술형으로 분석해 주세요.")
    lines.append("대학원 수준의 증권분석 보고서 스타일로, 각 항목을 소제목으로 구분하세요.")
    lines.append("")
    lines.append("1. 이 기간 한국 주식시장의 핵심 흐름 및 원인 추정")
    lines.append("2. 외국인·기관 수급 흐름 해석 및 시사점")
    lines.append("3. 현재 선정 종목의 수급 강도 특징 및 선정 타당성")
    lines.append("4. 보유 포트폴리오 손익 평가")
    lines.append("5. 다음 리밸런싱 기간 전망 및 주의 사항")

    return "\n".join(lines)


def call_gpt(prompt: str, config: dict) -> str:
    """OpenAI API 호출 → 서술형 분석 반환.

    Args:
        prompt: build_prompt() 반환값
        config: config.yaml 딕셔너리

    Returns:
        GPT 응답 텍스트. 실패 시 오류 메시지 포함 문자열 반환.
    """
    try:
        from openai import OpenAI

        report_cfg = config.get("report", {})
        api_key    = report_cfg.get("openai_api_key", "")
        model      = report_cfg.get("model", "gpt-5.4-mini")

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "당신은 한국 주식시장 전문 분석가입니다. 데이터 기반으로 논리적이고 간결하게 분석합니다."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or "(빈 응답)"

    except Exception as e:
        return f"[GPT 호출 실패] {e}"


def save_report(content: str, date: str, report_dir: str = "logs/final-report") -> str:
    """리포트를 마크다운 파일로 저장.

    Args:
        content:    마크다운 본문 전체 문자열
        date:       기준일 "YYYYMMDD"
        report_dir: 저장 디렉토리 경로

    Returns:
        저장된 파일의 절대(또는 상대) 경로
    """
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"report_{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[리포트 저장] {path}")
    return path


def run(
    selected: pd.DataFrame,
    signal_date: str,
    group_name: str = "",
    config_path: str = "config/config.yaml",
) -> None:
    """selector.py에서 호출하는 메인 진입점.

    Args:
        selected:    selector.run() 반환 종목 선정 DataFrame
        signal_date: 시그널 마감일 "YYYYMMDD"
        group_name:  현재 시그널 그룹 이름 (예: "G6"). 없으면 schedule_groups로 조회.
        config_path: config.yaml 경로
    """
    config = load_config(config_path)

    if not config.get("report", {}).get("enabled", True):
        print("[리포트] 비활성화 (config.yaml report.enabled: false)")
        return

    print(f"\n{'='*56}")
    print(f"  리포트 생성  |  시그널: {signal_date}  |  그룹: {group_name or '?'}")
    print(f"{'='*56}")

    # 그룹 이름 조회 (전달 없을 시)
    if not group_name:
        try:
            from schedule_groups import RebalancingSchedule
            sched = RebalancingSchedule(
                int(config["rebalancing"]["year"]),
                groups_path=config["rebalancing"]["groups_file"],
            )
            grp = sched.find_group(signal_date)
            group_name = grp.name if grp else ""
        except Exception:
            group_name = ""

    # 직전 그룹 시그널 날 (수급 강도 변화 비교용)
    prev_signal_date = ""
    try:
        from schedule_groups import RebalancingSchedule
        sched = RebalancingSchedule(
            int(config["rebalancing"]["year"]),
            groups_path=config["rebalancing"]["groups_file"],
        )
        curr_grp = sched.find_group(signal_date)
        if curr_grp:
            idx = sched.groups.index(curr_grp)
            if idx > 0:
                prev_grp = sched.groups[idx - 1]
                prev_signal_date = prev_grp.end_str
    except Exception:
        prev_signal_date = ""

    # 직전 그룹 시작일 (시장 데이터 수집 범위)
    market_start = ""
    try:
        from schedule_groups import RebalancingSchedule
        sched = RebalancingSchedule(
            int(config["rebalancing"]["year"]),
            groups_path=config["rebalancing"]["groups_file"],
        )
        curr_grp = sched.find_group(signal_date)
        market_start = curr_grp.start_str if curr_grp else signal_date
    except Exception:
        market_start = signal_date

    print("\n[1/4] 포트폴리오 손익 수집...")
    portfolio = collect_portfolio_pnl(config)
    if "error" in portfolio:
        print(f"  [경고] API 실패: {portfolio['error']}")

    print("[2/4] 시장 지수 데이터 수집...")
    market = collect_market_data(market_start, signal_date)
    if "error" in market:
        print(f"  [경고] 지수 수집 실패: {market['error']}")

    print("[3/4] 수급 강도 변화 비교...")
    float_ratio = config["filter"].get("float_ratio", 0.5)
    supply_change = collect_supply_change(
        prev_signal_date, signal_date, float_ratio=float_ratio
    ) if prev_signal_date else {}

    print("[4/4] GPT 분석 호출...")
    prompt  = build_prompt(portfolio, market, supply_change, selected, group_name)
    gpt_txt = call_gpt(prompt, config)

    # ── 최종 마크다운 조합 ───────────────────────────────────────────
    date_fmt = f"{signal_date[:4]}-{signal_date[4:6]}-{signal_date[6:]}"
    header = f"# 리밸런싱 리포트 — {group_name} ({date_fmt})\n\n"

    sections = []
    sections.append(_fmt_pnl_section(portfolio))
    sections.append(_fmt_market_section(market))
    sections.append(_fmt_supply_section(supply_change))
    sections.append(_fmt_selected_section(selected))
    sections.append(f"## 5. GPT 분석 (GPT-5.4-mini)\n\n{gpt_txt}\n")

    content = header + "\n".join(sections)
    save_report(content, signal_date)
    print(f"\n[리포트 완료]")


# ── 섹션 포맷 헬퍼 ───────────────────────────────────────────────────

def _fmt_pnl_section(portfolio: dict) -> str:
    lines = ["## 1. 포트폴리오 손익 요약\n"]
    if "error" in portfolio:
        lines.append(f"> API 연결 실패: {portfolio['error']}\n")
        return "\n".join(lines)
    lines.append(f"- 총 평가금액: **{portfolio['total_eval']:,}원**")
    lines.append(f"- 총 평가손익: **{portfolio['total_pnl']:,}원**")
    lines.append(f"- 예수금: {portfolio['deposit']:,}원\n")
    lines.append("| 종목명 | 매입단가 | 현재가 | 수익률 | 평가손익 |")
    lines.append("|---|---:|---:|---:|---:|")
    for h in portfolio["holdings"]:
        sign = "+" if h["평가손익"] >= 0 else ""
        lines.append(
            f"| {h['종목명']} | {h['매입단가']:,}원 | {h['현재가']:,}원 "
            f"| {sign}{h['수익률']:.2f}% | {sign}{h['평가손익']:,}원 |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt_market_section(market: dict) -> str:
    lines = ["## 2. 시장 흐름 요약\n"]
    if "error" in market:
        lines.append(f"> 수집 실패: {market['error']}\n")
        return "\n".join(lines)
    kospi  = market["kospi"]
    kosdaq = market["kosdaq"]
    sign_k  = "+" if kospi["change_pct"]  >= 0 else ""
    sign_kq = "+" if kosdaq["change_pct"] >= 0 else ""
    lines.append(
        f"- **KOSPI**: {kospi['start']:,.2f} → {kospi['end']:,.2f} "
        f"(**{sign_k}{kospi['change_pct']}%**)"
    )
    lines.append(
        f"- **KOSDAQ**: {kosdaq['start']:,.2f} → {kosdaq['end']:,.2f} "
        f"(**{sign_kq}{kosdaq['change_pct']}%**)"
    )
    lines.append(f"- 기간: {market['start_date']} ~ {market['end_date']}\n")
    return "\n".join(lines)


def _fmt_supply_section(supply_change: dict) -> str:
    lines = ["## 3. 수급 강도 변화 (직전 그룹 → 현재 그룹)\n"]
    if not supply_change:
        lines.append("_직전 그룹 데이터 없음 (첫 시그널이거나 CSV 파일 누락)_\n")
        return "\n".join(lines)
    lines.append("| 종목명 | 직전 수급강도 | 현재 수급강도 | 변화율 |")
    lines.append("|---|---:|---:|---:|")
    for _, info in supply_change.items():
        arrow = "▲" if info["change_pct"] >= 0 else "▼"
        lines.append(
            f"| {info['종목명']} | {info['prev_strength']:.5f} "
            f"| {info['curr_strength']:.5f} | {arrow} {info['change_pct']:+.1f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt_selected_section(selected: pd.DataFrame) -> str:
    lines = ["## 4. 신규 선정 종목\n"]
    if selected.empty:
        lines.append("_선정 종목 없음_\n")
        return "\n".join(lines)
    lines.append("| 종목명 | 단기_수급강도 | 장기_수급강도 | 선정_가중치 |")
    lines.append("|---|---:|---:|---:|")
    for ticker, row in selected.iterrows():
        weight = int(row.get("선정_가중치", 1))
        lines.append(
            f"| {row.get('종목명', ticker)} "
            f"| {row.get('단기_수급강도', 0):.5f} "
            f"| {row.get('장기_수급강도', 0):.5f} "
            f"| {'★★' if weight == 2 else '★'} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="리밸런싱 리포트 생성")
    parser.add_argument("date", nargs="?", default=None, help="시그널 날짜 YYYYMMDD")
    args = parser.parse_args()

    signal = args.date or datetime.today().strftime("%Y%m%d")
    csv_path = f"data/supply_demand/selected_{signal}.csv"
    if os.path.exists(csv_path):
        sel = pd.read_csv(csv_path, index_col="티커", encoding="utf-8-sig")
    else:
        sel = pd.DataFrame()
        print(f"[경고] {csv_path} 없음 — 선정 종목 없이 리포트 생성")

    run(selected=sel, signal_date=signal)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_reporter.py -k "save_report or build_prompt" -v
```
Expected: 2개 모두 `PASSED`

- [ ] **Step 5: 전체 테스트 실행**

```bash
python -m pytest tests/test_reporter.py -v
```
Expected: 전체 `PASSED` (collect_market_data는 네트워크 필요)

- [ ] **Step 6: 커밋**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: GPT 호출·리포트 저장·run() 구현 완료"
```

---

## Task 6: selector.py — argparse + reporter 연동

**Files:**
- Modify: `src/selector.py:133-191`

- [ ] **Step 1: __main__ 블록을 argparse로 교체**

`src/selector.py`의 기존 `__main__` 블록:
```python
if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date=date_arg)
```
을 아래로 교체:
```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="수급 강도 기반 종목 선정")
    parser.add_argument("date", nargs="?", default=None, help="기준일 YYYYMMDD (기본: 오늘)")
    parser.add_argument("--no-report", action="store_true", help="리포트 생성 비활성화")
    args = parser.parse_args()

    selected = run(date=args.date)

    if not args.no_report and not selected.empty:
        import reporter
        signal_date = args.date or datetime.today().strftime("%Y%m%d")
        reporter.run(selected=selected, signal_date=signal_date)
```

- [ ] **Step 2: 기존 동작 확인 (--no-report 플래그)**

```bash
python src/selector.py --no-report --help
```
Expected: usage 출력, 오류 없음

- [ ] **Step 3: 하위 호환성 확인 — rebalancer.py에서 selector.run() 직접 호출 여부**

```bash
grep -n "from selector import\|import selector" src/rebalancer.py
```
Expected: `from selector import run as select_stocks` — `__main__` 블록과 무관하므로 영향 없음

- [ ] **Step 4: 커밋**

```bash
git add src/selector.py
git commit -m "feat: selector.py에 --no-report 플래그 및 reporter 연동 추가"
```

---

## Task 7: dashboard.py — 리포트 탭 추가

**Files:**
- Modify: `src/dashboard.py`

- [ ] **Step 1: 탭 4(설정) 앞에 리포트 탭 삽입**

`src/dashboard.py`의:
```python
        # ── 탭 4: 설정 ───────────────────────────────────────────────
        dbc.Tab(label="설정", tab_id="tab-settings", children=dbc.Container([
```
앞에 아래 블록 삽입:
```python
        # ── 탭 4: 리포트 ─────────────────────────────────────────────
        dbc.Tab(label="리포트", tab_id="tab-report", children=dbc.Container([
            dbc.Row([
                dbc.Col(html.Span(id="report-date-badge"), className="mt-3 mb-2"),
            ]),
            dcc.Markdown(
                id="report-content",
                style={"fontFamily": "monospace", "fontSize": "14px"},
            ),
        ], fluid=True)),

```

- [ ] **Step 2: 리포트 탭 콜백 추가**

`src/dashboard.py`의 콜백 섹션 끝 (파일 끝 또는 `if __name__ == "__main__":` 앞)에 추가:
```python
@app.callback(
    Output("report-content", "children"),
    Output("report-date-badge", "children"),
    Input("tabs", "active_tab"),
)
def update_report_tab(active_tab: str):
    if active_tab != "tab-report":
        return dash.no_update, dash.no_update

    report_dir = ROOT / "logs" / "final-report"
    if not report_dir.exists():
        return "_리포트 없음. `python src/selector.py`를 실행하세요._", ""

    files = sorted(report_dir.glob("report_*.md"), reverse=True)
    if not files:
        return "_리포트 없음. `python src/selector.py`를 실행하세요._", ""

    latest  = files[0]
    content = latest.read_text(encoding="utf-8")
    raw_date = latest.stem.replace("report_", "")
    date_fmt = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    badge = dbc.Badge(f"최신 리포트: {date_fmt}", color="info", className="fs-6")
    return content, badge
```

- [ ] **Step 3: 대시보드 실행으로 탭 확인**

```bash
python src/dashboard.py
```
Expected: `http://localhost:8050` 접속 시 "리포트" 탭 표시. 리포트 파일 없으면 안내 문구 표시.

- [ ] **Step 4: 커밋**

```bash
git add src/dashboard.py
git commit -m "feat: 대시보드에 리포트 탭 추가"
```

---

## 최종 검증

- [ ] **전체 테스트 통과 확인**

```bash
python -m pytest tests/ -v
```

- [ ] **selector.py 기본 실행 확인 (네트워크·API 없이 --no-report로)**

```bash
python src/selector.py --no-report 20260318
```
Expected: 종목 선정 결과 출력, 리포트 생성 없음

- [ ] **reporter.py 단독 실행 확인**

```bash
python src/reporter.py 20260318
```
Expected: 4단계 진행 출력 → `logs/final-report/report_20260318.md` 생성

- [ ] **최종 커밋**

```bash
git add .
git commit -m "feat: 리밸런싱 리포트 기능 구현 완료"
```
