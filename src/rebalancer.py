"""
rebalancer.py

현재 보유 종목과 신규 선정 종목을 비교해
편출(매도) / 편입(매수) 주문을 실행하는 리밸런싱 모듈.

매도 우선순위:
    1. 편출 종목 (선정 리스트에서 제외된 종목) — 전량 매도
    2. 손절 조건 (-8%) — 즉시 전량 매도
    3. 목표수익 조건 (+15%) — 보유 수량 50% 분할 매도

편입 매수:
    - 매도 후 남은 예수금 기준 균등 비중 배분
    - 이미 보유 중인 선정 종목은 스킵 (리밸런싱 주기 내 재매수 없음)

⚠️  Windows 전용 (kiwoom_api 의존)
"""

import csv
import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd
import yaml

# src/ 디렉토리를 모듈 검색 경로에 추가 (단독 실행 시)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kiwoom_api import KiwoomAPI
from selector import run as select_stocks


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calc_target_qty(price: int, budget_per_stock: int) -> int:
    """균등 비중 기준 매수 수량 계산.

    Args:
        price: 현재가 (원)
        budget_per_stock: 종목당 배분 금액 (원)

    Returns:
        매수 가능 수량 (금액 부족 시 0)
    """
    if price <= 0:
        return 0
    return budget_per_stock // price


def check_exit_conditions(holdings: pd.DataFrame, config: dict) -> list:
    """개별 종목 손절 / 목표수익 조건 체크.

    Args:
        holdings: get_holdings() 반환값
        config: config.yaml 딕셔너리

    Returns:
        [(종목코드, 종목명, 매도수량, 사유), ...] 형태의 리스트
    """
    stop_loss    = config["sell_rules"]["stop_loss_ratio"]       # -0.08
    take_profit  = config["sell_rules"]["take_profit_ratio"]     # 0.15
    partial_ratio = config["sell_rules"]["sell_partial_ratio"]   # 0.5

    orders = []
    for _, row in holdings.iterrows():
        rate = row["수익률"] / 100  # pykiwoom은 % 단위로 반환

        if rate <= stop_loss:
            orders.append((
                row["종목코드"], row["종목명"],
                int(row["보유수량"]), "손절(-8%)"
            ))
        elif rate >= take_profit:
            partial_qty = max(1, int(row["보유수량"] * partial_ratio))
            orders.append((
                row["종목코드"], row["종목명"],
                partial_qty, "목표수익(+15%) 분할매도"
            ))

    return orders


def execute_rebalance(
    api: KiwoomAPI,
    selected: pd.DataFrame,
    config: dict,
) -> dict:
    """리밸런싱 주문 실행 (편출 → 조건 매도 → 편입).

    Args:
        api: KiwoomAPI 인스턴스 (로그인 완료 상태)
        selected: selector.run()이 반환한 선정 종목 DataFrame (index=티커)
        config: config.yaml 딕셔너리

    Returns:
        실행 결과 요약 딕셔너리
    """
    holdings = api.get_holdings()
    holding_codes = set(holdings["종목코드"].tolist()) if not holdings.empty else set()
    selected_codes = set(selected.index.tolist())

    exit_log       = []
    condition_log  = []
    entry_log      = []

    # ── Step 1. 편출 종목 전량 매도 ──────────────────────────────────
    exit_codes = holding_codes - selected_codes
    print(f"\n[편출 매도] {len(exit_codes)}개 종목")

    for code in exit_codes:
        row = holdings[holdings["종목코드"] == code].iloc[0]
        qty = int(row["보유수량"])
        order_no = api.sell(code, qty)
        status = "성공" if order_no else "실패"
        print(f"  {row['종목명']}({code}) {qty}주 [{status}]")
        exit_log.append({
            "종목코드": code, "종목명": row["종목명"],
            "수량": qty, "구분": "편출매도", "주문번호": order_no,
        })

    # ── Step 2. 손절 / 목표수익 조건 체크 ────────────────────────────
    condition_orders = check_exit_conditions(holdings, config)
    condition_orders = [(c, n, q, r) for c, n, q, r in condition_orders
                        if c not in exit_codes]  # 편출과 중복 제거
    print(f"\n[조건 매도] {len(condition_orders)}건")

    for code, name, qty, reason in condition_orders:
        order_no = api.sell(code, qty)
        status = "성공" if order_no else "실패"
        print(f"  {name}({code}) {qty}주 — {reason} [{status}]")
        condition_log.append({
            "종목코드": code, "종목명": name,
            "수량": qty, "구분": reason, "주문번호": order_no,
        })

    # ── Step 3. 편입 매수 ────────────────────────────────────────────
    entry_codes = selected_codes - holding_codes  # 미보유 종목만 매수
    print(f"\n[편입 매수] {len(entry_codes)}개 종목")

    deposit = api.get_deposit()  # 매도 체결 후 예수금 재조회
    holdings_value = 0
    if not holdings.empty:
        # 편출 종목 제외한 보유금액 합산
        remaining = holdings[~holdings["종목코드"].isin(exit_codes)]
        holdings_value = int((remaining["현재가"] * remaining["보유수량"]).sum())

    total_value = deposit + holdings_value
    n_target = len(selected_codes)
    budget_per_stock = total_value // n_target if n_target else 0

    for code in entry_codes:
        price = api.get_current_price(code)
        qty = calc_target_qty(price, budget_per_stock)

        if qty <= 0:
            name = selected.loc[code, "종목명"] if "종목명" in selected.columns else code
            print(f"  {name}({code}) — 스킵 (현재가 {price:,}원, 예산 {budget_per_stock:,}원 부족)")
            continue

        order_no = api.buy(code, qty)
        name = selected.loc[code, "종목명"] if "종목명" in selected.columns else code
        status = "성공" if order_no else "실패"
        print(f"  {name}({code}) {qty}주 @ {price:,}원 [{status}]")
        entry_log.append({
            "종목코드": code, "종목명": name,
            "수량": qty, "구분": "편입매수", "주문번호": order_no,
        })

    return {
        "편출":    exit_log,
        "조건매도": condition_log,
        "편입":    entry_log,
        "총투자금액": total_value,
    }


