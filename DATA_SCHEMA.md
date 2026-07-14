# DATA_SCHEMA.md — 연구 데이터 스키마

> **문서 버전:** v0.1 · **작성 기준일:** 2026-07-08
> 이 문서는 웹앱이 **어떤 데이터를 언제·어디에 저장하는지**를 정의한다. 화면보다 데이터 구조를 먼저 확정한다.
> 규칙 기반은 [.claude/rules/research-data.md](.claude/rules/research-data.md). 이벤트 이름은 [EVENT_DICTIONARY.md](EVENT_DICTIONARY.md)에서 관리한다.
> 실제 SQL 생성문(`schema.sql`)은 Phase 1에서 이 문서를 근거로 작성한다. **스키마 변경은 사용자 승인 후** 이 문서를 먼저 갱신하고 진행한다.

---

## 공통 규칙

- **모든 시각 필드는 timezone-aware timestamp**로 저장한다. (종단분석에서 순서 재구성에 필수)
- **모든 연구 이벤트/기록에는 참여자·발생시각·시스템 버전**이 연결된다.
- **PK는 UUID**를 기본으로 하고, `participant_id`만 사람이 읽는 익명 코드(`P001`)를 병행할 수 있다.
- **핵심 분석변수는 명확한 컬럼**으로 저장한다. 형태가 자주 바뀌는 부가정보만 `*_json`에 담는다.
- **직접식별정보(실명·전화·주소·환자번호)는 어떤 테이블에도 저장하지 않는다.**
- **수집 우선(collect-now, analyze-later):** MVP에서 분석하지 않더라도 추후 분석 가치가 있는 데이터는 지금 최소 필드로 수집한다(→ 아래 별도 절). 데이터는 한 번 놓치면 소급 수집이 불가능하다.

## 수집 우선 원칙 (collect-now, analyze-later)

> 연구팀 피드백 반영: "이번에 결과 분석이 되지 않더라도, 추후를 고려해 그 데이터를 모을 수 있는 최소한의 스키마가 있으면 좋겠다." (2026-07)

- MVP에서 **분석하지 않더라도, 추후 분석 가치가 있는 데이터는 지금 최소 필드로 수집**한다. 데이터는 사후 소급 수집이 불가능하기 때문이다.
- 단, **개인정보·동의 부담이 큰 항목(위치, 정밀 이동정보 등)은 IRB 동의를 확보하기 전까지 수집하지 않는다.** 수집 우선 원칙이 개인정보 최소수집 원칙을 넘어서지 않는다.
- 확장은 가능한 한 **기존 유연 필드**(`payload_json`, `context_json` 등)로 담아, 나중에 스키마를 크게 바꾸지 않고도 데이터를 살릴 수 있게 한다.

### 미래 대비 최소 수집 항목 (MVP는 "수집만", 분석 제외)

| 미래 기능 | 지금 수집할 최소 데이터 | 저장 위치 | 개인정보 주의 |
|-----------|------------------------|-----------|--------------|
| 날씨 기반 넛지 | 넛지 노출 당시 맥락(시간대·요일·자가보고 상황) | `nudge_events.context_json` (신설) | **위치정보는 동의 전 수집 안 함** |
| 예약 넛지 | 예정 시각·트리거 유형 | `nudge_events.scheduled_at`, `trigger_type` (이미 있음) | — |
| 외부 알림(문자·카카오·푸시) | (지금은 미수집) 발송 채널·결과는 향후 별도 테이블 | 향후 `notification_events` | 연락처는 앱 밖 분리 보관 |
| 장기 개인화 | 넛지 반응·행동 수행 패턴 | 기존 `nudge_events`·`action_followups` (이미 수집됨) | — |
| 세밀 사용성 분석 | 화면 체류·클릭 등 상호작용 | `events.payload_json` (이미 유연) | 식별정보 미포함 |

> 위 항목은 **지금 값을 채워 저장만** 하고, MVP 분석 대상에는 넣지 않는다. 분석 우선순위는 Day 5의 "최소 결과물(분석 목표) 정의"에서 확정한다.

## 전체 관계도

