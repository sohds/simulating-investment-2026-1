"""
kiwoom_api.py

키움 OpenAPI 연결, 계좌 조회, 주문 실행 모듈.
⚠️  Windows 전용 (pykiwoom / PyQt5 COM 객체 필요)

실행:
    python src/kiwoom_api.py    # 연결 테스트 (예수금·보유 종목 출력)
"""

import sys

import pandas as pd
import yaml
from PyQt5.QtWidgets import QApplication
from pykiwoom.kiwoom import Kiwoom


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class KiwoomAPI:
    """키움 OpenAPI 래퍼 클래스.

    block_request()를 사용해 TR 요청을 동기(블로킹) 방식으로 처리합니다.
    모의투자 서버 전용으로 설계되어 있습니다 (config.yaml mock: true).
    """

    # 화면 번호 — 중복 사용 시 이전 요청이 취소되므로 기능별로 구분
    SCREEN_DEPOSIT  = "2001"
    SCREEN_HOLDINGS = "2002"
    SCREEN_PRICE    = "2003"
    SCREEN_ORDER    = "0101"

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.acc_no = self.config["account"]["number"]
        self.kiwoom = Kiwoom()

    def connect(self) -> None:
        """키움 OpenAPI 로그인.
        팝업 창이 열리면 '모의투자 서버' 체크 후 로그인하세요.
        """
        self.kiwoom.CommConnect(block=True)
        user = self.kiwoom.GetLoginInfo("USER_NAME")
        print(f"[로그인 완료] 사용자: {user} / 계좌: {self.acc_no}")

    def get_deposit(self) -> int:
        """주문 가능 예수금 조회 (원).

        TR: opw00001 — 예수금상세현황요청
        """
        df = self.kiwoom.block_request(
            "opw00001",
            계좌번호=self.acc_no,
            비밀번호="",
            비밀번호입력매체구분="00",
            조회구분="1",
            output="예수금상세현황",
            next=0,
        )
        raw = str(df["주문가능금액"].iloc[0]).replace(",", "")
        return int(raw)

    def get_holdings(self) -> pd.DataFrame:
        """보유 종목 조회.

        TR: opw00018 — 계좌평가잔고내역요청

        Returns:
            columns=[종목코드, 종목명, 보유수량, 매입단가, 현재가, 평가손익, 수익률]
            보유 종목 없으면 빈 DataFrame 반환.
        """
        df = self.kiwoom.block_request(
            "opw00018",
            계좌번호=self.acc_no,
            비밀번호="",
            비밀번호입력매체구분="00",
            조회구분="1",
            output="계좌평가잔고개별합산",
            next=0,
        )

        if df is None or df.empty:
            return pd.DataFrame(
                columns=["종목코드", "종목명", "보유수량", "매입단가", "현재가", "평가손익", "수익률"]
            )

        # 숫자 컬럼 정제 (쉼표 제거 후 int 변환)
        for col in ["보유수량", "매입단가", "현재가", "평가손익"]:
            df[col] = (
                df[col].astype(str).str.replace(",", "")
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0).astype(int)
            )
        df["수익률"] = (
            df["수익률"].astype(str).str.replace(",", "")
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )

        return df[["종목코드", "종목명", "보유수량", "매입단가", "현재가", "평가손익", "수익률"]]

    def get_current_price(self, code: str) -> int:
        """종목 현재가 조회 (원).

        TR: opt10001 — 주식기본정보요청

        Args:
            code: 종목 코드 (예: "005930")
        """
        df = self.kiwoom.block_request(
            "opt10001",
            종목코드=code,
            output="주식기본정보",
            next=0,
        )
        # 하한가 시 음수로 내려올 수 있으므로 abs 처리
        raw = str(df["현재가"].iloc[0]).replace(",", "")
        return abs(int(raw))

    def buy(self, code: str, qty: int) -> int:
        """시장가 매수 주문.

        Args:
            code: 종목 코드
            qty: 매수 수량

        Returns:
            주문 번호 (0이면 실패)
        """
        return self.kiwoom.SendOrder(
            "시장가매수",       # 요청명 (임의 지정)
            self.SCREEN_ORDER,
            self.acc_no,
            1,                 # 주문 유형: 1=매수
            code,
            qty,
            0,                 # 시장가는 가격 0
            "03",              # 호가 구분: 03=시장가
            "",                # 원주문번호 (신규 주문이므로 빈 문자열)
        )

    def sell(self, code: str, qty: int) -> int:
        """시장가 매도 주문.

        Args:
            code: 종목 코드
            qty: 매도 수량

        Returns:
            주문 번호 (0이면 실패)
        """
        return self.kiwoom.SendOrder(
            "시장가매도",
            self.SCREEN_ORDER,
            self.acc_no,
            2,                 # 주문 유형: 2=매도
            code,
            qty,
            0,
            "03",
            "",
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    api = KiwoomAPI()
    api.connect()

    print("\n=== 예수금 ===")
    deposit = api.get_deposit()
    print(f"{deposit:,}원")

    print("\n=== 보유 종목 ===")
    holdings = api.get_holdings()
    if holdings.empty:
        print("보유 종목 없음")
    else:
        print(holdings.to_string(index=False))
