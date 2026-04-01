"""
dashboard.py

키움 모의투자 Dash 대시보드.
실행: python src/dashboard.py  (프로젝트 루트에서)
브라우저: http://localhost:8050
"""
import contextlib
import io
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import yaml
import dash
from dash import Input, Output, State, callback_context, dash_table, dcc, html
import dash_bootstrap_components as dbc

# src/ 를 import 경로에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kiwoom_api import KiwoomAPI
from schedule_groups import RebalancingSchedule

CONFIG_PATH = str(ROOT / "config" / "config.yaml")


# ── 전역 상태 ────────────────────────────────────────────────────────
_api: Optional[KiwoomAPI] = None
_log_queues: dict[str, queue.Queue] = {
    "rebalance": queue.Queue(),
    "collect": queue.Queue(),
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_api() -> KiwoomAPI:
    global _api
    if _api is None:
        _api = KiwoomAPI(CONFIG_PATH)
        _api.connect()
    return _api


def reset_api():
    global _api
    _api = None


# ── 백그라운드 태스크 실행 ───────────────────────────────────────────

def run_in_thread(target, q: queue.Queue):
    """target 함수를 스레드에서 실행하며 print 출력을 queue에 넣는다."""

    class QueueWriter(io.TextIOBase):
        def write(self, s: str) -> int:
            if s.strip():
                q.put(s)
            return len(s)

    with contextlib.redirect_stdout(QueueWriter()):
        try:
            target()
        except Exception as e:
            q.put(f"[오류] {e}")
    q.put("__DONE__")


# ── 앱 초기화 ────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    title="모의투자 대시보드",
)


# ── 레이아웃 ─────────────────────────────────────────────────────────

def _stat_card(label: str, card_id: str) -> dbc.Col:
    return dbc.Col(dbc.Card(dbc.CardBody([
        html.P(label, className="text-muted small mb-1"),
        html.H5(id=card_id, className="mb-0"),
    ])), md=4, className="mb-2")


