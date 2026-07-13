-- schema.sql — 연구 데이터 테이블 정의
-- 근거: DATA_SCHEMA.md · EVENT_DICTIONARY.md · .claude/rules/research-data.md
-- Phase 1(첫 슬라이스)에 필요한 최소 테이블만 생성한다. 나머지는 해당 기능을 만들 때 추가.
--
-- 보안: 모든 테이블에 RLS를 켜고 정책을 만들지 않는다
--       → 외부(anon/authenticated)는 읽기·쓰기 모두 차단.
--       → 우리 앱 서버가 쓰는 secret 키(service_role)만 RLS를 우회해 기록 가능.
--       → 연구 데이터에 외부에서 가짜 데이터를 넣을 수 없다.

-- ─────────────────────────────────────────────────────────────
-- 1. system_versions — 어떤 설정으로 중재했는지 추적 (연구 재현성)
--    모든 연구 이벤트가 이 버전을 참조한다 (research-data.md 필수 규칙)
-- ─────────────────────────────────────────────────────────────
create table if not exists system_versions (
    system_version_id      uuid primary key default gen_random_uuid(),
    app_version            text        not null,
    llm_model_version      text,                  -- Phase 2에서 채움
    embedding_version      text,                  -- Phase 2에서 채움
    prompt_bundle_version  text,
    nudge_rule_version     text,
    safety_rule_version    text,
    knowledge_base_version text,
    activated_at           timestamptz not null default now(),
    deactivated_at         timestamptz,           -- null이면 현재 활성 버전
    change_note            text
);

-- ─────────────────────────────────────────────────────────────
-- 2. participants — 연구 참여자 (익명 ID만. 직접식별정보 저장 금지)
-- ─────────────────────────────────────────────────────────────
create table if not exists participants (
    participant_id    text        primary key,           -- 예: 'P001'
    enrolled_at       timestamptz not null default now(),
    study_start_date  date,
    study_end_date    date,
    status            text        not null default 'scheduled'
                      check (status in ('scheduled', 'active', 'completed', 'withdrawn')),
    timezone          text        not null default 'Asia/Seoul',
    created_at        timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────
-- 3. sessions — 한 번의 접속 (시작~종료)
-- ─────────────────────────────────────────────────────────────
create table if not exists sessions (
    session_id        uuid        primary key default gen_random_uuid(),
    participant_id    text        not null references participants(participant_id),
    system_version_id uuid        not null references system_versions(system_version_id),
    started_at        timestamptz not null default now(),
    ended_at          timestamptz,
    device_type       text        check (device_type in ('mobile', 'tablet', 'desktop')),
    app_version       text        not null,
    completion_status text        check (completion_status in ('normal', 'interrupted', 'error'))
);

create index if not exists idx_sessions_participant on sessions (participant_id, started_at);

-- ─────────────────────────────────────────────────────────────
-- 4. events — 행동 이벤트 시간순 로그 (EVENT_DICTIONARY.md의 event_type)
--    participant_id / session_id 가 nullable 인 이유:
--    app_opened 는 참여자 코드 입력 '전'에도 발생하므로(EVENT_DICTIONARY),
--    그 시점엔 참여자·세션을 아직 알 수 없다. 인증 이후 이벤트는 항상 값이 채워진다.
-- ─────────────────────────────────────────────────────────────
create table if not exists events (
    event_id           uuid        primary key default gen_random_uuid(),
    participant_id     text        references participants(participant_id),
    session_id         uuid        references sessions(session_id),
    system_version_id  uuid        not null references system_versions(system_version_id),
    event_type         text        not null,
    occurred_at        timestamptz not null default now(),
    related_message_id uuid,                                -- messages 테이블 생성 후 FK 추가
    payload_json       jsonb
);

create index if not exists idx_events_participant_time on events (participant_id, occurred_at);
create index if not exists idx_events_type on events (event_type);

-- ─────────────────────────────────────────────────────────────
-- RLS: 전 테이블 활성화 (정책 없음 = 외부 접근 전면 차단)
-- ─────────────────────────────────────────────────────────────
alter table system_versions enable row level security;
alter table participants    enable row level security;
alter table sessions        enable row level security;
alter table events          enable row level security;

-- ─────────────────────────────────────────────────────────────
-- 초기 시스템 버전 1건 (현재 활성)
-- ─────────────────────────────────────────────────────────────
insert into system_versions (app_version, nudge_rule_version, safety_rule_version, change_note)
select '0.1.0', 'v0.1', 'v0.1', 'Phase 1 초기 골격 (참여자·세션·이벤트)'
where not exists (select 1 from system_versions where deactivated_at is null);
