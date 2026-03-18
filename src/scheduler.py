"""
scheduler.py

2주 간격 자동 리밸런싱 스케줄러.

동작 방식:
    - 매 영업일(월~금) 오전 09:30에 리밸런싱 예정일 여부를 확인합니다.
    - 마지막 실행일로부터 2주(설정 가능)가 경과하면 전체 파이프라인을 실행합니다.
    - 마지막 실행일은 logs/last_rebalancing_date.txt 에 저장됩니다.

전체 파이프라인:
    [수급 데이터 수집] → [종목 선정] → [리밸런싱 주문] → [이력 저장]

실행:
    python src/scheduler.py          # 스케줄러 시작 (종료: Ctrl+C)
    python src/scheduler.py --now    # 예정일 무관하게 즉시 실행

⚠️  리밸런싱 주문 실행은 Windows 전용 (rebalancer → kiwoom_api 의존)
    수급 데이터 수집·종목 선정만 테스트하려면 collector.py / selector.py 를 직접 실행하세요.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import schedule
import yaml

# ── 로거 설정 ────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── 상수 ─────────────────────────────────────────────────────────────
LAST_RUN_FILE = "logs/last_rebalancing_date.txt"
SRC_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 유틸리티 ─────────────────────────────────────────────────────────

def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_last_run_date() -> Optional[str]:
    """마지막 리밸런싱 실행 날짜 읽기 ("YYYYMMDD")."""
    if not os.path.isfile(LAST_RUN_FILE):
        return None
    with open(LAST_RUN_FILE, "r") as f:
        return f.read().strip() or None


def save_last_run_date(date: str) -> None:
    """마지막 리밸런싱 실행 날짜 저장."""
    with open(LAST_RUN_FILE, "w") as f:
        f.write(date)


def is_rebalancing_due(interval_weeks: int = 2) -> bool:
    """오늘이 리밸런싱 예정일인지 확인.

    마지막 실행일로부터 interval_weeks 주 이상 경과하면 True.
    실행 이력이 없으면 즉시 실행(True) 반환.
    """
    last_date = get_last_run_date()

    if last_date is None:
        logger.info("첫 실행 — 리밸런싱을 즉시 시작합니다.")
        return True

    last_dt = datetime.strptime(last_date, "%Y%m%d")
    next_dt = last_dt + timedelta(weeks=interval_weeks)
    today   = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    if today >= next_dt:
        logger.info(f"리밸런싱 예정일 도달 (마지막: {last_date} → 다음: {next_dt.strftime('%Y%m%d')})")
        return True

    days_left = (next_dt - today).days
    logger.info(f"대기 중 — 다음 리밸런싱까지 {days_left}일 남음 ({next_dt.strftime('%Y%m%d')})")
    return False


# ── 파이프라인 ───────────────────────────────────────────────────────

def run_pipeline(config_path: str = "config/config.yaml") -> None:
    """전체 파이프라인 실행:
        1. 수급 데이터 수집 (collector)
        2. 종목 선정 + 리밸런싱 주문 (rebalancer — Windows 전용)
    """
    sys.path.insert(0, SRC_DIR)

    from collector import collect_all
    from rebalancer import run as run_rebalance

    today = datetime.today().strftime("%Y%m%d")
    logger.info(f"{'='*52}")
    logger.info(f"파이프라인 시작 — 기준일: {today}")
    logger.info(f"{'='*52}")

    try:
        logger.info("[1/2] 수급 데이터 수집 중...")
        collect_all(end_date=today, config_path=config_path)

        logger.info("[2/2] 종목 선정 및 리밸런싱 주문 실행 중...")
        run_rebalance(date=today, config_path=config_path)

        save_last_run_date(today)
        logger.info(f"파이프라인 완료 — {today}")

    except Exception as e:
        logger.error(f"파이프라인 실행 중 오류 발생: {e}", exc_info=True)


def check_and_run(config_path: str = "config/config.yaml") -> None:
    """리밸런싱 예정일이면 파이프라인 실행."""
    config = load_config(config_path)
    interval = config["rebalancing"]["interval_weeks"]

    if is_rebalancing_due(interval_weeks=interval):
        run_pipeline(config_path=config_path)


# ── 스케줄러 진입점 ──────────────────────────────────────────────────

def start_scheduler(config_path: str = "config/config.yaml") -> None:
    """스케줄러 시작.

    매 영업일(월~금) 09:30에 리밸런싱 예정일 여부를 확인합니다.
    시작 시 즉시 한 번 확인 후, 이후 스케줄에 따라 반복합니다.
    """
    logger.info("스케줄러 시작 — 매 영업일 09:30 리밸런싱 예정일 확인")
    logger.info("종료하려면 Ctrl+C를 누르세요.")

    for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
        getattr(schedule.every(), day).at("09:30").do(
            check_and_run, config_path=config_path
        )

    # 시작 시 즉시 한 번 확인
    check_and_run(config_path=config_path)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # 30초마다 스케줄 체크
    except KeyboardInterrupt:
        logger.info("스케줄러 종료 (Ctrl+C)")


if __name__ == "__main__":
    # --now 옵션: 예정일 무관하게 즉시 파이프라인 실행
    if "--now" in sys.argv:
        logger.info("즉시 실행 모드 (--now)")
        run_pipeline()
    else:
        start_scheduler()
