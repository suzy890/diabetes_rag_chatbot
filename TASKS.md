# TASKS.md — 개발 작업 백로그

> **문서 버전:** v0.1 · **작성 기준일:** 2026-07-09
> 기능을 작은 단위로 나눈다. **한 번에 하나씩** 구현한다([CLAUDE.md](CLAUDE.md)). 각 작업은 목적·입력·출력·수정 파일·완료 기준·테스트·의존을 갖는다.
> MVP 범위는 [PRD.md](PRD.md), 데이터는 [DATA_SCHEMA.md](DATA_SCHEMA.md)/[EVENT_DICTIONARY.md](EVENT_DICTIONARY.md), 규칙은 각 RULES 문서를 따른다.
> **제외 기능(외부 알림·예약 넛지·날씨·네이티브 앱 등)은 이 백로그에 넣지 않는다.**

---

## Phase 0 — 설계·규칙 고정 ✅ (이번 주 완료)

- [x] 프로젝트 문서 작성 (README, PRD, CLAUDE, rules)
- [x] 데이터 구조 확정 (DATA_SCHEMA)
- [x] 이벤트 사전 확정 (EVENT_DICTIONARY)
- [x] 넛지 규칙 확정 (NUDGE_RULES)
- [x] RAG 규칙 확정 (RAG_RULES)
- [x] 안전 규칙 확정 (SAFETY_RULES)

---

## Phase 1 — 웹앱·DB 골격 ✅ (2026-07-13 완료)

- [x] **T1.1** 참여자 코드 입력 · 확인 · 세션 생성 — 테스트 8/8 통과
- [x] **T1.2** Supabase 연결 · 스키마 생성 (7개 테이블, RLS 전면 적용)
- [x] **T1.3** 기본 채팅 화면 (메시지 저장·DB 복원·중복 방지) — 테스트 7/7 통과
- [x] **T1.4** 접속 시간대 넛지 (승인 템플릿 v0.1 5종, 하루 3회 상한) — 테스트 10/10 통과
- [x] **데모 배포** (Streamlit Community Cloud, 비공개) → [DEPLOY.md](DEPLOY.md)

<details>
<summary>Phase 1 작업 상세 (완료)</summary>

### T1.1 참여자 코드 입력 · 참여자 확인 · 세션 생성 ⭐ (첫 작업)
- **목적:** 참여자가 익명 코드로 입장하고, 유효 세션을 만들어 접속을 기록한다.
- **입력:** 참여자 코드(예: P001), (Supabase에 등록된 participants)
- **예상 출력:** 유효 코드면 세션 생성 후 채팅 화면 진입 / 무효면 안내. `sessions` 1행 + `app_opened`·`session_started` 이벤트 저장.
- **수정 대상 파일:** `app.py`, `database.py`, `config.py`, `schema.sql`(participants·sessions·events)
- **완료 기준:**
  1. 유효 코드로 입장하면 `sessions`에 1행이 생기고 `session_started` 이벤트가 저장된다.
  2. 무효 코드는 진입이 막히고 안내가 뜬다.
  3. **새로고침(rerun) 시 세션이 중복 생성되지 않는다.**
  4. 저장 실패 시 `technical_errors`에 기록된다.
- **테스트 방법:** 유효/무효 코드 각각 입력 → Supabase에서 sessions·events 행 수 확인 → 새로고침 반복 후 중복 없음 확인.
- **의존 작업:** 없음 (첫 작업). 단 participants 등록 방식(연구자 입력 vs 직접) 결정 필요 → [DECISIONS.md](DECISIONS.md) 미결정.

### T1.2 Supabase 연결 · 기본 스키마 생성
- **목적:** DB 연결과 최소 테이블 생성.
- **입력:** Supabase 접속정보(시크릿, 코드에 하드코딩 금지), `schema.sql`
- **예상 출력:** participants·sessions·messages·events 테이블 생성, 연결 확인.
- **수정 대상 파일:** `database.py`, `config.py`, `schema.sql`
- **완료 기준:** 앱에서 DB 읽기/쓰기 성공. 스키마가 DATA_SCHEMA.md와 일치.
- **테스트 방법:** 연결 테스트 스크립트, 샘플 insert/select.
- **의존 작업:** DB 스키마 변경은 **사용자 승인** 후.

