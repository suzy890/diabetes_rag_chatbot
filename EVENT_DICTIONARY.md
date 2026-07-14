# EVENT_DICTIONARY.md — 핵심 이벤트 사전

> **문서 버전:** v0.1 · **작성 기준일:** 2026-07-08
> 이 문서는 시스템이 기록하는 **이벤트의 이름·발생조건·저장값·연구적 의미**를 고정한다.
> **이벤트 이름은 개발 중 임의로 바꾸지 않는다.** 이름을 바꾸면 이 문서를 먼저 갱신한다.
> 이벤트는 [DATA_SCHEMA.md](DATA_SCHEMA.md)의 `events` 테이블(`event_type`)에 저장되며, 넛지·RAG·안전 관련 이벤트는 각 전용 테이블에도 함께 반영된다.

---

## 공통 저장 규칙

- 모든 이벤트는 `events` 테이블에 **참여자 ID · 세션 ID · 발생시각(`occurred_at`) · 시스템 버전**과 함께 저장한다.
- 부가정보(버튼값·점수·선택지 등)는 `payload_json`에 담되, 핵심 분석변수는 관련 전용 테이블 컬럼으로도 저장한다.
- **중복 방지:** Streamlit 재실행(rerun)이나 새로고침으로 같은 이벤트가 두 번 기록되지 않도록 멱등하게 처리한다. 각 이벤트는 고유 ID를 갖는다.

## 이벤트 한눈에

| 이벤트 | 발생 시점 | 연구적 의미 |
|--------|-----------|------------|
| `app_opened` | 웹앱을 열었을 때 | 실제 접근 빈도 |
| `session_started` | 참여자 인증 후 사용 시작 | 유효 세션 시작 |
| `nudge_scheduled` | 넛지가 예정되었을 때 | 중재 계획량 |
| `nudge_displayed` | 화면에 실제 노출되었을 때 | 실제 중재 노출량 |
| `nudge_answered` | 사용자가 넛지에 답했을 때 | 즉시 참여 반응 |
| `action_committed` | 행동을 하겠다고 선택했을 때 | 행동의도·약속 |
| `action_completed` | 추후 수행했다고 보고했을 때 | 자기보고 행동 수행 |
| `question_asked` | 자유 질문을 입력했을 때 | 정보요구 발생 |
| `clarification_asked` | 용어가 모호해 되물었을 때 | **용어 모호성 발생** (AI 건강문해력) |
| `clarification_answered` | 참여자가 되묻기에 답했을 때 | **참여자의 용어 이해 수준** |
| `answer_displayed` | RAG 답변이 제시되었을 때 | 정보중재 노출 |
| `source_clicked` | 출처를 열었을 때 | 근거 확인 행동 |
| `safety_message_shown` | 안전 제한 응답이 표시되었을 때 | 고위험 질문 발생 |
| `survey_submitted` | 설문을 완료했을 때 | 결과변수 측정 |
| `session_ended` | 세션 종료 | 사용시간 계산 |

> 기술 오류는 `error_occurred`로 감지해 `technical_errors` 테이블에 별도 기록한다(연구 행동 데이터와 분리).

---

## 1. app_opened

- **발생 조건:** 참여자가 웹앱 URL을 열어 앱이 로드될 때 (인증 이전 포함).
- **저장 시점:** 앱 로드 직후.
- **필수 속성:** 시각, (가능 시) participant_id, session 후보.
- **관련 테이블:** events
- **중복 방지:** 같은 로드/새로고침이 반복 기록되지 않도록 세션 로드 단위로 1회.
- **분석 활용:** 실제 접근 빈도. 인증까지 이어지지 않은 이탈 파악.

## 2. session_started