```
participants (참여자)
├──< sessions (접속 세션)
│      ├──< messages (대화 메시지)
│      │      ├── retrieval_logs (RAG 검색 1회)
│      │      │      └──< retrieval_chunks (검색된 청크 1개당 1행)
│      │      └── model_calls (외부 API 호출)
│      ├──< events (행동 이벤트)
│      └──< technical_errors (기술 오류)
├──< nudge_events (넛지)
│      └──< action_followups (추후 수행 확인)
└──< measurements (설문·측정)

documents (원문)
└──< document_chunks (문서 청크)   ←── retrieval_chunks 가 참조

system_versions (시스템 버전)  ──→ sessions · messages · events · nudge_events · retrieval_logs 등에 연결
```

기호 `──<` = 1:다 (한 참여자가 여러 세션·메시지를 가질 수 있음).

---

## 1. participants — 연구 참여자 기본정보

- **목적:** 참여자를 식별하고 연구 참여 상태를 관리한다. 직접식별정보 없이 익명 ID로만 관리.
- **PK:** `participant_id`
- **생성 시점:** 연구자가 참여자를 등록할 때 1회.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `participant_id` | 연구용 익명 ID (예: P001) | PK · 필수 |
| `enrolled_at` | 연구 등록일 | 필수 |
| `study_start_date` | 실제 사용 시작일 | 선택 |
| `study_end_date` | 사용 종료일 | 선택 |
| `status` | 예정 / 참여중 / 완료 / 철회 | 필수 |
| `timezone` | 시간 기반 넛지용 기준 시간대 | 필수 |
| `created_at` | 시스템 등록 시각 | 필수 |

- **연결:** → sessions, nudge_events, measurements (1:다)
- **분석 의미:** 배경변수·참여 상태 기준. 모든 데이터의 출발점.
- **개인정보:** 익명 ID만 저장. 실명↔ID 연결표는 **애플리케이션 밖에서 분리 보관**.
- **중복 방지:** 참여자당 1행. `participant_id` 유일.

## 2. sessions — 한 번의 접속 단위

- **목적:** 웹앱을 열고 종료할 때까지를 하나의 세션으로 기록.
- **PK:** `session_id` · **FK:** `participant_id`
- **생성 시점:** 참여자 인증 후 사용 시작(`session_started`) 시.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `session_id` | 세션 고유 ID | PK · 필수 |
| `participant_id` | 참여자 연결 | FK · 필수 |
| `system_version_id` | 당시 시스템 버전 | FK · 필수 |
| `started_at` | 접속 시작 시각 | 필수 |
| `ended_at` | 접속 종료 시각 | 선택 |
| `device_type` | mobile / tablet / desktop | 선택 |
| `completion_status` | 정상종료 / 중단 / 오류 | 선택 |

- **연결:** participants(부모) → messages, events, technical_errors (1:다)
- **분석 의미:** 참여 빈도, 세션 길이, 기기 유형별 사용 차이.
- **개인정보:** 없음.
- **중복 방지:** 접속 1회당 1행. 새로고침(rerun)이 새 세션을 만들지 않도록 세션 식별을 유지.
- **⚠️ `app_version` 컬럼 없음 (2026-07-13 결정):** 웹앱은 "기기에 설치된 앱 버전"이 존재하지 않는다(모두 같은 서버에 접속). 앱 버전은 `system_version_id`로 알 수 있으므로 별도 컬럼을 두면 **중복이자 불일치 위험**만 생긴다.

## 3. messages — 채팅창의 모든 메시지

- **목적:** 사용자·AI 메시지를 한 표에 시간순 저장.
- **PK:** `message_id` · **FK:** `session_id`, `participant_id`, `system_version_id`
- **생성 시점:** 메시지가 생성될 때마다.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `message_id` | 메시지 고유 ID | PK · 필수 |
| `session_id` | 세션 연결 | FK · 필수 |
| `participant_id` | 참여자 연결 | FK · 필수 |
| `role` | user / assistant / system | 필수 |
| `message_type` | nudge / nudge_response / rag_question / rag_answer / safety_message / free_text / system_notice / **clarification_question** / **clarification_response** | 필수 |
| `content` | 실제 메시지 내용 | 필수 |
| `created_at` | 생성 시각 | 필수 |
| `system_version_id` | 당시 시스템 버전 | FK · 필수 |

