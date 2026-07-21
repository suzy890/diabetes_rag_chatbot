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

## 관리자 대시보드 배포 (별도 앱 · PRD §8-1) — 상세 절차

연구자용 대시보드(`src/admin_app.py`)는 참여자 앱과 **같은 저장소**에서 **메인 파일만 다르게** 지정해 **두 번째 앱**으로 배포한다. 참여자 앱과는 **다른 URL**이며, 비밀번호로 보호한다.

> 핵심 차이 (참여자 앱 배포와 비교):
> - Main file path만 **`src/admin_app.py`** (참여자 앱은 `src/app.py`)
> - Secrets에 **`ADMIN_PASSWORD` 한 줄 추가** (나머지 3개는 동일)
> - 나머지(저장소·브랜치·Python 버전·requirements)는 전부 동일

**1단계. Streamlit Cloud 접속**
1. 브라우저에서 **https://share.streamlit.io** 접속
2. 우측 상단 **Sign in** → **Continue with GitHub** → (이미 참여자 앱을 배포했으므로 같은 계정으로 로그인됨)
3. 대시보드에 기존 참여자 앱이 보인다. 여기서 새 앱을 하나 더 만든다.

**2단계. 새 앱 생성**
4. 우측 상단 **"Create app"**(또는 "New app") 클릭
5. **"Deploy a public app from GitHub"** 선택
6. 입력란을 아래처럼 채운다:
   - **Repository:** `suzy890/diabates_rag_chatbot`
   - **Branch:** `main`
   - **Main file path:** `src/admin_app.py`  ← ⚠️ 여기가 참여자 앱과 유일하게 다른 부분
   - **App URL(선택):** 원하면 `...-admin` 같이 알아보기 쉬운 주소로 지정

**3단계. 시크릿(비밀정보) 입력** — ⚠️ 가장 중요
7. **"Advanced settings"** 클릭 → **Python version: 3.12** 선택
8. **Secrets** 칸에 아래 4줄을 붙여넣는다 (TOML 형식). 값은 **로컬 `.env` 파일에서 복사**한다:
   ```toml
   SUPABASE_URL = "https://fxerfhgvohppzioxcbva.supabase.co"
   SUPABASE_KEY = "여기에 .env의 SUPABASE_KEY 값"
   LLM_API_KEY  = "여기에 .env의 LLM_API_KEY 값(nvapi-...)"
   ADMIN_PASSWORD = "연구팀이 정한 관리자 비밀번호"
   ```
   > 🔒 실제 키·비밀번호는 이 문서·GitHub에 적지 않는다. `.env`에서 복사해 붙여넣는다.
   > `SUPABASE_URL`·`SUPABASE_KEY`·`LLM_API_KEY`는 **참여자 앱에 넣은 값과 동일**하다. `ADMIN_PASSWORD`만 새로 정한다(예: 연구팀이 공유하는 문구).

**4단계. 배포**
9. **Deploy!** 클릭 → 2~5분간 빌드(“Your app is in the oven”). requirements.txt는 자동 설치된다(altair·pandas는 Streamlit에 포함).
10. 완료되면 **별도 URL**이 생성된다(예: `https://xxxx-admin.streamlit.app`).

**5단계. 확인 & 공유**
11. 그 URL로 접속 → **관리자 비밀번호** 입력창이 뜬다 → `ADMIN_PASSWORD` 값 입력 → 대시보드 확인.
12. 이 **URL + 비밀번호**를 **공동연구자에게만** 공유한다. **참여자에게는 절대 공유하지 않는다.**

**이후 갱신**: `main`에 push하면 참여자 앱·관리자 앱 **둘 다 자동 재배포**된다. 코드 반영이 안 보이면 각 앱의 **Manage app → Reboot**.

> - 무료 플랜에서 완전 비공개(Private) 앱은 개수 제한이 있어, **공개 앱 + 비밀번호 게이트**(`ADMIN_PASSWORD`)로 연구자만 들어오게 한다(URL을 알아도 비밀번호 없이는 못 봄).
> - 대시보드는 **읽기 전용**이며 참여자는 익명 ID로만 표시된다(수정·삭제 기능 없음).
> - 실증(실제 참여자) 시작 전에는 접근 정책·API 키 재발급(U14)을 확정한다.

## 코드가 두 환경에서 모두 도는 이유

`src/config.py`가 접속정보를 **환경변수 → Streamlit 시크릿** 순으로 찾는다.

- 로컬: `.env` 파일 (git 제외)
- 배포: Streamlit 시크릿 (git 제외)

어느 쪽에서도 **키가 코드나 저장소에 들어가지 않는다** (CLAUDE.md 규칙).
