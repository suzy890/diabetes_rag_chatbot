"""화면과 사용자 흐름.

UI에서 DB·LLM을 직접 호출하지 않고 담당 모듈(database 등)을 거친다 (architecture.md 규칙).
st.session_state는 화면의 임시 상태에만 쓰고, 연구 데이터는 Supabase에 남긴다 (CLAUDE.md 규칙).
"""

import streamlit as st

import database
import nudge
import rag

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


def maybe_show_nudge(participant_id: str, session_id: str) -> None:
    """규칙에 맞으면 AI가 먼저 넛지를 건넨다. 접속당 한 번만 판단한다(rerun 중복 방지)."""
    if st.session_state.get("nudge_checked"):
        return
    st.session_state["nudge_checked"] = True

    try:
        participant = database.get_participant(participant_id)
        template = nudge.select_nudge(participant)
        if template is None:
            return

        message = database.save_message(
            session_id, participant_id, "assistant", "nudge", template["text"]
        )
        record = database.create_nudge(
            participant_id, session_id,
            {**template, "template_version": nudge.TEMPLATE_VERSION},
            message["message_id"],
        )
        database.log_event("nudge_scheduled", participant_id, session_id)
        database.log_event(
            "nudge_displayed", participant_id, session_id,
            payload={"template_key": template["key"]},
            related_message_id=message["message_id"],
        )
        st.session_state["nudge_options"] = template["options"]
        st.session_state["nudge_id"] = record["nudge_id"]
    except Exception as exc:
        database.log_technical_error(
            "nudge_failed", f"maybe_show_nudge: {exc}", participant_id, session_id
        )


