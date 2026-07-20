"""화면 프레젠테이션 (헤더·말풍선 등) — 그리기 전용.

원칙: 여기서는 DB·판단을 하지 않는다. app.py가 데이터를 넘겨주고, 사용자의
선택을 돌려받아 처리한다. (view ↔ controller 분리)
색·크기·문구는 코드 밖(assets/style.css)에서 조정한다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

USER_AVATAR = "🙂"
BOT_AVATAR = "🌿"

# 첫 화면 추천 질문(문장형, 입력창 위 보조). 적고 일반적으로 유지(연구 관측 오염 방지).
QUICK_QUESTIONS = [
    "식후 혈당은 언제 재나요?",
    "오늘은 어떤 운동이 좋을까요?",
    "저녁 식사 양이 고민돼요",
]


def brand(compact: bool = False) -> None:
    """서비스 브랜드 마크 '당 / 당뇨 건강 도우미'."""
    cls = " compact" if compact else ""
    st.markdown(
        f'<div class="brand{cls}"><span class="brand-mark">당</span><span>당뇨 건강 도우미</span></div>',
        unsafe_allow_html=True)


def login_decor() -> None:
    """로그인 화면 배경 장식 + 브랜드."""
    st.markdown('<div class="login-ambient login-ambient-one"></div>'
                '<div class="login-ambient login-ambient-two"></div>', unsafe_allow_html=True)
    brand()


def login_welcome() -> None:
    """로그인 왼쪽 환영 패널 (서비스 소개)."""
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
        unsafe_allow_html=True)


def login_card_intro() -> None:
    """로그인 카드 상단 인사·안내 문구."""
    st.markdown('<div class="hello-badge">안녕하세요!</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="login-heading"><h2>참여자 코드를 입력해 주세요</h2>'
        '<p>연구자에게 안내받은 코드를 입력하면<br>바로 시작할 수 있어요.</p></div>',
        unsafe_allow_html=True)


def login_privacy() -> None:
    st.markdown('<div class="privacy-note">🔒 &nbsp;이름이나 전화번호는 저장하지 않아요.</div>',
                unsafe_allow_html=True)


def login_footer() -> None:
    st.markdown('<div class="simple-footer">도움이 필요하신가요? <u>연구자에게 문의하기</u></div>',
                unsafe_allow_html=True)


def login_form() -> tuple[str, bool]:
    """로그인 화면 전체를 그리고 (입력 코드, 제출됨)을 돌려준다. 검증은 app이 한다(DB는 안 만짐)."""
    login_decor()
    st.markdown('<div class="login-spacer"></div>', unsafe_allow_html=True)
    welcome_col, form_col = st.columns([1.08, 0.92], gap="large", vertical_alignment="center")
    with welcome_col:
        login_welcome()
    code, submitted = "", False
    with form_col:
        with st.container(key="login_card"):
            login_card_intro()
            with st.form("login_form", border=False):
                code = st.text_input("참여자 코드", placeholder="예: P001",
                                     help="영문과 숫자를 안내받은 그대로 입력해 주세요.")
                submitted = st.form_submit_button("건강 대화 시작하기  →",
                                                  use_container_width=True, type="primary")
            login_privacy()
    login_footer()
    return code, submitted


def header() -> str | None:
    """상단 헤더(브랜드·글자크게·나가기)를 그리고, 눌린 동작('size'|'exit')을 돌려준다."""
    brand_col, _spacer, size_col, exit_col = st.columns([3, 5, 1.35, 1], vertical_alignment="center")
    with brand_col:
        brand(compact=True)
    with size_col:
        big = st.session_state.get("large_text", False)   # 켜짐/꺼짐을 라벨로 알려준다
        clicked_size = st.button("가⁻  글자 작게" if big else "가⁺  글자 크게",
                                 key="text_size", use_container_width=True)
    with exit_col:
        clicked_exit = st.button("나가기", key="logout", use_container_width=True)
    st.markdown('<div class="header-rule"></div>', unsafe_allow_html=True)
    return "size" if clicked_size else "exit" if clicked_exit else None


def apply_large_text() -> None:
    """'글자 크게'가 켜졌을 때 화면 전반의 글씨를 크게 키운다(고령 접근성). 말풍선만이 아니라
    버튼·입력창·사이드바·추천질문까지 함께 키워야 실제로 커진 게 체감된다."""
    st.markdown(
        "<style>"
        "[data-testid='stChatMessageContent'], [data-testid='stChatMessageContent'] *"
        "{font-size:23px!important;line-height:1.75!important}"
        "[data-testid='stChatInput'] textarea{font-size:21px!important}"
        "[class*='st-key-'] button, .stButton button, [data-testid='stSidebar'] button"
        "{font-size:19px!important}"
        ".quick-label, .medical-note, .st-key-today_card p, .st-key-today_card h2"
        "{font-size:18px!important}"
        "</style>",
        unsafe_allow_html=True)


def today_card() -> None:
    """대화 옆 '오늘' 카드 (날짜·인사·팁). 데스크톱에서만 보임. 진행바는 두지 않는다(실데이터 없음)."""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = f"{now.month}월 {now.day}일 · {'월화수목금토일'[now.weekday()]}요일"
    greet = "좋은 아침이에요!" if now.hour < 11 else "좋은 오후예요!" if now.hour < 18 else "좋은 저녁이에요!"
    st.markdown(
        f'<div class="date-chip">{date_str}</div>'
        f'<h2>{greet}</h2>'
        f'<p>오늘도 무리하지 말고,<br>할 수 있는 만큼 함께해요.</p>'
        f'<div class="side-tip"><span>☀</span><p><strong>작은 팁</strong>'
        f'완벽하게 하려 하기보다 한 가지부터 시작해 보세요.</p></div>',
        unsafe_allow_html=True)


def conversation_top() -> None:
    """대화 영역 상단 상태 바."""
    st.markdown(
        '<div class="conversation-top"><span class="online-dot"></span>'
        '<strong>건강 도우미</strong><span>지금 대화할 수 있어요</span></div>'
        '<div class="day-divider"><span>오늘</span></div>',
        unsafe_allow_html=True)


def medical_note() -> None:
    st.markdown('<div class="medical-note">건강 정보는 참고용이며, 진단이나 처방은 '
                '의료진과 상담해 주세요.</div>', unsafe_allow_html=True)


def show_user(text: str) -> None:
    """사용자 메시지를 즉시 화면에 보여준다 (전송 직후 바로 보이도록)."""
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(text)


def show_assistant(text: str) -> None:
    """AI 메시지를 한 번에 보여준다 (근거 부족 안내 등 스트리밍 아닌 경우)."""
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.write(text)


def stream_assistant(token_generator) -> str:
    """AI 답변을 실시간으로 흘려보내며 보여준다. 완성된 전체 텍스트를 돌려준다."""
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        return st.write_stream(token_generator)


def _session_label(session: dict, current: bool) -> str:
    """지난 대화 라벨: 첫 질문(있으면)으로, 없으면 날짜로 (ChatGPT식 목록, D45)."""
    preview = (session.get("preview") or "").strip()
    if preview:
        text = preview[:22] + ("…" if len(preview) > 22 else "")
    else:
        raw = (session.get("started_at") or "").replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw).astimezone(ZoneInfo("Asia/Seoul"))
            text = f"{dt.month}월 {dt.day}일 대화"
        except ValueError:
            text = "지난 대화"
    return ("🟢 " if current else "🗨 ") + text


def sidebar_history(sessions: list[dict], current_id: str) -> str | None:
    """왼쪽 사이드바: '새 대화' 버튼 + 지난 대화 목록(최근 순). 과거 대화가 사라지지 않게(D45).

    누른 동작을 돌려준다 — "new"(새 대화 시작) | session_id(그 대화로 전환) | None.
    """
    sb = st.sidebar
    sb.markdown("### 💬 내 대화")
    if sb.button("＋ 새 대화 시작", key="new_chat", type="primary"):
        return "new"
    if not sessions:
        sb.caption("아직 지난 대화가 없어요.")
    for s in sessions:
        if sb.button(_session_label(s, s["session_id"] == current_id), key=f"sess_{s['session_id']}"):
            return s["session_id"]
    return None


def quick_questions() -> str | None:
    """추천 질문(문장형)을 입력창 위에 보여주고, 누른 질문을 돌려준다(없으면 None)."""
    st.markdown('<div class="quick-label">이런 질문을 해보세요</div>', unsafe_allow_html=True)
    for column, question in zip(st.columns(len(QUICK_QUESTIONS)), QUICK_QUESTIONS):
        if column.button(question, key=f"quick_{question}", use_container_width=True):
            return question
    return None