app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H4("모의투자 대시보드", className="my-3"), width="auto"),
        dbc.Col([
            dbc.Badge(id="conn-badge", className="me-2 align-middle fs-6"),
            dbc.Button("연결", id="btn-connect", color="primary", size="sm", className="me-1"),
            dbc.Button("새로고침", id="btn-refresh", color="secondary", size="sm"),
        ], className="d-flex align-items-center"),
    ], align="center"),

    dbc.Tabs(id="tabs", active_tab="tab-portfolio", children=[

        # ── 탭 1: 포트폴리오 ──────────────────────────────────────────
        dbc.Tab(label="포트폴리오", tab_id="tab-portfolio", children=dbc.Container([
            dbc.Row([
                _stat_card("예수금", "card-deposit"),
                _stat_card("총평가금액", "card-total"),
                _stat_card("총평가손익", "card-pnl"),
            ], className="mt-3"),
            dcc.Graph(id="chart-holdings", config={"displayModeBar": False}),
            html.Div(id="table-holdings"),
        ], fluid=True)),

        # ── 탭 2: 리밸런싱 ───────────────────────────────────────────
        dbc.Tab(label="리밸런싱", tab_id="tab-rebalance", children=dbc.Container([
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.P("현재 그룹", className="text-muted small mb-1"),
                    html.H5(id="card-group"),
                ])), md=4, className="mb-2 mt-3"),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.P("시그널 날짜", className="text-muted small mb-1"),
                    html.H5(id="card-signal-date"),
                ])), md=4, className="mb-2 mt-3"),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.P("다음 수집일", className="text-muted small mb-1"),
                    html.H5(id="card-next-collect"),
                ])), md=4, className="mb-2 mt-3"),
            ]),
            html.H6("선정 종목", className="mt-2 mb-2"),
            html.Div(id="table-selected"),
            dbc.Row([
                dbc.Col(dbc.Input(
                    id="input-signal-date",
                    placeholder="시그널 날짜 (예: 20260318)",
                    type="text", size="sm",
                ), md=3),
                dbc.Col(dbc.Button(
                    "리밸런싱 실행", id="btn-rebalance", color="danger", size="sm",
                ), width="auto"),
            ], align="center", className="mt-3 mb-2"),
            html.Pre(
                id="log-rebalance",
                className="bg-dark text-light p-3 rounded mt-2",
                style={"minHeight": "180px", "fontSize": "12px", "whiteSpace": "pre-wrap"},
            ),
            dcc.Interval(id="interval-rebalance", interval=500, disabled=True),
        ], fluid=True)),

        # ── 탭 3: 수집·선정 ──────────────────────────────────────────
        dbc.Tab(label="수집·선정", tab_id="tab-collect", children=dbc.Container([
            html.H6("KRX 세션 쿠키", className="mt-3 mb-2"),
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("JSESSIONID", className="small fw-bold"),
                        dbc.Input(
                            id="input-jsessionid", type="text", size="sm",
                            placeholder="data.krx.co.kr 개발자도구 → Application → Cookies → JSESSIONID",
                        ),
                    ], md=10),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("extra_cookies (선택)", className="small fw-bold"),
                        dbc.Input(
                            id="input-extracookies", type="text", size="sm",
                            placeholder="__smVisitorID=...; mdc.client_session=true",
                        ),
                    ], md=10),
                ], className="mb-2"),
                dbc.Button("config.yaml에 저장", id="btn-save-krx", color="secondary", size="sm"),
                html.Span(id="krx-save-msg", className="ms-2 small"),
            ]), className="mb-3"),

            html.H6("수집·선정 실행", className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Input(
                    id="input-collect-date",
                    placeholder="날짜 (예: 20260401)",
                    type="text", size="sm",
                ), md=2),
                dbc.Col(dbc.Button(
                    "수집", id="btn-collect", color="primary", size="sm",
                ), width="auto"),
                dbc.Col(dbc.Button(
                    "선정", id="btn-select", color="success", size="sm",
                ), width="auto"),
                dbc.Col(dbc.Button(
                    "수집 + 선정", id="btn-collect-select", color="warning", size="sm",
                ), width="auto"),
            ], align="center", className="mb-2"),
            html.Pre(
                id="log-collect",
                className="bg-dark text-light p-3 rounded mt-2",
                style={"minHeight": "180px", "fontSize": "12px", "whiteSpace": "pre-wrap"},
            ),
            dcc.Interval(id="interval-collect", interval=500, disabled=True),
        ], fluid=True)),

        # ── 탭 4: 리포트 ─────────────────────────────────────────────
        dbc.Tab(label="리포트", tab_id="tab-report", children=dbc.Container([
            dbc.Row([
                dbc.Col(html.Span(id="report-date-badge"), className="mt-3 mb-2"),
            ]),
            dcc.Markdown(
                id="report-content",
                style={"fontFamily": "monospace", "fontSize": "14px"},
            ),
        ], fluid=True)),

        # ── 탭 5: 설정 ───────────────────────────────────────────────
        dbc.Tab(label="설정", tab_id="tab-settings", children=dbc.Container([
            html.H6("계좌 설정", className="mt-3 mb-2"),
            html.Div(id="settings-content"),
        ], fluid=True)),
    ]),
], fluid=True)


# ── 콜백 ─────────────────────────────────────────────────────────────

@app.callback(
    Output("conn-badge", "children"),
    Output("conn-badge", "color"),
    Output("card-deposit", "children"),
    Output("card-total", "children"),
    Output("card-pnl", "children"),
    Output("chart-holdings", "figure"),
    Output("table-holdings", "children"),
    Input("btn-connect", "n_clicks"),
    Input("btn-refresh", "n_clicks"),
    prevent_initial_call=False,
)
def update_portfolio(_c, _r):
    try:
        api = get_api()
        deposit = api.get_deposit()
        holdings = api.get_holdings()

        if holdings.empty:
            fig = go.Figure()
            fig.update_layout(
                title="보유 종목 없음", height=200,
                plot_bgcolor="white", paper_bgcolor="white",
            )
            return "연결됨", "success", f"{deposit:,}원", f"{deposit:,}원", "0원", fig, \
                   html.P("보유 종목이 없습니다.", className="text-muted mt-2")

        holdings_value = int((holdings["현재가"] * holdings["보유수량"]).sum())
        total = deposit + holdings_value
        pnl = int(holdings["평가손익"].sum())

        colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in holdings["수익률"]]
        fig = go.Figure(go.Bar(
            x=holdings["종목명"],
            y=holdings["수익률"],
            marker_color=colors,
            text=[f"{v:+.2f}%" for v in holdings["수익률"]],
            textposition="outside",
        ))
        fig.update_layout(
            title="보유 종목별 수익률 (%)",
            height=380,
            margin=dict(t=50, b=40, l=40, r=20),
            plot_bgcolor="white",
            paper_bgcolor="white",
            yaxis=dict(zeroline=True, zerolinecolor="#ccc", title="%"),
        )

        table = dash_table.DataTable(
            data=holdings.to_dict("records"),
            columns=[{"name": c, "id": c} for c in holdings.columns],
            style_cell={"fontSize": "13px", "textAlign": "right", "padding": "6px"},
            style_cell_conditional=[{"if": {"column_id": "종목명"}, "textAlign": "left"}],
            style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa", "textAlign": "center"},
            style_data_conditional=[
                {"if": {"filter_query": "{평가손익} < 0", "column_id": "평가손익"}, "color": "#e74c3c"},
                {"if": {"filter_query": "{평가손익} >= 0", "column_id": "평가손익"}, "color": "#2ecc71"},
                {"if": {"filter_query": "{수익률} < 0", "column_id": "수익률"}, "color": "#e74c3c"},
                {"if": {"filter_query": "{수익률} >= 0", "column_id": "수익률"}, "color": "#2ecc71"},
            ],
        )

        return "연결됨", "success", f"{deposit:,}원", f"{total:,}원", f"{pnl:+,}원", fig, table

    except Exception as e:
        reset_api()
        empty_fig = go.Figure()
        empty_fig.update_layout(
            annotations=[{"text": f"연결 실패: {e}", "showarrow": False, "font": {"size": 14}}],
            height=200, plot_bgcolor="white", paper_bgcolor="white",
        )
        return "미연결", "danger", "-", "-", "-", empty_fig, None


