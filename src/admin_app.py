"""연구자용 관리자 대시보드 — 참여자 앱과 완전 분리된 별도 앱 (PRD §8-1 · D22).

- **참여자 앱과 다른 URL로만** 접근한다. Streamlit Cloud에서 이 파일을 메인으로
  하는 별도 앱으로 배포하고, 비밀번호(`ADMIN_PASSWORD` 시크릿)로 보호한다.
- 연구 행동 데이터(messages·events·nudge_events·retrieval_logs)는 **읽기 전용**.
  수정·삭제 기능을 두지 않는다(데이터 무결성).
- 참여자는 **익명 ID로만** 표시한다(직접식별정보 없음).
- 이 앱은 참여자 앱의 핵심 500줄 로직에 포함되지 않는다(D22).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

import database

st.set_page_config(page_title="연구자 대시보드", page_icon="📊", layout="wide")


def check_password() -> bool:
    """비밀번호 게이트. 앱 시크릿 ADMIN_PASSWORD(또는 환경변수)와 일치해야 통과."""
    try:
        secret = str(st.secrets.get("ADMIN_PASSWORD", ""))
    except Exception:      # secrets.toml이 없으면(로컬 등) 접근만으로 예외가 난다
        secret = ""
    expected = secret or os.getenv("ADMIN_PASSWORD", "")
    if not expected:
        st.error("ADMIN_PASSWORD가 설정되지 않았습니다. 앱 시크릿에 추가해 주세요.")
        return False
    if st.session_state.get("admin_ok"):
        return True
    st.title("📊 연구자 대시보드")
    pw = st.text_input("관리자 비밀번호", type="password")
    if st.button("들어가기", type="primary") and pw:
        if pw == expected:
            st.session_state["admin_ok"] = True
            st.rerun()
        st.error("비밀번호가 올바르지 않습니다.")
    return False


@st.cache_data(ttl=60, show_spinner=False)
def load(table: str, cols: str = "*") -> pd.DataFrame:
    """테이블을 DataFrame으로 읽는다(60초 캐시). 대규모 연구에서는 페이지네이션 필요(현재 파일럿 규모)."""
    rows = database.get_client().table(table).select(cols).limit(10000).execute().data
    return pd.DataFrame(rows)


def col(df: pd.DataFrame, name: str) -> pd.Series:
    """빈 DataFrame·없는 컬럼에도 안전하게 열을 돌려준다(집계용)."""
    if df.empty or name not in df.columns:
        return pd.Series([], dtype=object)
    return df[name]


def rate(part: int, whole: int) -> str:
    """전환율 문자열. 분모가 0이면 '-'."""
    return f"{part / whole * 100:.0f}%  ({part}/{whole})" if whole else "-"


def participant_table(parts, sessions, msgs) -> pd.DataFrame:
    """참여자별 요약: 세션 수·질문 수·넛지응답 수·마지막 활동."""
    rows = []
    for pid in col(parts, "participant_id"):
        m = msgs[col(msgs, "participant_id") == pid] if not msgs.empty else msgs
        s = sessions[col(sessions, "participant_id") == pid] if not sessions.empty else sessions
        status = parts.loc[parts.participant_id == pid, "status"].iloc[0] if "status" in parts else "-"
        rows.append({
            "참여자": pid,
            "상태": status,
            "세션수": len(s),
            "질문수": int(((col(m, "role") == "user") & (col(m, "message_type") == "rag_question")).sum()),
            "넛지응답": int((col(m, "message_type") == "nudge_response").sum()),
            "마지막 활동": (col(m, "created_at").max() or "-")[:16] if len(m) else "-",
        })
    return pd.DataFrame(rows)


def main() -> None:
    st.title("📊 연구자 대시보드")
    st.caption("참여자 앱과 분리된 읽기 전용 화면 · 참여자는 익명 ID로만 표시")
    if st.button("🔄 새로고침(캐시 비우기)"):
        st.cache_data.clear()
        st.rerun()

    parts = load("participants")
    sessions = load("sessions", "session_id, participant_id, started_at")
    msgs = load("messages", "participant_id, role, message_type, created_at")
    events = load("events", "event_type, participant_id")
    nudges = load("nudge_events", "status, response, action_commitment, template_key")
    retr = load("retrieval_logs", "evidence_level")
    calls = load("model_calls", "call_type, input_tokens, output_tokens, latency_ms, status")
    errors = load("technical_errors", "error_type")

    # ── 참여 현황 ────────────────────────────────────────────
    st.header("참여 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("참여자 수", len(parts))
    c2.metric("총 세션 수", len(sessions))
    c3.metric("총 질문 수", int(((col(msgs, "role") == "user") &
                                (col(msgs, "message_type") == "rag_question")).sum()))
    st.dataframe(participant_table(parts, sessions, msgs), use_container_width=True, hide_index=True)

    # ── 넛지 성과 ────────────────────────────────────────────
    st.header("넛지 성과")
    displayed = len(nudges)
    answered = int((col(nudges, "status") == "answered").sum())
    committed = int(col(nudges, "action_commitment").notna().sum()) if not nudges.empty else 0
    n1, n2, n3 = st.columns(3)
    n1.metric("넛지 노출", displayed)
    n2.metric("응답 전환율", rate(answered, displayed))
    n3.metric("행동 약속(하겠다)", committed)
    if not nudges.empty and "template_key" in nudges:
        by_tpl = nudges.groupby("template_key").size().reset_index(name="노출수")
        st.dataframe(by_tpl, use_container_width=True, hide_index=True)

    # ── 질문 · 근거 ─────────────────────────────────────────
    st.header("질문 · 근거")
    clicks = int((col(events, "event_type") == "source_clicked").sum())
    questions = int((col(events, "event_type") == "question_asked").sum())
    q1, q2 = st.columns(2)
    q1.metric("질문 발생(이벤트)", questions)
    q2.metric("출처 클릭", clicks)
    if not retr.empty and "evidence_level" in retr:
        lvl = retr["evidence_level"].value_counts().reset_index()
        lvl.columns = ["근거 충분성", "건수"]
        st.dataframe(lvl, use_container_width=True, hide_index=True)

    # ── 안전 ────────────────────────────────────────────────
    st.header("안전")
    safety = int((col(events, "event_type") == "safety_message_shown").sum())
    st.metric("안전 안내 노출(safety_message_shown)", safety)

    # ── 비용 · 운영 ─────────────────────────────────────────
    st.header("비용 · 운영")
    if not calls.empty:
        agg = calls.groupby("call_type").agg(
            호출수=("call_type", "size"),
            입력토큰=("input_tokens", "sum"),
            출력토큰=("output_tokens", "sum"),
            평균지연ms=("latency_ms", "mean"),
        ).reset_index()
        agg["평균지연ms"] = agg["평균지연ms"].round(0)
        st.dataframe(agg, use_container_width=True, hide_index=True)
        fails = int((col(calls, "status") != "success").sum())
        st.caption(f"API 실패 호출: {fails}건")
    else:
        st.caption("API 호출 기록이 아직 없습니다.")
    if not errors.empty:
        st.dataframe(errors["error_type"].value_counts().reset_index(),
                     use_container_width=True, hide_index=True)

    # ── CSV 추출 ────────────────────────────────────────────
    st.header("데이터 추출 (CSV)")
    st.caption("분석용 원자료를 내려받습니다. 직접식별정보는 저장되지 않습니다.")
    cols = st.columns(4)
    for i, (label, table) in enumerate([
        ("참여자", "participants"), ("세션", "sessions"), ("메시지", "messages"),
        ("이벤트", "events"), ("넛지", "nudge_events"), ("검색로그", "retrieval_logs"),
        ("API호출", "model_calls"), ("기술오류", "technical_errors"),
    ]):
        df = load(table)
        cols[i % 4].download_button(
            f"⬇ {label}", df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{table}.csv", mime="text/csv", use_container_width=True,
            key=f"dl_{table}", disabled=df.empty)


if check_password():
    main()
