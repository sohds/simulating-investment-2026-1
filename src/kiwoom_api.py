"""
kiwoom_api.py

키움 REST API 연결, 계좌 조회, 주문 실행 모듈.
모의투자 서버: https://mockapi.kiwoom.com
공식 문서: https://openapi.kiwoom.com/guide/apiguide

실행:
    python src/kiwoom_api.py    # 연결 테스트 (예수금·보유 종목 출력)
"""

import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests
import yaml


# ── 서버 URL ────────────────────────────────────────────────────────
MOCK_BASE_URL = "https://mockapi.kiwoom.com"
REAL_BASE_URL = "https://api.kiwoom.com"


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class KiwoomAPI:
    """키움 REST API 래퍼 클래스.

    OAuth2 client_credentials 방식으로 토큰을 발급하고,
    Bearer 토큰을 Authorization 헤더에 실어 각 API를 호출합니다.
    모의투자 전용 (config.yaml mock: true).

    API 경로 및 api-id 매핑 (공식 문서 기준):
        예수금 조회       kt00001  POST /api/dostk/acnt
        계좌평가/보유종목  kt00004  POST /api/dostk/acnt
        주식 현재가       ka10001  POST /api/dostk/stkinfo
        주식 매수         kt10000  POST /api/dostk/ordr
        주식 매도         kt10001  POST /api/dostk/ordr
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.acc_no    = str(self.config["account"]["number"])
        self.appkey    = self.config["account"]["appkey"]
        self.secretkey = self.config["account"]["secretkey"]
        self.mock      = self.config["account"].get("mock", True)
        self.base_url  = MOCK_BASE_URL if self.mock else REAL_BASE_URL

        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    # ── 인증 ────────────────────────────────────────────────────────

    def _fetch_token(self) -> None:
        """OAuth2 토큰 발급.

        POST /oauth2/token
        Body: grant_type, appkey, secretkey
        Response: {"token": "...", "token_type": "Bearer", "expires_dt": "YYYYMMDDHHMMSS"}
        """
        url = f"{self.base_url}/oauth2/token"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            json={
                "grant_type": "client_credentials",
                "appkey":     self.appkey,
                "secretkey":  self.secretkey,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["token"]
        # expires_dt 형식: "YYYYMMDDHHMMSS"
        self._token_expires = datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
        print(f"[토큰 발급] 만료: {self._token_expires.strftime('%Y-%m-%d %H:%M:%S')}")

    def _get_token(self) -> str:
        """유효한 토큰 반환 (만료 5분 전 자동 재발급)."""
        if (
            self._token is None
            or self._token_expires is None
            or (self._token_expires - datetime.now()).total_seconds() < 300
        ):
            self._fetch_token()
        assert self._token is not None
        return self._token

    def _headers(self, api_id: str) -> dict:
        """공통 요청 헤더 생성."""
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json;charset=UTF-8",
            "api-id":        api_id,
            "cont-yn":       "N",
            "next-key":      "",
        }

    def connect(self) -> None:
        """토큰 발급으로 연결 확인 (REST는 별도 로그인 불필요)."""
        self._fetch_token()
        print(f"[연결 완료] 서버: {self.base_url} / 계좌: {self.acc_no}")

    # ── 계좌 조회 ───────────────────────────────────────────────────

    def get_deposit(self) -> int:
        """주문 가능 예수금 조회 (원).

        api-id: kt00001
        endpoint: POST /api/dostk/acnt
        response field: ord_alow_amt (주문가능금액)
        """
        url = f"{self.base_url}/api/dostk/acnt"
        resp = requests.post(
            url,
            headers=self._headers("kt00001"),
            json={"qry_tp": "1"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("return_code", -1) != 0:
            raise RuntimeError(f"예수금 조회 실패: {data.get('return_msg')}")

        raw = str(data.get("ord_alow_amt", 0)).replace(",", "")
        return int(raw) if raw else 0

    def get_holdings(self) -> pd.DataFrame:
        """보유 종목 조회.

        api-id: kt00004
        endpoint: POST /api/dostk/acnt
        response list field: stk_acnt_evlt_prst

        Returns:
            columns=[종목코드, 종목명, 보유수량, 매입단가, 현재가, 평가손익, 수익률]
            보유 종목 없으면 빈 DataFrame 반환.
        """
        url = f"{self.base_url}/api/dostk/acnt"
        resp = requests.post(
            url,
            headers=self._headers("kt00004"),
            json={"qry_tp": "1", "dmst_stex_tp": "KRX"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("return_code", -1) != 0:
            raise RuntimeError(f"보유종목 조회 실패: {data.get('return_msg')}")

        items = data.get("stk_acnt_evlt_prst", [])
        if not items:
            return pd.DataFrame(
                columns=["종목코드", "종목명", "보유수량", "매입단가", "현재가", "평가손익", "수익률"]
            )

        rows = []
        for item in items:
            raw_cd = item.get("stk_cd", "")
            stk_cd = raw_cd.lstrip("AQ") if raw_cd else ""
            rows.append({
                "종목코드": stk_cd,
                "종목명":   item.get("stk_nm", ""),
                "보유수량": int(str(item.get("rmnd_qty", 0)).replace(",", "")),
                "매입단가": int(str(item.get("avg_prc", 0)).replace(",", "")),
                "현재가":   abs(int(str(item.get("cur_prc", 0)).replace(",", "").lstrip("-"))),
                "평가손익": int(str(item.get("pl_amt", 0)).replace(",", "")),
                "수익률":   float(str(item.get("pl_rt", 0)).replace(",", "")),
            })

        return pd.DataFrame(rows)

    def get_current_price(self, code: str) -> int:
        """종목 현재가 조회 (원).

        api-id: ka10001
        endpoint: POST /api/dostk/stkinfo
        response field: cur_prc

        Args:
            code: 종목 코드 (예: "005930")
        """
        url = f"{self.base_url}/api/dostk/stkinfo"
        time.sleep(1)
        resp = requests.post(
            url,
            headers=self._headers("ka10001"),
            json={"stk_cd": code},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("return_code", -1) != 0:
            raise RuntimeError(f"현재가 조회 실패 [{code}]: {data.get('return_msg')}")

        raw = str(data.get("cur_prc", 0)).replace(",", "").lstrip("-")
        return abs(int(raw)) if raw else 0

    # ── 주문 ────────────────────────────────────────────────────────

    def buy(self, code: str, qty: int) -> str:
        """시장가 매수 주문.

        api-id: kt10000
        endpoint: POST /api/dostk/ordr

        Args:
            code: 종목 코드
            qty:  매수 수량

        Returns:
            주문 번호 (빈 문자열이면 실패)
        """
        return self._send_order(code=code, qty=qty, order_side="buy")

    def sell(self, code: str, qty: int) -> str:
        """시장가 매도 주문.

        api-id: kt10001
        endpoint: POST /api/dostk/ordr

        Args:
            code: 종목 코드
            qty:  매도 수량

        Returns:
            주문 번호 (빈 문자열이면 실패)
        """
        return self._send_order(code=code, qty=qty, order_side="sell")

    def _send_order(self, code: str, qty: int, order_side: str) -> str:
        """주문 실행 공통 로직.

        Args:
            code:       종목 코드
            qty:        수량
            order_side: "buy" 또는 "sell"
        """
        api_id = "kt10000" if order_side == "buy" else "kt10001"
        url = f"{self.base_url}/api/dostk/ordr"

        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":       code,
            "ord_qty":      str(qty),
            "trde_tp":      "3",    # 3 = 시장가
            "ord_uv":       "0",    # 시장가는 0
        }

        resp = requests.post(
            url,
            headers=self._headers(api_id),
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("return_code", -1) != 0:
            print(f"  [주문 실패] {data.get('return_msg')}")
            return ""

        return str(data.get("ord_no", ""))


if __name__ == "__main__":
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