- **연결:** sessions(부모) → retrieval_logs, model_calls
- **분석 의미:** `role`과 `message_type`을 **분리**해야 넛지/RAG답변/안전안내를 구분 분석 가능.
- **개인정보:** 자유서술에 식별정보가 섞일 수 있음 → 입력 안내·마스킹 검토(research-data 규칙).
- **중복 방지:** `message_id` 유일. rerun 시 이미 저장된 메시지 재저장 금지.

## 4. events — 행동 이벤트 로그

- **목적:** 메시지 외의 사건(화면 열기·클릭·출처 확인·행동 선택)을 시간순 기록.
- **PK:** `event_id` · **FK:** `participant_id`, `session_id`, `related_message_id`, `system_version_id`
- **생성 시점:** 정의된 이벤트가 발생할 때마다. (이벤트 목록은 EVENT_DICTIONARY.md)

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `event_id` | 이벤트 고유 ID | PK · 필수 |
| `participant_id` | 참여자 연결 | FK · **선택**(아래 예외 참고) |
| `session_id` | 세션 연결 | FK · **선택**(아래 예외 참고) |
| `event_type` | 어떤 사건인지 (사전 정의값) | 필수 |
| `occurred_at` | 발생 시각 | 필수 |
| `related_message_id` | 관련 메시지 | FK · 선택 |
| `payload_json` | 버튼값·점수 등 부가정보 | 선택 |
| `system_version_id` | 당시 시스템 버전 | FK · 필수 |

- **연결:** sessions(부모)
- **분석 의미:** 참여자별 **시간순 행동 경로** 재구성.
- **개인정보:** payload_json에 식별정보를 넣지 않는다.
- **중복 방지:** `event_id` 유일. 같은 사용자 행동이 rerun으로 중복 기록되지 않도록 처리.
- **⚠️ 인증 전 이벤트 예외 (2026-07-13 결정):** `app_opened`는 참여자가 코드를 입력하기 **전**에도 발생하므로([EVENT_DICTIONARY.md](EVENT_DICTIONARY.md)), 그 시점에는 참여자·세션을 알 수 없다. 따라서 `participant_id`·`session_id`는 **nullable**이다.
  - **인증 이후의 모든 이벤트는 두 값이 반드시 채워진다.** (`occurred_at`·`system_version_id`는 언제나 필수)
  - 이 예외 덕분에 "앱은 열었지만 코드를 넣지 않고 이탈"한 경우를 기록할 수 있다 → 고령 사용자의 **접근성·이탈 분석**에 활용.

## 5. nudge_events — 넛지 생성·노출·반응

- **목적:** 넛지 연구의 핵심 전용 테이블. 예정·노출·반응을 함께 기록.
- **PK:** `nudge_id` · **FK:** `participant_id`, `session_id`
- **생성 시점:** 넛지가 예정될 때(`nudge_scheduled`) 생성, 이후 노출·반응 시각을 갱신.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `nudge_id` | 넛지 고유 ID | PK · 필수 |
| `participant_id` | 대상 참여자 | FK · 필수 |
| `session_id` | 노출된 세션 | FK · 선택 |
| `trigger_type` | app_open / scheduled / behavior_based | 필수 |
| `health_domain` | 식사 / 운동 / 복약 / 혈당측정 | 필수 |
| `nudge_type` | 정보형 / 선택구조형 / 작은행동제안 / 자기효능감강화 등 | 필수 |
| `template_version` | 사용한 승인 템플릿 버전 | 필수 |
| `scheduled_at` | 예정 시각 | 필수 |
| `displayed_at` | 실제 노출 시각 | 선택 |
| `responded_at` | 반응 시각 | 선택 |
| `response` | 사용자의 답변/선택 | 선택 |
| `action_commitment` | 하겠다고 선택한 행동 | 선택 |
| `context_json` | 노출 당시 맥락(시간대·요일·자가보고 상황 등) — **향후 상황기반 넛지(날씨 등) 분석용, MVP는 수집만** | 선택 |
| `status` | 예정 / 노출 / 응답 / 무응답 / 완료 | 필수 |

