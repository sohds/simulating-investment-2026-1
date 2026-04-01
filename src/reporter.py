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
