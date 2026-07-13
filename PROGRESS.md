# PROGRESS.md — 현재 진행 상태

> **문서 버전:** v0.2 · **갱신일:** 2026-07-13
> **현재 단계: Phase 1 완료 · 데모 배포 완료 → 다음은 Phase 2 (RAG)**

---

## 완료 ✅

### Phase 0 — 설계·규칙 고정 (1주차)
- 프로젝트 문서: README · PRD · CLAUDE + `.claude/rules/`(architecture·research-data·medical-safety)
- 데이터 스키마 (DATA_SCHEMA — 14개 테이블) + **수집 우선 원칙**
- 이벤트 사전 (EVENT_DICTIONARY — 13개 이벤트)
- 넛지·RAG·안전 규칙 (NUDGE_RULES · RAG_RULES · SAFETY_RULES)
- 백로그·의사결정·비용·분석목표 (TASKS · DECISIONS · COST_PLAN · analysis-targets)
- 문서 일관성 검수 통과

### Phase 1 — 웹앱·DB 골격 (2주차)
- **개발환경:** Python 3.12 · venv · requirements 고정 (streamlit · supabase · python-dotenv · watchdog)
- **Supabase 연결:** 프로젝트 `diabetes_rag_chatbot` (서울 리전) · `config.py`/`database.py`
- **스키마 생성 (7개 테이블):** system_versions · participants · sessions · events · messages · nudge_events · technical_errors
  - 전 테이블 **RLS 활성화(정책 0개)** → 외부 접근 차단, 앱 서버만 기록
  - `events`·`messages`에 **복합 FK**로 참여자·세션 일관성을 DB가 원천 보장
- **T1.1** 참여자 코드 입력 · 확인 · 세션 생성 (새로고침 중복 방지)
- **T1.3** 기본 채팅 화면 (메시지 저장 · DB에서 복원 · 중복 저장 없음)
- **T1.4** 접속 시간대 넛지 — **AI가 먼저 말을 검** (승인 템플릿 v0.1 5종 · 하루 3회 상한)
- **테스트:** T1.1 8건 · T1.3 7건 · T1.4 10건 전부 통과 + 실제 DB 데이터로 교차 검증
- **핵심 코드 404줄 / 500줄 제한** (주석 제외 기준 — CLAUDE.md에서 확정)

### 데모 배포 (2026-07-13)
- **Streamlit Community Cloud** (무료) · **비공개** — 공동연구자 이메일 허용 목록
- URL: https://cshmragchatbot.streamlit.app
- GitHub push 시 **자동 재배포**
- ⚠️ 실증용 아님. 테스트 참여자(P001~P003)만 있으며 **실제 참여자 데이터 없음**

## 미완료 ⬜

### Phase 2 — RAG (다음)
- 승인 문서 등록 · 텍스트 추출 · 청킹 · 임베딩 · 벡터 저장
- 검색 · 근거 기반 답변 · 출처 표시 · 비용 로그
- 필요 테이블(미생성): documents · document_chunks · retrieval_logs · retrieval_chunks · model_calls · measurements · action_followups
- **pgvector 확장 미활성화** (사용 가능 상태)

### Phase 3 — 넛지 확장 · 종단 추적
### Phase 4 — 통합 테스트 · 현장 파일럿
- **T4.9 연구자용 관리자 대시보드** (2026-07-13 범위 추가)
  - 이유: 공동연구자가 비개발자라 Supabase 원시 테이블을 쓸 수 없고, 학교·기관 공유용 시각화가 필요
  - **Phase 2·3 이후에 만든다** — 보여줄 데이터(RAG·수행확인)가 다 쌓인 뒤여야 다시 안 만든다
  - 별도 앱(`admin/`), 참여자용 앱과 주소·권한 분리, 연구 데이터는 읽기 전용

## 다음 작업 ▶ (Phase 2 착수 조건)

Phase 2는 아래 **두 가지가 준비되면 즉시 착수** 가능하다.

| # | 필요한 것 | 담당 | 상태 |
|---|-----------|------|------|
| 1 | **승인 문서** (당뇨 가이드라인 등 2~3종) | 연구팀 | 이미 선정됨 — Phase 2 착수 시 전달 예정 |
| 2 | **LLM · 임베딩 API 계정** | 연구자 | Phase 2 착수 시 함께 설정 |

> 참고: Anthropic은 임베딩 API가 없어 **임베딩은 별도 제공사**(Voyage/OpenAI 등)가 필요하다. 모델·단가 확정 후 [COST_PLAN.md](COST_PLAN.md) 갱신.
> 전체 연구 예상 API 비용은 최고 성능 모델 기준으로도 **10만원대**로 추정된다(참여자 20명·12주·1일 3질문 가정).

## ⚠️ 실증 전 반드시 처리할 것

- **테스트 데이터 삭제** — 데모/개발 중 쌓인 P001~P003의 세션·메시지·넛지·이벤트를 실증 시작 전에 비운다. (현재 로컬·배포가 **같은 Supabase**를 공유)
- **실증용 배포환경·접근 제한 확정** (미결정 U11)
- **안전 안내문·응급 문구 의료전문가 검토** (미결정 U12)

---

## 문서 일관성 검수 결과 (2026-07-09, Phase 0 종료 시점)

| 점검 항목 | 결과 |
|-----------|------|
| 대상자 표현이 모든 문서에서 동일한가 | ✅ "고령 제2형 당뇨 환자"로 통일 |
| PRD와 CLAUDE의 기술 구성이 일치하는가 | ✅ |
| MVP 기능과 TASKS 작업이 일치하는가 | ✅ |
| 제외 기능이 작업목록에 들어가 있지 않은가 | ✅ 외부 알림·날씨·네이티브 앱 없음 |
| 데이터 구조도와 DATA_SCHEMA가 일치하는가 | ✅ (이후 리뷰 반영해 14개로 갱신) |
| 이벤트 이름이 문서마다 동일한가 | ✅ |
| 넛지 규칙과 안전 규칙이 충돌하지 않는가 | ✅ 복약 넛지=상기까지만 |
| 연구 데이터 영구 저장 위치가 Supabase로 통일 | ✅ |

> Phase 1에서 코드로 옮기며 **문서만으로는 못 잡던 모순 2건**을 발견해 수정했다(인증 전 이벤트 예외, sessions.app_version 중복). 문서는 계속 갱신 중.