- **연결:** participants(부모) → action_followups
- **분석 의미:** **예정(scheduled)≠노출(displayed)** 분리로 실제 중재 노출량 측정. 반응률·행동의도 분석. `context_json`은 수집 우선 원칙에 따라 지금 모아두는 미래용 맥락(위치정보는 동의 전 제외).
- **개인정보:** 없음.
- **중복 방지:** 같은 예정 넛지가 새로고침으로 중복 노출/기록되지 않도록 하루 노출·응답 규칙 적용(NUDGE_RULES).

## 6. action_followups — 약속한 행동의 추후 수행 확인

- **목적:** 종단 행동분석을 위해 **"하겠다"(의도)와 "실제로 했다"(수행)를 분리** 기록.
- **PK:** `followup_id` · **FK:** `nudge_id`, `participant_id`
- **생성 시점:** 넛지에서 행동 약속(`action_committed`)이 생길 때.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `followup_id` | 추후 확인 기록 ID | PK · 필수 |
| `nudge_id` | 시작된 넛지 | FK · 필수 |
| `participant_id` | 참여자 연결 | FK · 필수 |
| `planned_action` | 약속한 행동 | 필수 |
| `followup_due_at` | 다시 물어볼 예정 시각 | 필수 |
| `asked_at` | 실제 확인 질문 시각 | 선택 |
| `completion_status` | 완료 / 일부완료 / 미완료 / 확인불가 | 선택 |
| `participant_comment` | 사용자의 간단한 설명 | 선택 |

- **연결:** nudge_events(부모)
- **분석 의미:** 행동 약속 → 실제 수행까지의 전환·소요시간(종단).
- **개인정보:** comment에 식별정보 유입 주의.
- **중복 방지:** 넛지 1건의 약속당 1행.

## 7. retrieval_logs — RAG 검색 근거 기록

- **목적:** 최종 답변만이 아니라 **검색 과정 자체**를 저장. 할루시네이션이 검색 실패인지 생성 실패인지 구분.
- **PK:** `retrieval_id` · **FK:** `question_message_id`, `answer_message_id`, (참조) `document_chunks`
- **생성 시점:** RAG 검색이 수행될 때.

> **⚠️ 구조 변경 (2026-07-13, 연구팀 리뷰 반영):** 검색된 청크를 **배열**(`retrieved_chunk_ids`, `similarity_scores`)로 담으면 분석이 매우 어렵다. ("이 청크가 몇 번 검색됐나?", "유사도 분포는?", "선택된 청크의 평균 순위는?" 모두 배열로는 고통스럽다.)
> → **검색 1회 = `retrieval_logs` 1행**, **검색된 청크 1개 = `retrieval_chunks` 1행**으로 정규화한다. 이래야 [RAG_RULES.md](RAG_RULES.md)의 "검색 품질과 답변 품질을 분리 평가"가 실제로 가능하다.

**7-1. `retrieval_logs` — 검색 1회의 메타정보**

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `retrieval_id` | 검색 기록 ID | PK · 필수 |
| `question_message_id` | 질문 메시지 연결 | FK · 필수 |
| `answer_message_id` | 답변 메시지 연결 | FK · 선택 |
| `query_text` | 실제 검색에 사용한 질문 | 필수 |
| `embedding_model` | 질문 임베딩 모델 | 필수 |
| `top_k` | 검색 청크 수 | 필수 |
| `knowledge_base_version` | 당시 지식베이스 버전 | 필수 |
| `evidence_level` | 근거 충분성 판정: 충분 / 부분 / 부족 (RAG_RULES 3단계) | 필수 |
| `retrieved_at` | 검색 시각 | 필수 |

**7-2. `retrieval_chunks` — 검색된 청크 1개당 1행 (신설)**

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `retrieval_chunk_id` | PK | PK · 필수 |
| `retrieval_id` | 어느 검색인지 | FK · 필수 |
| `chunk_id` | 어떤 청크인지 | FK · 필수 |
| `rank` | 검색 순위 (1위, 2위 …) | 필수 |
| `similarity_score` | 유사도 점수 | 필수 |
| `was_selected` | 답변에 실제로 사용됐는지 | 필수 |

- **연결:** retrieval_logs(부모) · document_chunks(참조) · messages(질문/답변)
- **분석 의미:** 청크별 검색 빈도, 유사도 분포, 선택률, 순위별 채택률을 **SQL 한 줄로** 집계 가능. 오답이 검색 실패인지 생성 실패인지 구분.
- **개인정보:** query_text에 식별정보 유입 주의.
- **중복 방지:** 검색 1회당 retrieval_logs 1행 / (검색 × 청크)당 retrieval_chunks 1행.
- **생성 시점:** Phase 2 (RAG 구현 시).

