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

    prev_df = pd.read_csv(prev_path, dtype={"티커": str}, encoding="utf-8-sig").set_index("티커")
    curr_df = pd.read_csv(curr_path, dtype={"티커": str}, encoding="utf-8-sig").set_index("티커")

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


def build_prompt(
    portfolio: dict,
    market: dict,
    supply_change: dict,
    selected: pd.DataFrame,
    group_name: str = "",
) -> str:
    """GPT에 전달할 구조화 프롬프트 생성."""
    lines = []
    lines.append(f"당신은 한국 주식시장 전문 분석가입니다.")
    lines.append(f"아래 데이터를 바탕으로 {group_name} 리밸런싱 기간의 시장 흐름과 수급 변화를 분석해 주세요.")
    lines.append("")

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
    """OpenAI API 호출 → 서술형 분석 반환. 실패 시 오류 메시지 포함 문자열 반환."""
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
    """리포트를 마크다운 파일로 저장. 저장된 파일 경로 반환."""
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
    """selector.py에서 호출하는 메인 진입점."""
    config = load_config(config_path)

    if not config.get("report", {}).get("enabled", True):
        print("[리포트] 비활성화 (config.yaml report.enabled: false)")
        return

    print(f"\n{'='*56}")
    print(f"  리포트 생성  |  시그널: {signal_date}  |  그룹: {group_name or '?'}")
    print(f"{'='*56}")

    # 그룹 이름 및 기간 정보 조회 (한 번만 import)
    prev_signal_date = ""
    market_start = signal_date
    try:
        from schedule_groups import RebalancingSchedule
        sched = RebalancingSchedule(
            int(config["rebalancing"]["year"]),
            groups_path=config["rebalancing"]["groups_file"],
        )
        if not group_name:
            grp = sched.find_group(signal_date)
            group_name = grp.name if grp else ""

        curr_grp = sched.find_group(signal_date)
        if curr_grp:
            market_start = curr_grp.start_str
            idx = sched.groups.index(curr_grp)
            if idx > 0:
                prev_signal_date = sched.groups[idx - 1].end_str
    except Exception:
        pass

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