@app.callback(
    Output("card-group", "children"),
    Output("card-signal-date", "children"),
    Output("card-next-collect", "children"),
    Output("table-selected", "children"),
    Input("tabs", "active_tab"),
)
def update_rebalance_info(active_tab):
    if active_tab != "tab-rebalance":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    cfg = load_config()
    groups_path = str(ROOT / cfg["rebalancing"]["groups_file"])
    sched = RebalancingSchedule(cfg["rebalancing"]["year"], groups_path=groups_path)

    today = datetime.today().strftime("%Y%m%d")
    current = sched.find_group(today)
    signal = sched.get_signal_group(today)
    next_group = sched.get_next_group(today)

    group_str = current.name if current else "그룹 외"
    signal_str = signal.end_str if signal else "-"
    next_str = next_group.end_str if next_group else "-"

    if signal:
        csv_path = ROOT / "data" / "supply_demand" / f"selected_{signal.end_str}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            display_cols = [c for c in ["종목명", "단기_수급강도", "장기_수급강도", "최대_수급강도", "선정_가중치"] if c in df.columns]
            table = dash_table.DataTable(
                data=df[display_cols].to_dict("records"),
                columns=[{"name": c, "id": c} for c in display_cols],
                style_cell={"fontSize": "13px", "textAlign": "right", "padding": "6px"},
                style_cell_conditional=[{"if": {"column_id": "종목명"}, "textAlign": "left"}],
                style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"},
                page_size=16,
            )
        else:
            table = html.P(f"선정 파일 없음: {csv_path.name}", className="text-muted")
    else:
        table = html.P("시그널 그룹 없음", className="text-muted")

    return group_str, signal_str, next_str, table


@app.callback(
    Output("krx-save-msg", "children"),
    Input("btn-save-krx", "n_clicks"),
    State("input-jsessionid", "value"),
    State("input-extracookies", "value"),
    prevent_initial_call=True,
)
def save_krx_cookie(_, jsessionid, extra_cookies):
    if not jsessionid:
        return "⚠ JSESSIONID를 입력하세요."
    cfg = load_config()
    cfg["krx_session"]["jsessionid"] = jsessionid.strip()
    if extra_cookies:
        cfg["krx_session"]["extra_cookies"] = extra_cookies.strip()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    return "✅ 저장 완료"


@app.callback(
    Output("settings-content", "children"),
    Input("tabs", "active_tab"),
)
def update_settings(active_tab):
    if active_tab != "tab-settings":
        return dash.no_update
    cfg = load_config()
    return [
        dbc.Card(dbc.CardBody([
            html.P(f"계좌번호: {cfg['account']['number']}", className="mb-1"),
            html.P(
                f"서버: {'모의투자 (mockapi.kiwoom.com)' if cfg['account']['mock'] else '실계좌 (api.kiwoom.com)'}",
                className="mb-1",
            ),
            html.P(f"appkey: {cfg['account']['appkey'][:12]}...", className="mb-1 text-muted small"),
        ]), className="mb-3"),
        html.H6("현재 KRX 세션", className="mb-2"),
        dbc.Card(dbc.CardBody([
            html.P(
                f"jsessionid: {cfg['krx_session']['jsessionid'][:40]}...",
                className="mb-1 small text-muted",
            ),
            html.P(
                f"extra_cookies: {cfg['krx_session'].get('extra_cookies', '-')}",
                className="mb-1 small text-muted",
            ),
        ])),
    ]


