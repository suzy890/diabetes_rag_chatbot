"""화면 프레젠테이션 (헤더·추천 질문 카드·말풍선 등) — 그리기 전용.

원칙: 여기서는 DB·판단을 하지 않는다. app.py가 데이터를 넘겨주고, 사용자의
선택(누른 카드의 질문 등)을 돌려받아 처리한다. (view ↔ controller 분리)
문구·카드는 코드 밖 데이터/CSS에서 조정 가능. 색·크기는 assets/style.css.
"""

import json
from pathlib import Path

import streamlit as st

_CARDS = json.loads((Path(__file__).resolve().parent.parent
                     / "prompts" / "question_cards.json").read_text(encoding="utf-8"))["cards"]


def greeting(display_name: str) -> None:
    """개인화 인사 헤더. 이름은 실명이 아니라 호칭이며 화면에만 쓴다(외부 전송 안 함)."""
    st.markdown(
        f"<div class='dh-header'>"
        f"<div class='dh-hello'>안녕하세요, {display_name}님 😊</div>"
        f"<div class='dh-sub'>오늘도 건강을 함께 관리해요 · 항상 근거에 기반해 답해드려요</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def question_cards() -> str | None:
    """추천 질문 카드를 보여주고, 누른 카드의 질문을 돌려준다(없으면 None).

    고령 사용자가 '무엇을 물어봐야 하지?'에서 막히지 않도록 첫 질문을 쉽게 열어준다.
    """
    st.markdown("<div class='dh-cards-title'>💬 무엇이든 편하게 물어보세요</div>",
                unsafe_allow_html=True)
    columns = st.columns(len(_CARDS))
    for column, card in zip(columns, _CARDS):
        if column.button(f"{card['emoji']}\n{card['label']}",
                         key=f"card_{card['label']}", use_container_width=True):
            return card["question"]
    return None
