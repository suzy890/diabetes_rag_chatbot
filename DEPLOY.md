# DEPLOY.md — 배포 안내

> **문서 버전:** v0.1 · **작성 기준일:** 2026-07-13
> 공동연구자에게 진행 상황을 보여주기 위한 **데모 배포** 안내.
> ⚠️ **이것은 실증(실제 참여자)용 배포가 아니다.** 실증용 배포환경은 미결정(U11)이며 접근 제한·백업을 별도로 정해야 한다.

---

## 배포 방식: Streamlit Community Cloud (무료)

| 항목 | 값 |
|------|-----|
| 저장소 | `suzy890/diabates_rag_chatbot` |
| 브랜치 | `main` |
| **Main file path** | **`src/app.py`** |
| Python 버전 | **3.12** |
| 비용 | 무료 |

GitHub에 push하면 **자동으로 재배포**된다. → 진행할 때마다 팀원이 최신 화면을 볼 수 있다.

## 배포 절차 (연구자가 직접 — 1회만)

1. **https://share.streamlit.io** 접속 → **GitHub 계정으로 로그인**
2. **"Create app"** (또는 New app) 클릭
3. 아래를 선택/입력
   - Repository: `suzy890/diabates_rag_chatbot`
   - Branch: `main`
   - **Main file path: `src/app.py`** ← 중요 (기본값 `streamlit_app.py` 아님)
   - Advanced settings → **Python version: 3.12**
4. **Advanced settings → Secrets** 에 아래를 붙여넣기 (TOML 형식)

   ```toml
   SUPABASE_URL = "https://fxerfhgvohppzioxcbva.supabase.co"
   SUPABASE_KEY = "여기에 .env의 SUPABASE_KEY 값을 붙여넣기"
   LLM_API_KEY = "여기에 .env의 LLM_API_KEY 값(nvapi-...)을 붙여넣기"
   ```

   > 🔒 실제 키는 이 문서에 적지 않는다. 로컬 `.env` 파일에서 복사해 붙여넣는다.
   > Streamlit 시크릿은 GitHub에 올라가지 않는다.
   > ⚠️ **`LLM_API_KEY`는 Phase 2(RAG)부터 필요**하다. 이 키가 없으면 질문 답변이 실패한다.
   > (RAG 답변·임베딩은 NVIDIA API를 호출하므로 — [llm-provider](.claude/rules/) 참고)

5. **Deploy** 클릭 → 몇 분 뒤 URL 생성

## ⚠️ 접근 제한 (반드시 확인)

기본 설정은 **URL을 아는 누구나 접속 가능**하다. 그러면 외부인이 `P001`을 입력해 **가짜 연구 데이터를 만들 수** 있다.

- 앱 설정에서 **비공개(Private)** 로 바꾸고, **공동연구자 이메일만 허용**한다.
- 공개로 둘 경우: 데모 목적으로만 쓰고, **실제 참여자 데이터를 절대 넣지 않는다.**
- 실증 시작 전에는 **반드시** 접근 제한 방식을 확정한다(U11).

## 현재 데모에 들어있는 것

- 테스트 참여자 `P001`(active) · `P002`(active) · `P003`(scheduled — 진입 차단됨)
- 실제 참여자 데이터 **없음**
- 기능: 참여자 코드 입력 → 세션 생성 → 시간대별 식사 넛지 → 응답 저장 → 자유 메시지 저장
- **아직 없음:** RAG 답변(Phase 2), 행동 수행 확인(Phase 3)

## 코드가 두 환경에서 모두 도는 이유

`src/config.py`가 접속정보를 **환경변수 → Streamlit 시크릿** 순으로 찾는다.

- 로컬: `.env` 파일 (git 제외)
- 배포: Streamlit 시크릿 (git 제외)

어느 쪽에서도 **키가 코드나 저장소에 들어가지 않는다** (CLAUDE.md 규칙).