@app.callback(
    Output("log-rebalance", "children"),
    Output("interval-rebalance", "disabled"),
    Output("btn-rebalance", "disabled"),
    Input("btn-rebalance", "n_clicks"),
    Input("interval-rebalance", "n_intervals"),
    State("input-signal-date", "value"),
    State("log-rebalance", "children"),
    prevent_initial_call=True,
)
def handle_rebalance(n_clicks, n_intervals, signal_date, current_log):
    triggered = callback_context.triggered_id

    if triggered == "btn-rebalance":
        if not signal_date:
            return "⚠ 시그널 날짜를 입력하세요.", True, False
        while not _log_queues["rebalance"].empty():
            _log_queues["rebalance"].get_nowait()

        import rebalancer
        def task():
            rebalancer.run(signal_date=signal_date, config_path=CONFIG_PATH)

        threading.Thread(
            target=run_in_thread,
            args=(task, _log_queues["rebalance"]),
            daemon=True,
        ).start()
        return "실행 중...\n", False, True

    # interval 폴링
    lines, done = [], False
    while not _log_queues["rebalance"].empty():
        msg = _log_queues["rebalance"].get_nowait()
        if msg == "__DONE__":
            done = True
        else:
            lines.append(msg)

    new_log = (current_log or "") + "".join(lines)
    if done:
        new_log += "\n✅ 완료"
    return new_log, done, done


@app.callback(
    Output("log-collect", "children"),
    Output("interval-collect", "disabled"),
    Output("btn-collect", "disabled"),
    Output("btn-select", "disabled"),
    Output("btn-collect-select", "disabled"),
    Input("btn-collect", "n_clicks"),
    Input("btn-select", "n_clicks"),
    Input("btn-collect-select", "n_clicks"),
    Input("interval-collect", "n_intervals"),
    State("input-collect-date", "value"),
    State("log-collect", "children"),
    prevent_initial_call=True,
)
def handle_collect(n_col, n_sel, n_both, n_int, collect_date, current_log):
    triggered = callback_context.triggered_id

    if triggered in ("btn-collect", "btn-select", "btn-collect-select"):
        if not collect_date:
            return "⚠ 날짜를 입력하세요.", True, False, False, False
        while not _log_queues["collect"].empty():
            _log_queues["collect"].get_nowait()

        import collector, selector

        if triggered == "btn-collect":
            def task():
                collector.collect_all(end_date=collect_date, config_path=CONFIG_PATH)
        elif triggered == "btn-select":
            def task():
                selector.run(date=collect_date, config_path=CONFIG_PATH)
        else:
            def task():
                collector.collect_all(end_date=collect_date, config_path=CONFIG_PATH)
                selector.run(date=collect_date, config_path=CONFIG_PATH)

        threading.Thread(
            target=run_in_thread,
            args=(task, _log_queues["collect"]),
            daemon=True,
        ).start()
        return "실행 중...\n", False, True, True, True

    # interval 폴링
    lines, done = [], False
    while not _log_queues["collect"].empty():
        msg = _log_queues["collect"].get_nowait()
        if msg == "__DONE__":
            done = True
        else:
            lines.append(msg)

    new_log = (current_log or "") + "".join(lines)
    if done:
        new_log += "\n✅ 완료"
    return new_log, done, done, done, done


@app.callback(
    Output("report-content", "children"),
    Output("report-date-badge", "children"),
    Input("tabs", "active_tab"),
)
def update_report_tab(active_tab: str):
    if active_tab != "tab-report":
        return dash.no_update, dash.no_update

    report_dir = ROOT / "logs" / "final-report"
    if not report_dir.exists():
        return "_리포트 없음. `python src/selector.py`를 실행하세요._", ""

    files = sorted(report_dir.glob("report_*.md"), reverse=True)
    if not files:
        return "_리포트 없음. `python src/selector.py`를 실행하세요._", ""

    latest  = files[0]
    content = latest.read_text(encoding="utf-8")
    raw_date = latest.stem.replace("report_", "")
    date_fmt = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    badge = dbc.Badge(f"최신 리포트: {date_fmt}", color="info", className="fs-6")
    return content, badge


if __name__ == "__main__":
    print("대시보드 시작: http://localhost:8050")
    app.run(debug=False, port=8050)