- **발생 조건:** 참여자 코드 입력·확인이 성공해 유효 세션이 시작될 때.
- **저장 시점:** 세션 생성 직후.
- **필수 속성:** session_id, participant_id, started_at, app_version, system_version.
- **관련 테이블:** sessions(생성), events
- **중복 방지:** rerun이 새 세션을 만들지 않도록 세션 식별 유지. 세션당 1회.
- **분석 활용:** 유효 세션 시작 수, 참여 빈도, 세션 길이 계산 기준.

## 3. nudge_scheduled

- **발생 조건:** 시간대·기록·규칙에 따라 넛지가 예정될 때.
- **저장 시점:** 예정 결정 시.
- **필수 속성:** nudge_id, participant_id, trigger_type, health_domain, nudge_type, template_version, scheduled_at.
- **관련 테이블:** nudge_events(생성), events
- **중복 방지:** 같은 시간대·도메인 넛지가 하루 규칙을 초과해 중복 예정되지 않도록(NUDGE_RULES).
- **분석 활용:** 중재 **계획량**. 노출량과 비교해 미노출 파악.

## 4. nudge_displayed

- **발생 조건:** 예정된 넛지가 실제 화면에 표시될 때.
- **저장 시점:** 화면 렌더 시.
- **필수 속성:** nudge_id, displayed_at, session_id.
- **관련 테이블:** nudge_events(`displayed_at` 갱신), events
- **중복 방지:** 같은 넛지가 새로고침으로 반복 노출 기록되지 않도록. `scheduled_at`과 **분리** 저장.
- **분석 활용:** 실제 중재 **노출량**. 예정 대비 노출률.

## 5. nudge_answered

- **발생 조건:** 사용자가 넛지에 응답(선택/입력)할 때.
- **저장 시점:** 응답 수신 시.
- **필수 속성:** nudge_id, responded_at, response.
- **관련 테이블:** nudge_events(`responded_at`, `response` 갱신), messages(nudge_response), events
- **중복 방지:** 넛지 1건당 유효 응답 1회.
- **분석 활용:** 즉시 참여 반응, 넛지 반응률.

## 6. action_committed

- **발생 조건:** 사용자가 특정 행동을 "하겠다"고 선택할 때.
- **저장 시점:** 약속 선택 시.
- **필수 속성:** nudge_id, action_commitment(=planned_action), 시각.
- **관련 테이블:** nudge_events(`action_commitment`), action_followups(생성), events
- **중복 방지:** 넛지 1건의 약속당 1행.
- **분석 활용:** **행동의도·약속**. 수행(action_completed)과 분리해 의도→수행 전환 분석.

## 7. action_completed

- **발생 조건:** 추후 확인에서 사용자가 실제로 수행했다고 보고할 때.
- **저장 시점:** 수행 확인 응답 시.
- **필수 속성:** followup_id, completion_status, 시각.
- **관련 테이블:** action_followups(`completion_status`, `asked_at`), events
- **중복 방지:** 확인 1건당 1회(재확인은 별도 followup).
- **분석 활용:** **자기보고 행동 수행**. 약속→수행 소요시간, 넛지 유형별 수행 가능성.

## 8. question_asked

- **발생 조건:** 사용자가 자유 질문을 입력할 때.
- **저장 시점:** 질문 제출 시.
- **필수 속성:** message_id(rag_question), 시각.
- **관련 테이블:** messages(rag_question), events, (이어서) retrieval_logs·model_calls
- **중복 방지:** 질문 메시지 1건당 1회.
- **분석 활용:** 정보요구 발생 빈도·주제.

## 8-1. clarification_asked (2026-07-14 추가)

- **발생 조건:** 참여자의 표현이 모호해 **답이 달라질 수 있을 때**, AI가 되물을 때.
  (예: "혈당이 7인데 괜찮나요?" → 혈당인지 당화혈색소인지 확인 필요)