### T1.3 기본 채팅 화면
- **목적:** 하나의 채팅 화면(메시지 표시·입력).
- **예상 출력:** 메시지가 `messages`에 시간순 저장되고 새로고침 후 DB에서 복원.
- **수정 대상 파일:** `app.py`, `database.py`
- **완료 기준:** 사용자·AI 메시지가 role·message_type과 함께 저장, 재실행 후 대화 복원, 중복 저장 없음.
- **테스트 방법:** 메시지 여러 개 입력 → 새로고침 → 복원 확인.
- **의존 작업:** T1.1, T1.2

### T1.4 접속 시간대 넛지 1종
- **목적:** 접속 시각 기반 넛지 1종 표시(규칙·템플릿).
- **예상 출력:** 시간대에 맞는 승인 템플릿 넛지 노출, `nudge_events`·`nudge_scheduled`/`nudge_displayed` 저장.
- **수정 대상 파일:** `nudge.py`, `app.py`, `database.py`
- **완료 기준:** 시간대별 넛지 노출, 하루 1회·새로고침 중복 방지(NUDGE_RULES), 응답 저장.
- **테스트 방법:** 시간대 모의 → 노출 확인 → 새로고침 중복 없음.
- **의존 작업:** T1.1~T1.3

</details>

---

## Phase 2 — 최소 RAG Vertical Slice ◀ **다음**

> **착수 조건 (2가지):**
> 1. **승인 문서** 2~3종 — 연구팀이 이미 선정, 착수 시 전달 예정
> 2. **LLM · 임베딩 API 계정** — 착수 시 함께 설정
>    (⚠️ Anthropic은 임베딩 API가 없어 **임베딩은 별도 제공사** 필요)
>
> 먼저 만들 것: pgvector 활성화 + `documents` · `document_chunks` · `retrieval_logs` · `retrieval_chunks` · `model_calls` 테이블

각 작업 공통: 완료 기준=지정 데이터가 저장되고 재현 가능 / 테스트=샘플 질문으로 확인 / 의존=직전 작업.

- [ ] **T2.1 승인 문서 등록** — `documents` 등록(제목·기관·연도·버전·승인상태). 파일: database.py, schema.sql
- [ ] **T2.2 문서 텍스트 추출·전처리** — 원문에서 텍스트 추출. 파일: (스크립트)/rag.py
- [ ] **T2.3 청킹** — 의미 단위 분할 + 토큰 수. 파일: rag.py. _단위 미결정_
- [ ] **T2.4 임베딩·벡터 저장** — 임베딩 API 호출→`document_chunks` 저장, `model_calls` 기록. 파일: rag.py, database.py
- [ ] **T2.5 검색 테스트** — 질문 임베딩→pgvector 검색→`retrieval_logs`. 파일: rag.py, database.py
- [ ] **T2.6 근거 기반 답변 생성** — 3단계 충분성 판단→답변. 파일: rag.py
- [ ] **T2.7 출처 표시** — 답변에 출처·`source_clicked` 이벤트. 파일: app.py
- [ ] **T2.8 비용 로그** — 모든 호출 토큰·단가·비용 `model_calls` 저장. 파일: database.py

---

## Phase 3 — 넛지·종단 추적

- [ ] **T3.1 식사·운동 넛지 유형 추가** — 템플릿·규칙 확장. 파일: nudge.py
- [ ] **T3.2 행동 약속 저장** — `action_committed`→`action_followups`. 파일: nudge.py, database.py
- [ ] **T3.3 추후 수행 확인** — 다음 접속 시 확인 질문→`action_completed`. 파일: nudge.py, app.py
- [ ] **T3.4 참여자별 종단 이벤트 생성** — 시간순 이벤트 무결성 확인. 파일: database.py

---

## Phase 4 — 통합·테스트·현장 파일럿

- [ ] **T4.1 RAG·넛지 통합** (하나의 채팅 화면 오케스트레이션)
- [ ] **T4.2 위험 질문 처리 테스트** (SAFETY 5범주)
- [ ] **T4.3 API 오류 처리** (`technical_errors`)
- [ ] **T4.4 DB 오류 처리**
- [ ] **T4.5 중복 저장 테스트** (rerun 멱등성)
- [ ] **T4.6 모바일 화면 테스트** (고령친화)
- [ ] **T4.7 데이터 CSV 추출** (연구자 확인)
- [ ] **T4.8 시스템 버전 고정** (`system_versions`)

---

## 공통 작업 규칙 (모든 태스크)

- 한 번에 하나의 태스크만. 완료 후 다음으로.
- 수정 후 테스트 실행 → 수정 파일·결과 보고.
- 파일 삭제·DB 스키마 변경·배포는 **사용자 승인** 후.
- 모든 연구 이벤트에 참여자 ID·시각·시스템 버전 기록.