def save_log(result: dict, date: str) -> None:
    """리밸런싱 이력을 logs/rebalance_history.csv에 추가."""
    log_path = "logs/rebalance_history.csv"
    os.makedirs("logs", exist_ok=True)

    rows = []
    for key in ["편출", "조건매도", "편입"]:
        for item in result.get(key, []):
            rows.append({
                "날짜":    date,
                "종목코드": item["종목코드"],
                "종목명":  item["종목명"],
                "수량":    item["수량"],
                "구분":    item["구분"],
                "주문번호": item["주문번호"],
            })

    if not rows:
        print("[이력] 실행된 주문 없음")
        return

    file_exists = os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["날짜", "종목코드", "종목명", "수량", "구분", "주문번호"]
        )
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"[이력 저장] {log_path} ({len(rows)}건 추가)")


def run(
    date: Optional[str] = None,
    config_path: str = "config/config.yaml",
) -> None:
    """메인 리밸런싱 실행 함수 (Windows 전용).

    Steps:
        1. 종목 선정 (selector.run)
        2. 키움 API 로그인
        3. 편출 → 조건매도 → 편입 주문 실행
        4. 이력 CSV 저장

    Args:
        date: 기준일 "YYYYMMDD". None이면 오늘.
        config_path: config.yaml 경로
    """
    from PyQt5.QtWidgets import QApplication

    config = load_config(config_path)

    if date is None:
        date = datetime.today().strftime("%Y%m%d")

    print(f"\n{'='*52}")
    print(f"  리밸런싱 실행: {date}")
    print(f"{'='*52}")

    # Step 1. 종목 선정
    print("\n[Step 1] 종목 선정")
    selected = select_stocks(date=date, config_path=config_path)

    if selected.empty:
        print("[중단] 선정된 종목이 없습니다.")
        return

    # Step 2. 키움 API 연결
    print("\n[Step 2] 키움 API 연결")
    app = QApplication(sys.argv)
    api = KiwoomAPI(config_path=config_path)
    api.connect()

    # Step 3. 주문 실행
    print("\n[Step 3] 주문 실행")
    result = execute_rebalance(api, selected, config)

    # Step 4. 이력 저장
    print("\n[Step 4] 이력 저장")
    save_log(result, date)

    n_exit  = len(result["편출"])
    n_cond  = len(result["조건매도"])
    n_entry = len(result["편입"])
    print(f"\n[완료] 편출 {n_exit}건 / 조건매도 {n_cond}건 / 편입 {n_entry}건")


if __name__ == "__main__":
    run()
