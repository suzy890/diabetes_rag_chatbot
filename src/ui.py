"""화면 프레젠테이션 (헤더·말풍선 등) — 그리기 전용.

원칙: 여기서는 DB·판단을 하지 않는다. app.py가 데이터를 넘겨주고, 사용자의
선택을 돌려받아 처리한다. (view ↔ controller 분리)
색·크기·문구는 코드 밖(assets/style.css)에서 조정한다.
"""

import streamlit as st


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
