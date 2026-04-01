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
