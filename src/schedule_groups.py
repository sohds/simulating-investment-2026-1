"""
schedule_groups.py

2주 리밸런싱 그룹 기간표 관리 모듈.

GN 기간에 수급 데이터를 수집·종목을 선정(시그널)하고,
GN+1 기간에 해당 종목으로 투자를 실행하는 구조.
따라서 실제 투자는 G2부터 시작됩니다.

그룹 기간표는 config/rebalancing_groups.yaml 에서 연도별로 정의합니다.

참조: github.com/sohds/Ko-ActiveETF

사용:
    from schedule_groups import RebalancingSchedule

    sched = RebalancingSchedule(2026)
    group = sched.find_group("20260319")
    signal = sched.get_signal_group("20260319")
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Union

import yaml


@dataclass
class Group:
    """리밸런싱 그룹 (2주 단위)."""
    name: str
    start: date
    end: date
    holidays: str

    @property
    def start_str(self) -> str:
        return self.start.strftime("%Y%m%d")

    @property
    def end_str(self) -> str:
        return self.end.strftime("%Y%m%d")

    def __str__(self) -> str:
        hol = f" ({self.holidays})" if self.holidays else ""
        return (
            f"{self.name}: {self.start.strftime('%m/%d')} ~ "
            f"{self.end.strftime('%m/%d')}{hol}"
        )


def _parse_date(d: Union[str, date]) -> date:
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y%m%d").date()


class RebalancingSchedule:
    """연도별 2주 리밸런싱 그룹 기간표.

    Args:
        year: 대상 연도
        groups_path: rebalancing_groups.yaml 파일 경로
    """

    def __init__(
        self,
        year: int,
        groups_path: str = "config/rebalancing_groups.yaml",
    ):
        self.year = year
        self.groups: list[Group] = self._load(groups_path, year)

    @staticmethod
    def _load(path: str, year: int) -> list[Group]:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw = data.get(year)
        if not raw:
            raise ValueError(
                f"{year}년 리밸런싱 그룹이 정의되어 있지 않습니다. "
                f"{path}에 {year}: 섹션을 추가하세요."
            )

        return [
            Group(
                name=g["group"],
                start=datetime.strptime(g["start"], "%Y-%m-%d").date(),
                end=datetime.strptime(g["end"], "%Y-%m-%d").date(),
                holidays=g.get("holidays", ""),
            )
            for g in raw
        ]

    def find_group(self, d: Union[str, date]) -> Optional[Group]:
        """날짜가 속한 그룹을 반환합니다. 어떤 그룹에도 속하지 않으면 None."""
        target = _parse_date(d)
        for g in self.groups:
            if g.start <= target <= g.end:
                return g
        return None

    def get_signal_group(self, d: Union[str, date]) -> Optional[Group]:
        """현재 투자 그룹(GN+1)에 대한 시그널 그룹(GN)을 반환합니다.

        GN에서 종목 선정 → GN+1에서 투자 실행이므로,
        현재 그룹의 직전 그룹을 반환합니다.
        첫 번째 그룹(G1)에는 시그널 그룹이 없으므로 None.
        """
        current = self.find_group(d)
        if current is None:
            return None
        idx = self.groups.index(current)
        return self.groups[idx - 1] if idx > 0 else None

    def is_investable_group(self, d: Union[str, date]) -> bool:
        """현재 그룹이 투자 가능한 그룹(G2 이상)인지 확인합니다.

        G1은 시그널 수집만 하고 투자는 G2부터 시작.
        """
        return self.get_signal_group(d) is not None

    def get_next_group(self, d: Union[str, date]) -> Optional[Group]:
        """현재 그룹의 다음 그룹을 반환합니다."""
        current = self.find_group(d)
        if current is None:
            return None
        idx = self.groups.index(current)
        return self.groups[idx + 1] if idx + 1 < len(self.groups) else None

    def print_schedule(self) -> None:
        """전체 그룹 기간표를 출력합니다."""
        print(f"\n{'='*52}")
        print(f"  {self.year}년 2주 리밸런싱 그룹 기간표")
        print(f"{'='*52}")
        for g in self.groups:
            invest = "시그널 전용" if g == self.groups[0] else "시그널+투자"
            print(f"  {g}  [{invest}]")
        print(f"{'='*52}\n")


if __name__ == "__main__":
    import sys

    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.today().year
    sched = RebalancingSchedule(year)
    sched.print_schedule()

    today = datetime.today().strftime("%Y%m%d")
    current = sched.find_group(today)
    if current:
        print(f"오늘({today})은 {current.name} 기간입니다.")
        signal = sched.get_signal_group(today)
        if signal:
            print(f"시그널 그룹: {signal.name} ({signal.start_str} ~ {signal.end_str})")
            print(f"시그널 수집 마감일: {signal.end_str}")
        else:
            print("첫 번째 그룹 — 시그널 수집 기간 (투자 미실행)")
    else:
        print(f"오늘({today})은 정의된 그룹 기간에 속하지 않습니다.")
