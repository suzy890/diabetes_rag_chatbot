"""오늘도 건강 — Streamlit UI prototype.

Replace the marked demo callbacks with the project's existing login, RAG, and
event logging functions. The UI and session-state flow are intentionally kept
independent from those integrations.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent

st.set_page_config(
    page_title="오늘도 건강",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_css() -> None:
    st.markdown(
        f"<style>{(APP_DIR / 'streamlit_styles.css').read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True,
    )


def init_state() -> None:
    defaults = {
        "authenticated": False,
        "participant_code": "",
        "messages": [],
        "nudge_answered": False,
        "large_text": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def brand(compact: bool = False) -> None:
    compact_class = " compact" if compact else ""
    st.markdown(
        f"""
        <div class="brand{compact_class}" aria-label="오늘도 건강">
            <span class="brand-mark">온</span>
            <span>오늘도 건강</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def login() -> None:
    st.markdown('<div class="login-ambient login-ambient-one"></div>', unsafe_allow_html=True)
    st.markdown('<div class="login-ambient login-ambient-two"></div>', unsafe_allow_html=True)
    brand()

    st.markdown('<div class="login-spacer"></div>', unsafe_allow_html=True)
    welcome_col, form_col = st.columns([1.08, 0.92], gap="large", vertical_alignment="center")

    with welcome_col:
        st.markdown(
            """
            <section class="welcome-panel">
                <span class="eyebrow">매일 곁에 있는 건강 친구</span>
                <h1>작은 실천이<br>건강한 오늘을 만들어요</h1>
                <p>식사, 운동, 혈당 관리가 궁금할 때<br>쉽고 편안하게 이야기해 보세요.</p>
                <div class="benefit-list">
                    <div class="benefit"><span class="benefit-icon mint">✓</span><span>신뢰할 수 있는 건강 정보</span></div>
                    <div class="benefit"><span class="benefit-icon peach">♥</span><span>부담 없이 시작하는 작은 실천</span></div>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    with form_col:
        with st.container(key="login_card"):
            st.markdown('<div class="hello-badge">안녕하세요!</div>', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="login-heading">
                    <h2>참여자 코드를 입력해 주세요</h2>
                    <p>연구자에게 안내받은 코드를 입력하면<br>바로 시작할 수 있어요.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("login_form", border=False):
                code = st.text_input(
                    "참여자 코드",
                    placeholder="예: HAPPY1234",
                    help="영문과 숫자를 안내받은 그대로 입력해 주세요.",
                    autocomplete="off",
                )
                submitted = st.form_submit_button(
                    "건강 대화 시작하기  →",
                    use_container_width=True,
                    type="primary",
                )
                if submitted:
                    if code.strip():
                        # INTEGRATION: replace with the existing participant lookup.
                        st.session_state.participant_code = code.strip()
                        st.session_state.authenticated = True
                        st.rerun()
                    else:
                        st.error("참여자 코드를 입력해 주세요.")

            st.markdown(
                '<div class="privacy-note">🔒 &nbsp;이름이나 전화번호는 저장하지 않아요.</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="simple-footer">도움이 필요하신가요? <u>연구자에게 문의하기</u></div>',
        unsafe_allow_html=True,
    )


def add_demo_answer(question: str) -> None:
    """Demo response; replace with the project's RAG call."""
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": (
                "좋은 질문이에요. 식후 혈당은 보통 식사를 시작한 때부터 "
                "2시간 뒤에 확인해요. 의료진이 따로 안내한 시간이 있다면 "
                "그 안내를 따라주세요."
            ),
            "source": "대한당뇨병학회 · 당뇨병 진료지침 2025",
        }
    )


