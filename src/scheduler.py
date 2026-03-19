"""
scheduler.py

2주 리밸런싱 그룹 기간표 기반 자동 스케줄러.

동작 방식:
    - 매 영업일(월~금) 오전 09:30에 현재 그룹 확인
    - 새로운 투자 그룹(GN+1)이 시작되면 시그널 그룹(GN)의 데이터로 파이프라인 실행
    - GN 기간 시그널 → GN+1 기간 투자 (G1은 시그널만, 실투자는 G2부터)
    - 마지막 실행 그룹은 logs/last_rebalancing_group.txt에 저장

전체 파이프라인:
    [수급 데이터 수집] → [종목 선정] → [리밸런싱 주문] → [이력 저장]

실행:
    python src/scheduler.py              # 스케줄러 시작 (종료: Ctrl+C)
    python src/scheduler.py --now        # 현재 그룹 즉시 실행
    python src/scheduler.py --schedule   # 그룹 기간표 출력

⚠️  리밸런싱 주문 실행은 Windows 전용 (rebalancer → kiwoom_api 의존)
    수급 데이터 수집·종목 선정만 테스트하려면 collector.py / selector.py 를 직접 실행하세요.
"""

import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

import schedule
import yaml

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)

from schedule_groups import Group, RebalancingSchedule

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

LAST_GROUP_FILE = "logs/last_rebalancing_group.txt"


# ── 유틸리티 ─────────────────────────────────────────────────────────

def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_last_executed_group() -> Optional[str]:
    """마지막으로 실행 완료된 그룹 이름 읽기 (예: 'G5')."""
    if not os.path.isfile(LAST_GROUP_FILE):
        return None
    with open(LAST_GROUP_FILE, "r") as f:
        content = f.read().strip()
        return content.split()[0] if content else None


def save_last_executed_group(group_name: str, date: str) -> None:
    """실행 완료 그룹 저장."""
    with open(LAST_GROUP_FILE, "w") as f:
        f.write(f"{group_name} {date}")


def build_schedule(config: dict) -> RebalancingSchedule:
    """config에서 연도와 그룹 파일 경로를 읽어 스케줄 객체 생성."""
    year = config["rebalancing"]["year"]
    groups_file = config["rebalancing"]["groups_file"]
    return RebalancingSchedule(year, groups_file)


# ── 파이프라인 ───────────────────────────────────────────────────────

def run_pipeline(
    signal_group: Group,
    invest_group: Group,
    config_path: str = "config/config.yaml",
) -> None:
    """전체 파이프라인 실행.

    Args:
        signal_group: 시그널 그룹 (GN) — 이 그룹의 마지막 날짜 기준으로 데이터 수집
        invest_group: 투자 그룹 (GN+1) — 실제 매매 실행 대상
        config_path: config.yaml 경로
    """
    from collector import collect_all
    from rebalancer import run as run_rebalance

    signal_date = signal_group.end_str
    today = datetime.today().strftime("%Y%m%d")

    logger.info(f"{'='*56}")
    logger.info(f"  투자 그룹: {invest_group.name}  |  시그널 그룹: {signal_group.name}")
    logger.info(f"  시그널 수집 마감일: {signal_date}  |  실행일: {today}")
    logger.info(f"{'='*56}")

    try:
        logger.info("[1/2] 수급 데이터 수집 중...")
        collect_all(end_date=signal_date, config_path=config_path)

        logger.info("[2/2] 종목 선정 및 리밸런싱 주문 실행 중...")
        run_rebalance(
            signal_date=signal_date,
            group_name=invest_group.name,
            config_path=config_path,
        )

        save_last_executed_group(invest_group.name, today)
        logger.info(f"파이프라인 완료 — {invest_group.name} (시그널: {signal_group.name})")

    except Exception as e:
        logger.error(f"파이프라인 실행 중 오류 발생: {e}", exc_info=True)


def check_and_run(config_path: str = "config/config.yaml") -> None:
    """현재 날짜의 그룹을 확인하고, 새 그룹이면 파이프라인 실행."""
    config = load_config(config_path)
    sched = build_schedule(config)

    today = datetime.today().strftime("%Y%m%d")
    current_group = sched.find_group(today)

    if current_group is None:
        logger.info(f"오늘({today})은 정의된 그룹 기간에 속하지 않습니다. 대기.")
        return

    last_group = get_last_executed_group()

    if last_group == current_group.name:
        next_group = sched.get_next_group(today)
        if next_group:
            logger.info(
                f"이미 실행됨 ({current_group.name}). "
                f"다음 그룹: {next_group.name} ({next_group.start_str}~)"
            )
        else:
            logger.info(f"이미 실행됨 ({current_group.name}). 올해 마지막 그룹.")
        return

    signal_group = sched.get_signal_group(today)

    if signal_group is None:
        logger.info(
            f"현재 {current_group.name} (첫 번째 그룹) — "
            f"시그널 수집 기간입니다. 투자는 다음 그룹부터 시작."
        )
        save_last_executed_group(current_group.name, today)
        return

    logger.info(f"새 투자 그룹 감지: {current_group.name} → 파이프라인 실행")
    run_pipeline(signal_group, current_group, config_path)


# ── 스케줄러 진입점 ──────────────────────────────────────────────────

def start_scheduler(config_path: str = "config/config.yaml") -> None:
    """스케줄러 시작. 매 영업일(월~금) 09:30에 그룹 확인."""
    config = load_config(config_path)
    sched = build_schedule(config)

    logger.info("스케줄러 시작 — 매 영업일 09:30 그룹 기간표 기반 리밸런싱 확인")
    logger.info("종료하려면 Ctrl+C를 누르세요.\n")
    sched.print_schedule()

    for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
        getattr(schedule.every(), day).at("09:30").do(
            check_and_run, config_path=config_path
        )

    check_and_run(config_path=config_path)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("스케줄러 종료 (Ctrl+C)")


if __name__ == "__main__":
    if "--schedule" in sys.argv:
        config = load_config()
        sched = build_schedule(config)
        sched.print_schedule()

    elif "--now" in sys.argv:
        logger.info("즉시 실행 모드 (--now)")
        check_and_run()

    else:
        start_scheduler()
