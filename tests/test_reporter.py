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
