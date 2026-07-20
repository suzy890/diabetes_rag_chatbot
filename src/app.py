"""화면과 사용자 흐름.

UI에서 DB·LLM을 직접 호출하지 않고 담당 모듈(database 등)을 거친다 (architecture.md 규칙).
st.session_state는 화면의 임시 상태에만 쓰고, 연구 데이터는 Supabase에 남긴다 (CLAUDE.md 규칙).
"""

from pathlib import Path

import streamlit as st

import database
import nudge
import rag
import ui

st.set_page_config(page_title="당뇨 건강 도우미", page_icon="🌿", layout="wide",
                   initial_sidebar_state="expanded")


def apply_theme() -> None:
    """고령 접근성 CSS를 주입한다 (assets/style.css — 코드 밖에서 편집 가능)."""
    css = (Path(__file__).resolve().parent.parent / "assets" / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


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


def _fail(error_type: str, detail: str, user_msg: str,
          participant_id: str | None = None, session_id: str | None = None) -> None:
    """실패를 기술 오류로 기록하고 사용자에게 안내한다 (여러 곳의 반복 처리를 한 곳에)."""
    database.log_technical_error(error_type, detail, participant_id, session_id)
    st.error(user_msg)


def _new_session(participant_id: str) -> str:
    """새 대화 세션을 만들고 session_started를 기록한 뒤 session_id를 돌려준다."""
    sid = database.create_session(participant_id)["session_id"]
    database.log_event("session_started", participant_id, sid)
    return sid


def start_session(participant_id: str) -> None:
    """가장 최근 세션을 이어받거나, 없으면 새로 만든다 (새로고침 시 중복 생성 방지)."""
    session = database.find_open_session(participant_id)
    sid = session["session_id"] if session else _new_session(participant_id)
    st.session_state["participant_id"] = participant_id
    st.session_state["session_id"] = sid


def render_login() -> None:
    typed, submitted = ui.login_form()   # 화면은 ui가 그리고, 검증은 여기서 한다
    if not submitted:
        return

    code = typed.strip().upper()
    if not code:
        st.warning("참여자 코드를 입력해 주세요.")
        return

    try:
        participant = database.get_participant(code)
    except Exception as exc:
        _fail("db_select_failed", f"get_participant: {exc}", "일시적인 오류가 생겼습니다. 잠시 후 다시 시도해 주세요.")
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
        _fail("db_insert_failed", f"start_session: {exc}", "접속을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", code)
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
        database.create_nudge(
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
    except Exception as exc:
        database.log_technical_error(
            "nudge_failed", f"maybe_show_nudge: {exc}", participant_id, session_id
        )


def _pick(options: list[str], key_prefix: str,
          participant_id: str, session_id: str, message_type: str) -> str | None:
    """선택지 버튼을 그려 클릭된 값을 돌려주고, 그 응답을 사용자 메시지로 저장한다.

    아무것도 안 눌렀으면 None. 저장에 실패하면 오류를 알리고 None을 돌려준다(호출부가 멈춤).
    넛지·행동제안·되묻기가 공유하는 '버튼 한 줄 + 응답 저장' 패턴을 한 곳에 모은다.
    """
    for column, option in zip(st.columns(len(options)), options):
        if not column.button(option, key=f"{key_prefix}_{option}"):
            continue
        try:
            database.save_message(session_id, participant_id, "user", message_type, option)
            return option
        except Exception as exc:
            _fail("db_insert_failed", f"{key_prefix}: {exc}", "응답을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", participant_id, session_id)
            return None
    return None


def render_nudge_options(participant_id: str, session_id: str) -> None:
    """답하지 않은 넛지가 있으면 선택지를 보여준다. 응답하면 이어서 행동 제안을 띄운다."""
    pending = database.get_unanswered_nudge(participant_id, session_id)
    if not pending:
        return
    template = next((t for t in nudge.TEMPLATES if t["key"] == pending["template_key"]), None)
    if not template:
        return
    option = _pick(template["options"], f"nudge_{pending['nudge_id']}", participant_id, session_id, "nudge_response")
    if not option:
        return
    database.record_nudge_response(pending["nudge_id"], option)
    database.log_event("nudge_answered", participant_id, session_id, payload={"response": option})
    # 넛지의 핵심 — 응답에 이어질 '작은 행동' 제안이 있으면 바로 이어서 보여준다.
    followup = nudge.get_followup(pending["template_key"], option)
    if followup:
        amsg = database.save_message(session_id, participant_id, "assistant", "nudge", followup)
        st.session_state["pending_action"] = {
            "nudge_id": pending["nudge_id"], "action": followup, "message_id": amsg["message_id"]}
    st.rerun()


def render_action_options(participant_id: str, session_id: str) -> None:
    """행동 제안에 대한 약속 선택지. '해볼게요'는 행동의도로 기록(Phase 3 출발점). 강요하지 않는다."""
    pending = st.session_state.get("pending_action")
    if not pending:
        return
    option = _pick(nudge.COMMIT_OPTIONS, f"action_{pending['message_id']}",
                   participant_id, session_id, "nudge_response")
    if not option:
        return
    committed = option == nudge.COMMIT_OPTIONS[0]      # '좋아요, 해볼게요' = 행동 약속
    if committed:
        database.set_action_commitment(pending["nudge_id"], pending["action"])
        database.log_event("action_committed", participant_id, session_id,
                           payload={"action": pending["action"]},
                           related_message_id=pending["message_id"])
    # 약속/거절 뒤에 격려 + 질문 유도 피드백을 남긴다 (대화가 어색하게 끝나지 않도록).
    database.save_message(session_id, participant_id, "assistant", "nudge",
                          nudge.get_commit_feedback(committed))
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
    """근거를 찾아(스피너) 답변을 실시간으로 흘려보이고(스트리밍), 끝나면 저장한다."""
    try:
        with st.spinner("근거를 찾고 있어요… 📚 당뇨 안내 자료를 확인 중입니다"):
            r = rag.retrieve(question, session_id, participant_id, question_message_id)
        titles = {d["document_id"]: d["title"] for d in database.list_documents()}
        selected = [{**c, "title": titles.get(c["document_id"], "문서")} for c in r["selected"]]
        # 근거 부족(보류·무관질문 안내 포함)도 answer_stream이 처리한다 → 분기 일원화.
        sysver = database.get_active_system_version_id()
        answer = ui.stream_assistant(rag.answer_stream(
            question, selected, r["evidence_level"], participant_id, question_message_id, sysver))
        msg = database.save_message(session_id, participant_id, "assistant", "rag_answer", answer)
        database.update_retrieval_answer(r["retrieval_id"], msg["message_id"])
        sources = [{"title": c["title"], "page": c.get("page_number")} for c in selected]
        st.session_state.setdefault("sources_by_msg", {})[msg["message_id"]] = sources
    except Exception as exc:
        _fail("rag_failed", f"stream: {exc}", "답변을 만드는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.", participant_id, session_id)


def render_clarification_options(participant_id: str, session_id: str) -> None:
    """되묻기가 걸려 있으면 선택지를 보여준다. 선택 시 답변을 이어서 생성한다(T2.10).

    '잘 모르겠어요'는 추측 없이 일반 정보 + 의료진 권고로 간다.
    나머지는 고른 개념(혈당/당화혈색소)을 검색어에 보태 근거를 좁힌다.
    """
    pending = st.session_state.get("clarify_pending")
    if not pending:
        return
    option = _pick(pending["options"], f"clarify_{pending['clarify_message_id']}",
                   participant_id, session_id, "clarification_response")
    if not option:
        return
    database.log_event("clarification_answered", participant_id, session_id,
                       payload={"term": pending["term"], "selected": option},
                       related_message_id=pending["clarify_message_id"])
    st.session_state.setdefault("clarified_terms", set()).add(pending["term"])  # 세션당 같은 용어 1회
    # 고른 개념을 검색어에 보태 답변을 생성한다. '모르겠어요'는 추측 없이 일반 정보로.
    if "당화혈색소" in option:
        question = pending["question"] + " (당화혈색소)"
    elif "모르겠" in option:
        question = pending["question"]
    else:
        question = pending["question"] + " (공복혈당 식후혈당)"
    run_rag(question, participant_id, session_id, pending["question_message_id"])
    st.session_state.pop("clarify_pending", None)
    st.rerun()


def render_chat() -> None:
    participant_id = st.session_state["participant_id"]
    session_id = st.session_state["session_id"]

    action = ui.header()          # 헤더를 그리고 눌린 동작을 돌려받는다
    if action == "size":
        st.session_state["large_text"] = not st.session_state.get("large_text", False)
        st.rerun()
    if action == "exit":
        for key in ("participant_id", "session_id", "nudge_checked", "clarified_terms",
                    "sources_by_msg", "pending_action", "clarify_pending"):
            st.session_state.pop(key, None)
        st.rerun()
    if st.session_state.get("large_text"):
        ui.apply_large_text()

    # 왼쪽 사이드바: 지난 대화 이어보기 / 새 대화 시작 (히스토리 지속, D45)
    picked = ui.sidebar_history(database.list_sessions(participant_id), session_id)
    if picked == "new":
        picked = _new_session(participant_id)
    if picked:
        for key in ("pending_action", "clarify_pending"):
            st.session_state.pop(key, None)
        st.session_state["session_id"] = picked
        st.rerun()

    today_col, chat_col = st.columns([0.31, 0.69], gap="large")
    with today_col:
        with st.container(key="today_card"):
            ui.today_card()

    with chat_col:
        with st.container(key="conversation"):
            ui.conversation_top()
            maybe_show_nudge(participant_id, session_id)
            # 화면 상태가 아니라 DB에서 대화를 불러온다 → 새로고침해도 복원된다.
            try:
                messages = database.get_messages(session_id)
            except Exception as exc:
                _fail("db_select_failed", f"get_messages: {exc}", "대화를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", participant_id, session_id)
                return
            sources_by_msg = st.session_state.get("sources_by_msg", {})
            for message in messages:
                avatar = ui.USER_AVATAR if message["role"] == "user" else ui.BOT_AVATAR
                with st.chat_message(message["role"], avatar=avatar):
                    st.write(message["content"])
                    srcs = sources_by_msg.get(message.get("message_id"))
                    if srcs:
                        render_sources(message, srcs, participant_id, session_id)

            render_nudge_options(participant_id, session_id)
            render_action_options(participant_id, session_id)
            render_clarification_options(participant_id, session_id)

            # 사용자가 아직 질문을 안 했으면 추천 질문을 제시한다. (넛지가 항상 메시지로
            # 먼저 저장돼 messages는 늘 비어있지 않으므로, '메시지 유무'가 아니라 '질문 유무'로 판단)
            asked = any(m["role"] == "user" and m.get("message_type") == "rag_question"
                        for m in messages)
            if not asked:
                picked = ui.quick_questions()
                if picked:
                    handle_question(picked, participant_id, session_id, source="suggested")
                    st.rerun()
            typed = st.chat_input("건강에 관해 궁금한 점을 편하게 물어보세요")
            if typed and typed.strip():
                handle_question(typed.strip(), participant_id, session_id, source="typed")
                st.rerun()
            ui.medical_note()
            st.caption(f"build: sidebar-v4 · 지난 대화 {len(database.list_sessions(participant_id))}개")  # 배포 확인용(임시)


def handle_question(question: str, participant_id: str, session_id: str,
                    source: str = "typed") -> None:
    """사용자 질문 하나를 처리한다 (입력창·추천질문 공용). 화면 갱신은 호출부가 한다.

    잡담이면 따뜻한 응답, 아니면 질문 저장 → (모호하면 되묻기 / 아니면 근거 기반 답변).
    source: 'typed'(직접 입력) / 'suggested'(추천 질문 클릭) — 연구 분석에서 자발적 질문만
    따로 보기 위해 기록한다.
    """
    social = rag.detect_social(question)
    if social:
        try:
            database.save_message(session_id, participant_id, "user", "free_text", question)
            database.save_message(session_id, participant_id, "assistant", "system_notice", social)
        except Exception as exc:
            database.log_technical_error("db_insert_failed", f"social: {exc}",
                                         participant_id, session_id)
        return
    try:
        saved = database.save_message(session_id, participant_id, "user", "rag_question", question)
        database.log_event("question_asked", participant_id, session_id,
                           payload={"source": source}, related_message_id=saved["message_id"])
    except Exception as exc:
        _fail("db_insert_failed", f"save_message: {exc}", "메시지를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", participant_id, session_id)
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
        ui.show_user(question)   # 질문을 즉시 보여준 뒤 답변을 스트리밍한다
        run_rag(question, participant_id, session_id, saved["message_id"])


apply_theme()
log_app_opened_once()

if "session_id" in st.session_state:
    render_chat()
else:
    render_login()