def render_nudge() -> None:
    with st.chat_message("assistant", avatar="🌿"):
        st.markdown(
            """
            <div class="nudge-copy">
                <p>안녕하세요! 점심 식사는 맛있게 하셨나요?</p>
                <p>식사 후 <strong>10분만 가볍게 걷기</strong>를 해보는 건 어떠세요?</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not st.session_state.nudge_answered:
            yes_col, done_col, later_col = st.columns(3, gap="small")
            with yes_col:
                if st.button("네, 해볼게요", use_container_width=True, key="nudge_yes"):
                    st.session_state.nudge_answered = "네, 해볼게요"
                    st.rerun()
            with done_col:
                if st.button("이미 했어요", use_container_width=True, key="nudge_done"):
                    st.session_state.nudge_answered = "이미 했어요"
                    st.rerun()
            with later_col:
                if st.button("지금은 어려워요", use_container_width=True, key="nudge_later"):
                    st.session_state.nudge_answered = "지금은 어려워요"
                    st.rerun()
        else:
            st.markdown(
                f'<div class="nudge-confirm">✓ “{escape(str(st.session_state.nudge_answered))}”로 기록했어요.</div>',
                unsafe_allow_html=True,
            )
        st.caption("오후 1:20")


def render_today_card() -> None:
    with st.container(key="today_card"):
        st.markdown(
            """
            <div class="date-chip">7월 19일 · 일요일</div>
            <h2>좋은 오후예요!</h2>
            <p>오늘도 무리하지 말고,<br>할 수 있는 만큼 함께해요.</p>
            <div class="daily-progress">
                <div class="progress-heading"><span>오늘의 실천</span><strong>1 / 3</strong></div>
                <div class="progress-track"><span></span></div>
            </div>
            <div class="side-tip">
                <span>☀</span>
                <p><strong>작은 팁</strong>완벽하게 하려 하기보다 한 가지부터 시작해 보세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def chat() -> None:
    header_brand, header_space, size_col, exit_col = st.columns([3, 5, 1.35, 1], vertical_alignment="center")
    with header_brand:
        brand(compact=True)
    with size_col:
        if st.button("가⁺  글자 크게", key="text_size", use_container_width=True):
            st.session_state.large_text = not st.session_state.large_text
            st.rerun()
    with exit_col:
        if st.button("나가기", key="logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.messages = []
            st.rerun()

    if st.session_state.large_text:
        st.markdown("<style>html, body, [class*='css'] {font-size: 1.075em !important}.stChatMessage p{font-size:20px!important}</style>", unsafe_allow_html=True)

    st.markdown('<div class="header-rule"></div>', unsafe_allow_html=True)
    today_col, chat_col = st.columns([0.31, 0.69], gap="large")

    with today_col:
        render_today_card()

    with chat_col:
        with st.container(key="conversation"):
            st.markdown(
                """
                <div class="conversation-top">
                    <span class="online-dot"></span>
                    <strong>건강 도우미</strong>
                    <span>지금 대화할 수 있어요</span>
                </div>
                <div class="day-divider"><span>오늘</span></div>
                """,
                unsafe_allow_html=True,
            )
            render_nudge()

            for message in st.session_state.messages:
                avatar = "🙂" if message["role"] == "user" else "🌿"
                with st.chat_message(message["role"], avatar=avatar):
                    st.write(message["content"])
                    if source := message.get("source"):
                        with st.expander("▤  근거 출처 확인하기"):
                            st.caption(source)

            if not st.session_state.messages:
                st.markdown('<div class="quick-label">이런 질문을 해보세요</div>', unsafe_allow_html=True)
                quick_questions = [
                    "식후 혈당은 언제 재나요?",
                    "오늘은 어떤 운동이 좋을까요?",
                    "저녁 식사 양이 고민돼요",
                ]
                quick_cols = st.columns(3, gap="small")
                for index, (column, question) in enumerate(zip(quick_cols, quick_questions)):
                    with column:
                        if st.button(question, key=f"quick_{index}", use_container_width=True):
                            add_demo_answer(question)
                            st.rerun()

            prompt = st.chat_input("건강에 관해 궁금한 점을 편하게 물어보세요")
            if prompt:
                # INTEGRATION: log the question and call the existing RAG pipeline here.
                add_demo_answer(prompt)
                st.rerun()

            st.markdown(
                '<div class="medical-note">건강 정보는 참고용이며, 진단이나 처방은 의료진과 상담해 주세요.</div>',
                unsafe_allow_html=True,
            )


load_css()
init_state()

if st.session_state.authenticated:
    chat()
else:
    login()
