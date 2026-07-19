# 오늘도 건강 — Streamlit UI 적용 안내

## 실행

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 기존 기능 연결 지점

`streamlit_app.py`에는 `INTEGRATION:` 주석으로 세 곳을 표시해 두었습니다.

1. **참여자 확인** — `login()`의 제출 처리에서 기존 참여자 조회 함수를 호출합니다.
2. **RAG 답변** — `add_demo_answer()`의 고정 답변을 기존 검색·생성 함수 결과로 교체합니다.
3. **연구 이벤트 기록** — 채팅 입력과 넛지 버튼 처리에서 기존 Supabase 저장 함수를 호출합니다.

화면 전환 상태는 `st.session_state.authenticated`, 대화 내역은
`st.session_state.messages`를 사용합니다. 기존 프로젝트에서 이미 같은 키를
사용한다면 키 이름만 맞춰 변경하면 됩니다.

## 파일 구성

- `streamlit_app.py`: 로그인·채팅 화면 및 데모 상호작용
- `streamlit_styles.css`: 파스텔 디자인과 반응형·고령친화 스타일
- `.streamlit/config.toml`: 앱 테마 기본값
- `requirements.txt`: Streamlit 의존성

CSS는 Streamlit의 내부 DOM 구조 일부를 대상으로 합니다. Streamlit 메이저 버전을
올릴 때에는 로그인 입력창, 채팅 말풍선, 버튼 스타일을 한 번 확인하는 것이 좋습니다.