def render_nudge_options(participant_id: str, session_id: str) -> None:
    """답하지 않은 넛지가 있으면 선택지를 보여준다. 거절·나중에 선택지를 항상 포함한다."""
    pending = database.get_unanswered_nudge(participant_id, session_id)
    if not pending:
        return

    options = st.session_state.get("nudge_options")
    if not options:
        template = next((t for t in nudge.TEMPLATES if t["key"] == pending["template_key"]), None)
        options = template["options"] if template else None
    if not options:
        return

    columns = st.columns(len(options))
    for column, option in zip(columns, options):
        if not column.button(option, key=f"nudge_{pending['nudge_id']}_{option}"):
            continue
        try:
            database.save_message(session_id, participant_id, "user", "nudge_response", option)
            database.record_nudge_response(pending["nudge_id"], option)
            database.log_event("nudge_answered", participant_id, session_id,
                               payload={"response": option})
        except Exception as exc:
            database.log_technical_error(
                "db_insert_failed", f"nudge_response: {exc}", participant_id, session_id
            )
            st.error("응답을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return
        st.session_state.pop("nudge_options", None)
        # 넛지의 핵심 — 응답에 이어질 '작은 행동' 제안이 있으면 바로 이어서 보여준다.
        followup = nudge.get_followup(pending["template_key"], option)
        if followup:
            amsg = database.save_message(session_id, participant_id, "assistant", "nudge", followup)
            st.session_state["pending_action"] = {
                "nudge_id": pending["nudge_id"], "action": followup,
                "message_id": amsg["message_id"]}
        st.rerun()


def render_action_options(participant_id: str, session_id: str) -> None:
    """행동 제안에 대한 약속 선택지를 보여준다.

    '해볼게요'는 행동의도(action_commitment)로 기록한다 → 추후 수행 확인(Phase 3)의 출발점.
    강요하지 않는다: '조금 있다/지금은 어려워요' 선택지를 함께 준다.
    """
    pending = st.session_state.get("pending_action")
    if not pending:
        return
    columns = st.columns(len(nudge.COMMIT_OPTIONS))
    for column, option in zip(columns, nudge.COMMIT_OPTIONS):
        if not column.button(option, key=f"action_{pending['message_id']}_{option}"):
            continue
        try:
            database.save_message(session_id, participant_id, "user", "nudge_response", option)
            if option == nudge.COMMIT_OPTIONS[0]:      # '좋아요, 해볼게요' = 행동 약속
                database.set_action_commitment(pending["nudge_id"], pending["action"])
                database.log_event("action_committed", participant_id, session_id,
                                   payload={"action": pending["action"]},
                                   related_message_id=pending["message_id"])
        except Exception as exc:
            database.log_technical_error("db_insert_failed", f"action_response: {exc}",
                                         participant_id, session_id)
            st.error("응답을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return
        st.session_state.pop("pending_action", None)
        st.rerun()


def render_sources(message: dict, sources: list[dict],
                   participant_id: str, session_id: str) -> None:
    """답변 아래에 근거 출처를 접이식으로 보여준다. 출처를 열면 source_clicked를 기록한다(T2.7)."""
    with st.expander("📚 이 답변의 근거 보기"):
        for i, s in enumerate(sources):
            label = f"{s['title']} {s.get('page') or ''}쪽".strip()
            if st.button(label, key=f"src_{message['message_id']}_{i}"):
                database.log_event(
                    "source_clicked", participant_id, session_id,
                    payload={"title": s["title"], "page": s.get("page")},
                    related_message_id=message["message_id"],
                )


def run_rag(question: str, participant_id: str, session_id: str, question_message_id: str) -> None:
    """질문에 근거 기반 답변을 생성하고, 출처를 화면 상태에 담는다. 실패는 기록만 하고 넘어간다."""
    try:
        with st.spinner("근거를 찾고 있습니다…"):
            result = rag.respond(question, session_id, participant_id, question_message_id)
        st.session_state.setdefault("sources_by_msg", {})[result["answer_message_id"]] = result["sources"]
    except Exception as exc:
        database.log_technical_error("rag_failed", f"respond: {exc}", participant_id, session_id)
        st.error("답변을 만드는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")


def render_clarification_options(participant_id: str, session_id: str) -> None:
    """되묻기가 걸려 있으면 선택지를 보여준다. 선택 시 답변을 이어서 생성한다(T2.10).

    '잘 모르겠어요'는 추측 없이 일반 정보 + 의료진 권고로 간다.
    나머지는 고른 개념(혈당/당화혈색소)을 검색어에 보태 근거를 좁힌다.
    """
    pending = st.session_state.get("clarify_pending")
    if not pending:
        return
    columns = st.columns(len(pending["options"]))
    for column, option in zip(columns, pending["options"]):
        if not column.button(option, key=f"clarify_{pending['clarify_message_id']}_{option}"):
            continue
        try:
            database.save_message(session_id, participant_id, "user", "clarification_response", option)
            database.log_event("clarification_answered", participant_id, session_id,
                               payload={"term": pending["term"], "selected": option},
                               related_message_id=pending["clarify_message_id"])
        except Exception as exc:
            database.log_technical_error("db_insert_failed", f"clarify_response: {exc}",
                                         participant_id, session_id)
            st.error("응답을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return
        # 같은 세션 같은 용어는 다시 되묻지 않는다.
        st.session_state.setdefault("clarified_terms", set()).add(pending["term"])
        # 고른 개념을 검색어에 보태 답변을 생성한다.
        if "당화혈색소" in option:
            question = pending["question"] + " (당화혈색소)"
        elif "모르겠" in option:
            question = pending["question"]          # 추측 없이 일반 정보로
        else:
            question = pending["question"] + " (공복혈당 식후혈당)"
        run_rag(question, participant_id, session_id, pending["question_message_id"])
        st.session_state.pop("clarify_pending", None)
        st.rerun()


def render_chat() -> None:
    participant_id = st.session_state["participant_id"]
    session_id = st.session_state["session_id"]

    st.title("당뇨 건강 도우미")
    st.caption(f"{participant_id}님, 안녕하세요.")

    maybe_show_nudge(participant_id, session_id)

    # 화면 상태가 아니라 DB에서 대화를 불러온다 → 새로고침해도 복원된다.
    try:
        messages = database.get_messages(session_id)
    except Exception as exc:
        database.log_technical_error(
            "db_select_failed", f"get_messages: {exc}", participant_id, session_id
        )
        st.error("대화를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    sources_by_msg = st.session_state.get("sources_by_msg", {})
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            srcs = sources_by_msg.get(message.get("message_id"))
            if srcs:
                render_sources(message, srcs, participant_id, session_id)

    if not messages:
        st.info("아직 대화가 없습니다. 아래에 자유롭게 입력해 보세요.")

    render_nudge_options(participant_id, session_id)
    render_action_options(participant_id, session_id)
    render_clarification_options(participant_id, session_id)

    typed = st.chat_input("메시지를 입력하세요")
    if not typed or not typed.strip():
        return

    question = typed.strip()
    try:
        saved = database.save_message(
            session_id, participant_id, "user", "rag_question", question
        )
        database.log_event(
            "question_asked", participant_id, session_id, related_message_id=saved["message_id"]
        )
    except Exception as exc:
        database.log_technical_error(
            "db_insert_failed", f"save_message: {exc}", participant_id, session_id
        )
        st.error("메시지를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    # 용어가 모호하면(예: '혈당'이 순간값인지 당화혈색소인지) 추측하지 않고 되묻는다 (T2.10).
    clarify = rag.detect_clarification(question)
    if clarify and clarify["term"] not in st.session_state.get("clarified_terms", set()):
        cmsg = database.save_message(session_id, participant_id, "assistant",
                                     "clarification_question",
                                     "혈당이라고 하셨는데, 어떤 걸 말씀하시는 걸까요?")
        database.log_event("clarification_asked", participant_id, session_id,
                           payload={"term": clarify["term"], "options": clarify["options"],
                                    "question_message_id": saved["message_id"]},
                           related_message_id=cmsg["message_id"])
        st.session_state["clarify_pending"] = {
            "term": clarify["term"], "options": clarify["options"], "question": question,
            "question_message_id": saved["message_id"], "clarify_message_id": cmsg["message_id"]}
    else:
        run_rag(question, participant_id, session_id, saved["message_id"])

    st.rerun()


log_app_opened_once()

if "session_id" in st.session_state:
    render_chat()
else:
    render_login()
