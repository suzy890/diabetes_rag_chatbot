"""화면 프레젠테이션 (헤더·말풍선 등) — 그리기 전용.

원칙: 여기서는 DB·판단을 하지 않는다. app.py가 데이터를 넘겨주고, 사용자의
선택을 돌려받아 처리한다. (view ↔ controller 분리)
색·크기·문구는 코드 밖(assets/style.css)에서 조정한다.
"""

import streamlit as st


def brand(compact: bool = False) -> None:
    """서비스 브랜드 마크 '온 / 오늘도 건강'."""
    cls = " compact" if compact else ""
    st.markdown(
        f'<div class="brand{cls}"><span class="brand-mark">온</span><span>오늘도 건강</span></div>',
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


def greeting(display_name: str) -> None:
    """개인화 인사 헤더. 이름은 실명이 아니라 호칭이며 화면에만 쓴다(외부 전송 안 함).

    인지부하를 줄이고 '믿을 수 있는 건강도우미' 느낌을 주는 용도. 질문을 유도하거나
    쥐여주지 않는다(참여자가 스스로 무엇을 묻는지가 연구 관측 대상이므로).
    """
    st.markdown(
        f"<div class='dh-header'>"
        f"<div class='dh-hello'>안녕하세요, {display_name}님 😊</div>"
        f"<div class='dh-sub'>오늘도 건강을 함께 관리해요 · 항상 근거에 기반해 답해드려요</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def show_user(text: str) -> None:
    """사용자 메시지를 즉시 화면에 보여준다 (전송 직후 바로 보이도록)."""
    with st.chat_message("user"):
        st.write(text)


def show_assistant(text: str) -> None:
    """AI 메시지를 한 번에 보여준다 (근거 부족 안내 등 스트리밍 아닌 경우)."""
    with st.chat_message("assistant"):
        st.write(text)


def stream_assistant(token_generator) -> str:
    """AI 답변을 실시간으로 흘려보내며 보여준다. 완성된 전체 텍스트를 돌려준다."""
    with st.chat_message("assistant"):
        return st.write_stream(token_generator)