## 8. measurements — 설문·반복 측정값

- **목적:** 횡단·종단 분석용 자기보고/평가값을 세로로 누적.
- **PK:** `measurement_id` · **FK:** `participant_id`, `session_id`(선택)
- **생성 시점:** 설문 제출(`survey_submitted`)/측정 시.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `measurement_id` | 측정 기록 ID | PK · 필수 |
| `participant_id` | 참여자 연결 | FK · 필수 |
| `session_id` | 측정 세션(있으면) | FK · 선택 |
| `measure_name` | AI건강문해력 / 신뢰 / 이해도 / 자기효능감 / 행동의도 / 사용성 등 | 필수 |
| `item_id` | 설문 문항 ID | 필수 |
| `value` | 응답값 | 필수 |
| `measurement_timepoint` | baseline / week1 / week2 / post 등 | 필수 |
| `measured_at` | 측정 시각 | 필수 |

- **연결:** participants(부모)
- **분석 의미:** 세로 누적으로 참여자별 시간 변화 분석 용이. _(측정시점 정의는 미결정 — PRD 부록 B)_
- **개인정보:** 없음.
- **중복 방지:** (참여자 × 문항 × 시점)당 1행.

## 9. documents — 지식베이스 원문 목록

- **목적:** RAG에 사용하는 승인 문서의 출처·버전 관리.
- **PK:** `document_id`
- **생성 시점:** 승인 후보 문서를 등록할 때.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `document_id` | 문서 고유 ID | PK · 필수 |
| `title` | 문서명 | 필수 |
| `publisher` | 발행기관 | 필수 |
| `published_at` | 발행일/개정일 | 필수 |
| `source_version` | 원문 버전 | 필수 |
| `approval_status` | 검토중 / 승인 / 비활성 | 필수 |
| `valid_from` | 사용 시작일 | 선택 |
| `valid_to` | 사용 종료일 | 선택 |
| `source_location` | 원문 파일/저장 위치 | 선택 |

- **연결:** → document_chunks (1:다)
- **분석 의미:** 개정돼도 이전 버전을 **삭제하지 않고 비활성화**해야 과거 답변 재현 가능.
- **개인정보:** 없음(공개 문서).
- **중복 방지:** (문서 × 버전)당 1행.

## 10. document_chunks — 검색용 문서 조각

- **목적:** 긴 문서를 의미 단위로 나눈 청크 + 임베딩 벡터 저장.
- **PK:** `chunk_id` · **FK:** `document_id`
- **생성 시점:** 문서 청킹·임베딩 시.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `chunk_id` | 청크 고유 ID | PK · 필수 |
| `document_id` | 원문 연결 | FK · 필수 |
| `section_path` | 장·절·소제목 위치 | 선택 |
| `page_number` | 원문 페이지 | 선택 |
| `content` | 청크 본문 | 필수 |
| `embedding` | 임베딩 벡터 (pgvector) | 필수 |
| `embedding_model` | 사용 임베딩 모델 | 필수 |
| `embedding_version` | 임베딩 버전 | 필수 |
| `token_count` | 청크 토큰 수 | 필수 |
| `is_active` | 현재 검색 대상 여부 | 필수 |

- **연결:** documents(부모) · retrieval_logs가 참조
- **분석 의미:** 검색 재현성. 변경된 청크만 재임베딩(비용 절감).
- **개인정보:** 없음.
- **중복 방지:** (문서버전 × 청크 × 임베딩버전)당 1행. `is_active`로 활성 버전 관리.

## 11. model_calls — 외부 API 호출·비용

