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

    KRX 서버 접근 불가 시 pytest.skip으로 건너뜀 (에러는 아님).
    """
    import pytest
    result = collect_market_data("20260319", "20260401")
    if "error" in result:
        pytest.skip(f"KRX 서버 접근 불가 (정상 동작): {result['error']}")
    assert "kospi" in result
    assert "kosdaq" in result
    assert "change_pct" in result["kospi"]
    assert "change_pct" in result["kosdaq"]


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
