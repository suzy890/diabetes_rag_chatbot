# PROGRESS.md — 현재 진행 상태

> **문서 버전:** v0.1 · **갱신일:** 2026-07-09 (1주차 종료)

---

## 완료 ✅ (Phase 0 — 설계·규칙 고정)

- 시스템 구조도 · 데이터 관계 구조도 · 기능별 데이터 흐름도 (설계 기록)
- MVP 범위 정의 / 디지털 넛지 구현 범위 정의
- 프로젝트 문서: README · PRD · CLAUDE + `.claude/rules/`(architecture·research-data·medical-safety)
- 데이터 스키마 문서화 (DATA_SCHEMA — 14개 테이블) + **수집 우선 원칙**
- 이벤트 사전 (EVENT_DICTIONARY — 13개 이벤트)
- 넛지·RAG·안전 규칙 (NUDGE_RULES · RAG_RULES · SAFETY_RULES)
- 백로그·의사결정·비용·분석목표 (TASKS · DECISIONS · COST_PLAN · analysis-targets)
- 노션 개발 로그(Day 1~5) + 인터랙티브 위젯 5종 (`docs/widgets/`)

## 진행 중 🔄

- 전체 문서 v0.1 초안 → 실증 준비하며 수치·문구 구체화
- 미결정 항목 확정 (연구팀, 역순 접근으로 우선순위화 — [docs/analysis-targets.md](docs/analysis-targets.md))

## 미완료 ⬜ (다음 주부터)

- Streamlit 앱 · Supabase 연결 · schema.sql
- 문서 청킹 · 임베딩 · RAG 검색 · 답변
- 넛지 엔진 · 종단 추적
- 통합 테스트 · CSV 추출

## 다음 작업 ▶

- **T1.1 참여자 코드 입력 · 참여자 확인 · 세션 생성** ([TASKS.md](TASKS.md))
  - 완료 기준: 유효 코드→세션·이벤트 저장 / 무효 차단 / **새로고침 중복 없음** / 실패는 technical_errors 기록
  - 선행 결정: **U1 참여자 인증 방식**(연구자 입력 vs 직접) — [DECISIONS.md](DECISIONS.md)

---

## 1주차 문서 일관성 검수 결과 (2026-07-09)

| 점검 항목 | 결과 |
|-----------|------|
| 대상자 표현이 모든 문서에서 동일한가 | ✅ "고령 제2형 당뇨 환자"로 통일 |
| PRD와 CLAUDE의 기술 구성이 일치하는가 | ✅ Python·Streamlit·Supabase·pgvector·외부 LLM/임베딩·GitHub |
| MVP 기능과 TASKS 작업이 일치하는가 | ✅ Phase 1~4가 MVP 흐름을 커버 |
| 제외 기능이 작업목록에 들어가 있지 않은가 | ✅ 외부 알림·예약 넛지·날씨·네이티브 앱 없음 |
| 데이터 구조도와 DATA_SCHEMA가 일치하는가 | ✅ 13개 테이블 일치 (+ context_json 신설 반영) |
| 이벤트 이름이 문서마다 동일한가 | ✅ EVENT_DICTIONARY 기준 일치 |
| 넛지 규칙과 안전 규칙이 충돌하지 않는가 | ✅ 복약 넛지=상기까지만, 나머지 안전 규칙 우선 |
| 복약 넛지가 의료적 판단으로 확장되지 않았는가 | ✅ NUDGE·SAFETY 모두 명시 |
| 외부 알림이 초기 구현범위에 포함되지 않았는가 | ✅ 제외 유지 |
| 연구 데이터 영구 저장 위치가 Supabase로 통일되어 있는가 | ✅ 화면 상태(session_state)와 분리 |

> 검수 통과. 다음 주 첫 개발 작업(T1.1)의 완료 기준이 정의되어 있음 → **1주차 목표 달성.**