- **목적:** LLM 답변·넛지 문장화·질문/문서 임베딩·안전 점검 등 외부 호출과 비용 기록.
- **PK:** `call_id` · **FK:** `participant_id`(선택), `related_message_id`
- **생성 시점:** 외부 API를 호출할 때마다.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `call_id` | 호출 ID | PK · 필수 |
| `participant_id` | 관련 참여자 | FK · 선택 |
| `related_message_id` | 관련 메시지 | FK · 선택 |
| `call_type` | rag_answer / nudge_rewrite / query_embedding / document_embedding / safety_check | 필수 |
| `provider` | API 제공사 | 필수 |
| `model_name` | 사용 모델 | 필수 |
| `input_tokens` | 입력 토큰 수 | 필수 |
| `output_tokens` | 출력 토큰 수 | 선택 |
| `unit_input_price` | 당시 입력 단가 | 필수 |
| `unit_output_price` | 당시 출력 단가 | 선택 |
| `estimated_cost` | 계산된 예상 비용 | 필수 |
| `latency_ms` | 응답시간 | 선택 |
| `status` | 성공 / 실패 / 재시도 | 필수 |
| `called_at` | 호출 시각 | 필수 |

- **연결:** messages(관련)
- **분석 의미:** 비용 산정·모니터링. 단가는 변하므로 **토큰뿐 아니라 단가·기준일도 함께** 저장.
- **개인정보:** 외부 전송 맥락 최소화.
- **중복 방지:** 호출 1회당 1행.

## 12. system_versions — 시스템 버전 추적

- **목적:** 각 데이터가 **어떤 설정으로 생성되었는지** 추적(연구 재현성).
- **PK:** `system_version_id`
- **생성 시점:** 설정(모델·프롬프트·규칙·지식베이스)이 바뀔 때마다 새 버전.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `system_version_id` | 시스템 버전 ID | PK · 필수 |
| `app_version` | 웹앱 코드 버전 | 필수 |
| `llm_model_version` | LLM 모델 | 필수 |
| `embedding_version` | 임베딩 모델·버전 | 필수 |
| `prompt_bundle_version` | 프롬프트 묶음 버전 | 필수 |
| `nudge_rule_version` | 넛지 규칙 버전 | 필수 |
| `safety_rule_version` | 안전 규칙 버전 | 필수 |
| `knowledge_base_version` | 지식베이스 버전 | 필수 |
| `term_dictionary_version` | **승인 용어 사전 버전** (2026-07-14 추가) — 어떤 용어사전으로 중재했는지 추적 | 선택 |
| `activated_at` | 적용 시작 시각 | 필수 |
| `deactivated_at` | 적용 종료 시각 | 선택 |
| `change_note` | 변경 내용 | 선택 |

- **연결:** sessions · messages · events · nudge_events · retrieval_logs 등이 참조
- **분석 의미:** 중간 설정 변경 시 참여자별 중재 차이를 통제.
- **개인정보:** 없음.
- **중복 방지:** 설정 조합당 1행. 활성 버전은 1개.

## 13. technical_errors — 기술 오류 기록

- **목적:** API·DB·검색 실패를 **연구 행동 데이터와 분리** 기록.
- **PK:** `error_id` · **FK:** `participant_id`(선택), `session_id`
- **생성 시점:** 기술 오류(`error_occurred`) 발생 시.

| 필드 | 의미 | 키/필수 |
|------|------|--------|
| `error_id` | 오류 ID | PK · 필수 |
| `participant_id` | 관련 참여자 | FK · 선택 |
| `session_id` | 관련 세션 | FK · 선택 |
| `error_type` | API 실패 / DB 실패 / 검색 실패 등 | 필수 |
| `error_message` | 오류 내용 | 필수 |
| `occurred_at` | 발생 시각 | 필수 |
| `resolved_status` | 해결 여부 | 선택 |

- **연결:** sessions(관련)
- **분석 의미:** 사용자의 무응답이 **실제 무관심인지 시스템 실패인지** 구분.
- **개인정보:** error_message에 식별정보/원문 민감정보 유입 주의.
- **중복 방지:** 오류 1건당 1행.

---

## 결측값·데이터형식 메모 (v0.1)

- 시각: `timestamptz`. 날짜: `date`. 금액/단가: 소수 허용 `numeric`. 토큰 수: `integer`.
- 목록형(`retrieved_chunk_ids`, `similarity_scores`): 배열 또는 JSON. 단, 핵심 분석변수는 별도 컬럼 유지.
- 선택값 미입력은 `NULL`. "무응답"과 "미측정"은 상태값(`status`, `completion_status`)으로 구분하고 NULL과 혼동하지 않는다.
