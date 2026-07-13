"""화면과 사용자 흐름.

UI에서 DB·LLM을 직접 호출하지 않고 담당 모듈(database 등)을 거친다 (architecture.md 규칙).
st.session_state는 화면의 임시 상태에만 쓰고, 연구 데이터는 Supabase에 남긴다 (CLAUDE.md 규칙).
"""

import streamlit as st

import database

st.set_page_config(page_title="당뇨 건강 도우미", page_icon="💙")


def log_app_opened_once() -> None:
    """app_opened는 접속당 1회만 기록한다. Streamlit은 상호작용마다 스크립트를 다시 실행하므로
    이 가드가 없으면 같은 접속이 여러 번 기록된다."""
    if st.session_state.get("app_opened_logged"):
        return
    try:
        database.log_event("app_opened")
    except Exception as exc:
        database.log_technical_error("db_insert_failed", f"app_opened: {exc}")
    st.session_state["app_opened_logged"] = True


def start_session(participant_id: str) -> None:
    """세션을 새로 만들거나, 최근에 열린 세션을 이어받는다.

    새로고침해도 세션이 중복 생성되지 않도록 기존 세션을 먼저 찾는다.
    """
    session = database.find_open_session(participant_id)
    is_new = session is None
    if is_new:
        session = database.create_session(participant_id)

    st.session_state["participant_id"] = participant_id
    st.session_state["session_id"] = session["session_id"]

    if is_new:
        database.log_event("session_started", participant_id, session["session_id"])


def render_login() -> None:
    st.title("당뇨 건강 도우미")
    st.write("참여자 코드를 입력해 주세요.")

    with st.form("login_form"):
        code = st.text_input("참여자 코드", placeholder="예: P001")
        submitted = st.form_submit_button("시작하기")

    if not submitted:
        return

    code = code.strip().upper()
    if not code:
        st.warning("참여자 코드를 입력해 주세요.")
        return

    try:
        participant = database.get_participant(code)
    except Exception as exc:
        database.log_technical_error("db_select_failed", f"get_participant: {exc}")
        st.error("일시적인 오류가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if participant is None:
        st.error("등록되지 않은 코드입니다. 연구자에게 문의해 주세요.")
        return

    if participant["status"] != "active":
        st.error("아직 사용할 수 없는 코드입니다. 연구자에게 문의해 주세요.")
        return

    try:
        start_session(code)
    except Exception as exc:
        database.log_technical_error("db_insert_failed", f"start_session: {exc}", participant_id=code)
        st.error("접속을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    st.rerun()


def render_home() -> None:
    st.title("당뇨 건강 도우미")
    st.success(f"{st.session_state['participant_id']}님, 안녕하세요.")
    st.caption("접속이 기록되었습니다. 다음 단계에서 대화 화면이 추가됩니다.")


log_app_opened_once()

if "session_id" in st.session_state:
    render_home()
else:
    render_login()