- **저장 시점:** 되묻기 메시지 렌더 시.
- **필수 속성:** 관련 question message_id, **모호했던 용어**(`term`), 제시한 선택지, 시각.
- **관련 테이블:** messages(`clarification_question`), events (payload_json에 term·선택지)
- **중복 방지:** **같은 세션에서 같은 용어는 한 번만** 되묻는다. 남발 금지(RAG_RULES §3-1).
- **분석 활용:** **용어 모호성이 얼마나 자주 발생하는가**, **어떤 용어가 혼동되는가.**
  → AI 건강문해력 연구의 직접 관측치.

## 8-2. clarification_answered (2026-07-14 추가)

- **발생 조건:** 참여자가 되묻기 선택지 중 하나를 선택할 때. **"잘 모르겠어요" 포함.**
- **저장 시점:** 선택 수신 시.
- **필수 속성:** 관련 `clarification_asked` 이벤트 연결, **선택한 값**, 시각.
- **관련 테이블:** messages(`clarification_response`), events
- **중복 방지:** 되묻기 1건당 유효 응답 1회.
- **분석 활용:** ⭐ **참여자가 혈당과 당화혈색소를 구분하는가?**
  **"모르겠다"를 선택한 비율**은 고령 참여자의 건강정보 이해 수준을 직접 보여준다.
  구분 여부와 이해도·자기효능감의 관계를 볼 수 있다.

> **"모르겠다"는 실패가 아니라 데이터다.** 고령 참여자가 두 지표를 구분하지 못하는 것은 정상이며,
> 그 비율 자체가 **연구 결과**다. 이 경우 시스템은 추측하지 않고 일반 정보 + 의료진 상담을 권고한다.

## 9. answer_displayed

- **발생 조건:** RAG 답변이 사용자에게 제시될 때.
- **저장 시점:** 답변 렌더 시.
- **필수 속성:** message_id(rag_answer), 관련 retrieval_id, 시각.
- **관련 테이블:** messages(rag_answer), retrieval_logs, events
- **중복 방지:** 답변 1건당 1회.
- **분석 활용:** 정보중재 노출. 질문→답변 연결.

## 10. source_clicked

- **발생 조건:** 사용자가 답변의 출처를 열어볼 때.
- **저장 시점:** 출처 클릭 시.
- **필수 속성:** 관련 answer message_id, 클릭한 출처 식별, 시각.
- **관련 테이블:** events (payload_json에 출처 정보)
- **중복 방지:** 동일 출처 반복 클릭은 각각 기록하되 rerun 중복은 방지.
- **분석 활용:** **근거 확인 행동**. 출처 클릭 경험과 이해도·신뢰의 관계.

## 11. safety_message_shown

- **발생 조건:** 위험/제한 질문에 대해 안전 제한 응답이 표시될 때.
- **저장 시점:** 안전 응답 렌더 시.
- **필수 속성:** 관련 message_id(safety_message), 질문 범주, 시각.
- **관련 테이블:** messages(safety_message), events (범주 포함)
- **중복 방지:** 안전 응답 1건당 1회.
- **분석 활용:** **고위험 질문 발생** 빈도·유형. 안내문 개선 근거(SAFETY_RULES).

## 12. survey_submitted

- **발생 조건:** 사용자가 설문을 완료·제출할 때.
- **저장 시점:** 제출 시.
- **필수 속성:** measurement 기록들(measure_name, item_id, value), measurement_timepoint, 시각.
- **관련 테이블:** measurements(생성), events
- **중복 방지:** (참여자 × 시점 × 문항)당 1행. 재제출 처리 규칙 필요.
- **분석 활용:** 결과변수 측정. 횡단·종단 분석의 핵심 값.

## 13. session_ended

- **발생 조건:** 세션이 종료될 때(명시적 종료·타임아웃·이탈).
- **저장 시점:** 종료 감지 시.
- **필수 속성:** session_id, ended_at, completion_status.
- **관련 테이블:** sessions(`ended_at`, `completion_status`), events
- **중복 방지:** 세션당 1회.
- **분석 활용:** 사용시간 계산, 세션 완료/중단 패턴.
