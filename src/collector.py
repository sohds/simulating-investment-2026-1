"""
collector.py

pykrx를 이용해 외국인·기관 순매수 및 시가총액 데이터를 수집하고
data/supply_demand/{date}.csv 로 저장합니다.

실행:
    python src/collector.py              # 오늘 기준 수집
    python src/collector.py 20250301    # 특정 날짜 기준 수집
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
import yaml
from pykrx import stock


def _inject_krx_session(jsessionid: str, extra_cookies: str = "") -> None:
    """KRX 로그인 세션 쿠키를 pykrx 요청에 주입한다.

    KRX가 2025-12-27부터 로그인을 필수화하여 pykrx 비인증 요청이 차단됨.
    브라우저에서 복사한 JSESSIONID를 여기서 주입하면 인증 우회 가능.

    Args:
        jsessionid: 브라우저 개발자 도구 Application > Cookies에서 복사한 JSESSIONID 값
        extra_cookies: __smVisitorID 등 추가 쿠키 문자열 (선택)
    """
    cookie_str = f"JSESSIONID={jsessionid}"
    if extra_cookies:
        cookie_str += f"; {extra_cookies}"

    original_post = requests.post

    def patched_post(url, *args, **kwargs):
        if "data.krx.co.kr" in url:
            headers = kwargs.get("headers", {}) or {}
            headers["Cookie"] = cookie_str
            kwargs["headers"] = headers
        return original_post(url, *args, **kwargs)

    requests.post = patched_post


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_recent_trading_dates(end_date: str, n: int) -> list:
    """
    end_date 이전 최근 n개 영업일 목록 반환.
    삼성전자(005930) OHLCV를 기준으로 실제 거래일을 추출합니다.

    Args:
        end_date: 기준일 "YYYYMMDD"
        n: 필요한 영업일 수

    Returns:
        최근 n개 영업일 리스트 (오래된 날짜 → 최근 날짜 순)
    """
    end_dt = datetime.strptime(end_date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=n * 2 + 30)  # 공휴일 여유분 포함
    start_str = start_dt.strftime("%Y%m%d")

    df = stock.get_market_ohlcv_by_date(start_str, end_date, "005930")
    dates = df.index.strftime("%Y%m%d").tolist()
    return dates[-n:]


def collect_net_purchases(
    start: str, end: str, investor: str, col_name: str, market: str = "ALL"
) -> pd.DataFrame:
    """
    기간 내 특정 투자자 유형의 누적 순매수 데이터 수집.

    Args:
        start: 시작일 "YYYYMMDD"
        end: 종료일 "YYYYMMDD"
        investor: "외국인" | "기관합계"
        col_name: 반환 DataFrame의 순매수 컬럼명
        market: "ALL" | "KOSPI" | "KOSDAQ"

    Returns:
        index=티커, columns=[종목명, col_name]
    """
    df = stock.get_market_net_purchases_of_equities_by_ticker(
        start, end, market, investor
    )
    return df[["종목명", "순매수거래대금"]].rename(columns={"순매수거래대금": col_name})


def collect_market_cap(date: str, market: str = "ALL") -> pd.DataFrame:
    """
    특정 날짜 기준 시가총액 및 일별 거래대금 수집.

    Returns:
        index=티커, columns=[시가총액, 거래대금]
    """
    df = stock.get_market_cap_by_ticker(date, market)
    return df[["시가총액", "거래대금"]]


def collect_avg_trading_value(end_date: str, days: int = 60) -> pd.Series:
    """
    end_date 기준 최근 days 영업일의 일별 거래대금 평균 산출.
    API 호출 제한 방지를 위해 호출 간 0.5초 대기하며, 실패 시 최대 3회 재시도합니다.

    Args:
        end_date: 기준일 "YYYYMMDD"
        days: 평균 산출 기간 (영업일 수)

    Returns:
        index=티커, name="평균거래대금"
    """
    trading_dates = get_recent_trading_dates(end_date, days)

    daily_volumes = []
    for i, date in enumerate(trading_dates):
        for attempt in range(3):
            try:
                df = stock.get_market_cap_by_ticker(date, "ALL")
                daily_volumes.append(df["거래대금"].rename(date))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"    [경고] {date} 거래대금 수집 실패 (3회 재시도 초과): {e}")
                else:
                    time.sleep(2 ** attempt)  # 1초, 2초 백오프
        time.sleep(0.5)
        if (i + 1) % 10 == 0:
            print(f"    거래대금 수집 중... {i + 1}/{days}일")

    if not daily_volumes:
        raise RuntimeError("거래대금 데이터를 하나도 수집하지 못했습니다.")

    combined = pd.concat(daily_volumes, axis=1).fillna(0)
    return combined.mean(axis=1).rename("평균거래대금")


def collect_all(
    end_date: Optional[str] = None,
    config_path: str = "config/config.yaml",
) -> str:
    """
    메인 수집 함수. end_date 기준 수급 데이터를 수집하여
    data/supply_demand/{end_date}.csv 에 저장합니다.

    scheduler.py에서 import해서 호출할 때도 KRX 세션이 주입되도록
    이 함수 내에서 직접 세션을 주입합니다.

    Args:
        end_date: 기준일 "YYYYMMDD". None이면 오늘.
        config_path: config.yaml 경로

    Returns:
        저장된 파일 경로
    """
    config = load_config(config_path)

    # KRX 세션 주입 (scheduler에서 import 실행 시에도 적용)
    _session = config.get("krx_session", {})
    _inject_krx_session(
        jsessionid=_session.get("jsessionid", ""),
        extra_cookies=_session.get("extra_cookies", ""),
    )

    if end_date is None:
        end_date = datetime.today().strftime("%Y%m%d")

    short_period = config["selection"]["short_period"]  # 10
    long_period = config["selection"]["long_period"]    # 20

    if short_period > long_period:
        raise ValueError(
            f"short_period({short_period}) > long_period({long_period}): "
            "config.yaml 설정을 확인하세요."
        )

    # 기간별 시작일 계산 (실제 영업일 기준)
    trading_dates = get_recent_trading_dates(end_date, long_period)
    short_start = trading_dates[-short_period]
    long_start = trading_dates[0]

    print(f"[수집 시작] 기준일: {end_date}")
    print(f"  단기({short_period}일): {short_start} ~ {end_date}")
    print(f"  장기({long_period}일): {long_start} ~ {end_date}")

    # 1. 외국인 순매수 (단기 / 장기)
    print("[1/5] 외국인 순매수 수집 중...")
    foreign_short = collect_net_purchases(short_start, end_date, "외국인", "외국인_단기_순매수")
    time.sleep(1)
    foreign_long = collect_net_purchases(long_start, end_date, "외국인", "외국인_장기_순매수")
    foreign_long = foreign_long[["외국인_장기_순매수"]]  # 종목명은 foreign_short에서 가져옴
    time.sleep(1)

    # 2. 기관 순매수 (단기 / 장기)
    print("[2/5] 기관 순매수 수집 중...")
    inst_short = collect_net_purchases(short_start, end_date, "기관합계", "기관_단기_순매수")
    inst_short = inst_short[["기관_단기_순매수"]]
    time.sleep(1)
    inst_long = collect_net_purchases(long_start, end_date, "기관합계", "기관_장기_순매수")
    inst_long = inst_long[["기관_장기_순매수"]]
    time.sleep(1)

    # 3. 시가총액 (기준일)
    print("[3/5] 시가총액 수집 중...")
    market_cap = collect_market_cap(end_date)
    time.sleep(1)

    # 4. 60일 평균 거래대금
    print("[4/5] 60일 평균 거래대금 수집 중 (약 30초 소요)...")
    avg_trading = collect_avg_trading_value(end_date, days=60)

    # 5. 병합 및 저장
    print("[5/5] 데이터 병합 중...")
    df = (
        foreign_short
        .join(foreign_long, how="outer")
        .join(inst_short, how="outer")
        .join(inst_long, how="outer")
        .join(market_cap, how="outer")
        .join(avg_trading, how="outer")
    )
    df.index.name = "티커"
    df = df.fillna(0)

    save_dir = "data/supply_demand"
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f"{end_date}.csv")
    df.to_csv(save_path, encoding="utf-8-sig")

    print(f"[완료] {save_path} 저장 완료 ({len(df)}개 종목)")
    return save_path


if __name__ == "__main__":
    # KRX 세션 주입은 collect_all() 내부에서 처리됩니다.
    # config/config.yaml의 krx_session.jsessionid 값을 최신으로 유지하세요.
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    collect_all(end_date=date_arg)
