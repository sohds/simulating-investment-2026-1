"""
selector.py

collector.py가 저장한 수급 데이터를 읽어 수급 강도 지표를 산출하고
투자 종목을 선정합니다.

종목 선정 흐름:
    1. 유니버스 구성: 외국인 순매수 상위 100 ∩ 기관 순매수 상위 100 (장기 기준)
    2. 필터: 시가총액 ≥ 5,000억, 60일 평균 거래대금 ≥ 100억
    3. 수급 강도 산출: 누적 순매수 / 유동 시가총액
    4. 선정: 단기·장기 각 상위 top_n, 합산 최대 max_stocks 종목

실행:
    python src/selector.py              # 오늘 기준
    python src/selector.py 20250301    # 특정 날짜 기준
"""

import sys
from datetime import datetime
from typing import Optional

import pandas as pd
import yaml


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_supply_data(date: str) -> pd.DataFrame:
    """
    data/supply_demand/{date}.csv 로드.

    Returns:
        index=티커, columns=[종목명, 외국인_단기_순매수, 외국인_장기_순매수,
                              기관_단기_순매수, 기관_장기_순매수,
                              시가총액, 거래대금, 평균거래대금]
    """
    path = f"data/supply_demand/{date}.csv"
    return pd.read_csv(path, index_col="티커", encoding="utf-8-sig")


def build_universe(df: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """
    외국인 순매수 상위 top_n ∩ 기관 순매수 상위 top_n 교집합으로 유니버스 구성.
    장기(20일) 누적 순매수 기준.

    Args:
        df: 전체 종목 수급 데이터
        top_n: 각 투자자별 상위 종목 수

    Returns:
        유니버스 종목 DataFrame
    """
    foreign_top = set(df.nlargest(top_n, "외국인_장기_순매수").index)
    inst_top = set(df.nlargest(top_n, "기관_장기_순매수").index)
    universe = foreign_top & inst_top
    if not universe:
        print("  [경고] 유니버스가 비어 있습니다 (외국인∩기관 교집합 없음). 종목 선정을 중단합니다.")
        return pd.DataFrame(columns=df.columns)
    return df.loc[list(universe)]


def apply_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    시가총액·평균 거래대금 필터 적용.

    조건:
        - 시가총액 ≥ min_market_cap (기본 5,000억)
        - 60일 평균 거래대금 ≥ min_avg_volume (기본 100억)
    """
    min_cap = config["filter"]["min_market_cap"]
    min_vol = config["filter"]["min_avg_volume"]

    return df[
        (df["시가총액"] >= min_cap) &
        (df["평균거래대금"] >= min_vol)
    ].copy()


def calc_supply_strength(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    수급 강도 지표 산출.

    공식:
        수급 강도 = (외국인 + 기관) 누적 순매수 / 유동 시가총액
        유동 시가총액 = 시가총액 × 유동비율

    Returns:
        단기_수급강도, 장기_수급강도 컬럼이 추가된 DataFrame
    """
    float_ratio = config["filter"]["float_ratio"]
    float_cap = df["시가총액"] * float_ratio

    df = df.copy()
    df["단기_수급강도"] = (df["외국인_단기_순매수"] + df["기관_단기_순매수"]) / float_cap
    df["장기_수급강도"] = (df["외국인_장기_순매수"] + df["기관_장기_순매수"]) / float_cap

    return df


def select_stocks(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    단기·장기 수급 강도 상위 top_n씩 선정 후 합산, 최대 max_stocks 종목 반환.
    양쪽에 모두 선정된 종목은 선정_가중치 = 2 (중복 가중치).

    정렬 기준:
        1순위: 선정_가중치 (2 > 1)
        2순위: max(단기_수급강도, 장기_수급강도) — 어느 한쪽이 높으면 공정하게 반영

    Returns:
        선정 종목 DataFrame (가중치 내림차순, 최대수급강도 내림차순 정렬)
    """
    top_n = config["selection"]["top_n"]
    max_stocks = config["selection"]["max_stocks"]

    short_top = set(df.nlargest(top_n, "단기_수급강도").index)
    long_top = set(df.nlargest(top_n, "장기_수급강도").index)
    all_tickers = short_top | long_top

    result = df.loc[list(all_tickers)].copy()
    result["선정_가중치"] = result.index.map(
        lambda t: 2 if t in short_top and t in long_top else 1
    )
    result["최대_수급강도"] = result[["단기_수급강도", "장기_수급강도"]].max(axis=1)
    result = result.sort_values(
        ["선정_가중치", "최대_수급강도"], ascending=[False, False]
    )
    return result.head(max_stocks)


def run(
    date: Optional[str] = None,
    config_path: str = "config/config.yaml",
) -> pd.DataFrame:
    """
    메인 실행 함수. 종목 선정 결과를 출력하고 DataFrame으로 반환합니다.

    Args:
        date: 기준일 "YYYYMMDD". None이면 오늘.
        config_path: config.yaml 경로

    Returns:
        선정 종목 DataFrame
    """
    config = load_config(config_path)

    if date is None:
        date = datetime.today().strftime("%Y%m%d")

    print(f"[선정 시작] 기준일: {date}")

    df = load_supply_data(date)
    print(f"  전체 종목 수: {len(df)}")

    universe_top_n = config["selection"].get("universe_top_n", 100)
    df = build_universe(df, top_n=universe_top_n)
    print(f"  유니버스 (외국인∩기관 상위 {universe_top_n}): {len(df)}개")

    if df.empty:
        return pd.DataFrame()

    if len(df) < 5:
        print(f"  [경고] 유니버스 종목 수가 {len(df)}개로 매우 적습니다. 선정 결과를 주의하세요.")

    df = apply_filters(df, config)
    print(f"  필터 후 (시총·거래대금): {len(df)}개")

    if df.empty:
        print("  [경고] 필터 후 종목이 0개입니다. 조건을 완화하거나 데이터를 확인하세요.")
        return pd.DataFrame()

    df = calc_supply_strength(df, config)
    selected = select_stocks(df, config)

    display_cols = ["종목명", "단기_수급강도", "장기_수급강도", "최대_수급강도", "시가총액", "선정_가중치"]
    print(f"\n[선정 결과] {len(selected)}개 종목")
    print(selected[display_cols].to_string())

    save_path = f"data/supply_demand/selected_{date}.csv"
    selected[display_cols].to_csv(save_path, encoding="utf-8-sig")
    print(f"[저장] {save_path}")

    return selected


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date=date_arg)
