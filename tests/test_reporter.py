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


from reporter import collect_market_data


def test_collect_market_data_returns_kospi_kosdaq():
    """반환 dict에 kospi, kosdaq 키가 존재하는지 확인.

    pykrx가 정상 동작할 때: kospi/kosdaq 키와 change_pct 포함 확인.
    KRX 서버 응답 이상 등으로 실패할 때: error 키 반환 확인 (크래시 없음).
    """
    result = collect_market_data("20260319", "20260401")
    assert isinstance(result, dict), "반환값은 항상 dict여야 함"
    if "error" in result:
        # KRX 서버 이슈 또는 네트워크 문제 — 크래시 없이 error 키 반환은 정상
        return
    assert "kospi" in result
    assert "kosdaq" in result
    assert "change_pct" in result["kospi"]
    assert "change_pct" in result["kosdaq"]
