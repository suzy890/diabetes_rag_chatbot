-- schema.sql — 연구 데이터 테이블 정의 (현재 DB 상태와 일치)
-- 근거: DATA_SCHEMA.md · EVENT_DICTIONARY.md · .claude/rules/research-data.md
-- Phase 1(첫 슬라이스)에 필요한 최소 테이블만 생성한다. 나머지는 해당 기능을 만들 때 추가.
--
-- 보안: 모든 테이블에 RLS를 켜고 정책을 만들지 않는다
--       → 외부(anon/authenticated)는 읽기·쓰기 모두 차단.
--       → 앱 서버가 쓰는 secret 키(service_role)만 RLS를 우회해 기록 가능.

-- ─────────────────────────────────────────────────────────────
-- 1. system_versions — 어떤 설정으로 중재했는지 추적 (연구 재현성)
--    모든 연구 이벤트가 이 버전을 참조한다.
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
--    participant_id를 PK로 두는 이유: 연구 코드는 한 번 부여하면 바뀌지 않고,
--    CSV로 내보낼 때 사람이 읽을 수 있어야 분석이 편하다.
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
--    app_version 컬럼은 두지 않는다: 웹앱은 '기기에 설치된 버전'이 없으므로
--    system_version_id 로 앱 버전을 알 수 있다 (중복·불일치 방지).
-- ─────────────────────────────────────────────────────────────
create table if not exists sessions (
    session_id        uuid        primary key default gen_random_uuid(),
    participant_id    text        not null references participants(participant_id),
    system_version_id uuid        not null references system_versions(system_version_id),
    started_at        timestamptz not null default now(),
    ended_at          timestamptz,
    device_type       text        check (device_type in ('mobile', 'tablet', 'desktop')),
    completion_status text        check (completion_status in ('normal', 'interrupted', 'error')),
    -- events가 (session_id, participant_id) 복합 FK를 걸 수 있도록 하는 대상 키
    constraint sessions_session_participant_uniq unique (session_id, participant_id)
);

create index if not exists idx_sessions_participant on sessions (participant_id, started_at);

-- ─────────────────────────────────────────────────────────────
-- 4. events — 행동 이벤트 시간순 로그 (EVENT_DICTIONARY.md의 event_type)
--    participant_id / session_id 가 nullable 인 이유:
--    app_opened 는 참여자 코드 입력 '전'에도 발생하므로 그 시점엔 참여자·세션을 알 수 없다.
--    인증 이후 이벤트는 항상 두 값이 채워진다.
-- ─────────────────────────────────────────────────────────────
create table if not exists events (
    event_id           uuid        primary key default gen_random_uuid(),
    participant_id     text        references participants(participant_id),
    session_id         uuid        references sessions(session_id),
    system_version_id  uuid        not null references system_versions(system_version_id),
    event_type         text        not null,
    occurred_at        timestamptz not null default now(),
    related_message_id uuid,                                -- messages 테이블 생성 후 FK 추가
    payload_json       jsonb,
    -- 참여자·세션 일관성을 DB가 원천 보장한다.
    -- ("P001의 세션인데 이벤트는 P002" 저장 불가)
    -- 둘 중 하나가 NULL이면(인증 전 app_opened) 검사를 건너뛴다.
    constraint events_session_participant_fk
        foreign key (session_id, participant_id)
        references sessions (session_id, participant_id)
);

create index if not exists idx_events_participant_time on events (participant_id, occurred_at);
create index if not exists idx_events_session on events (session_id);
create index if not exists idx_events_type on events (event_type);

-- ─────────────────────────────────────────────────────────────
-- 5. messages — 채팅창에 나타난 모든 메시지 (사용자·AI)
--    role(누가 보냈나)과 message_type(연구적으로 어떤 성격인가)을 분리한다.
--    AI가 보낸 메시지라도 넛지인지 RAG 답변인지 안전 안내인지 의미가 다르기 때문.
-- ─────────────────────────────────────────────────────────────
create table if not exists messages (
    message_id        uuid        primary key default gen_random_uuid(),
    session_id        uuid        not null,
    participant_id    text        not null,
    system_version_id uuid        not null references system_versions(system_version_id),
    role              text        not null check (role in ('user', 'assistant', 'system')),
    message_type      text        not null check (message_type in (
                          'nudge', 'nudge_response', 'rag_question', 'rag_answer',
                          'safety_message', 'free_text', 'system_notice')),
    content           text        not null,
    created_at        timestamptz not null default now(),
    -- 참여자·세션 일관성을 DB가 원천 보장 (events와 동일 원칙)
    constraint messages_session_participant_fk
        foreign key (session_id, participant_id)
        references sessions (session_id, participant_id)
);

create index if not exists idx_messages_session_time on messages (session_id, created_at);

-- messages가 생겼으므로 events.related_message_id 의 FK를 연결한다.
alter table events
    add constraint events_related_message_fk
    foreign key (related_message_id) references messages (message_id);

-- ─────────────────────────────────────────────────────────────
-- 6. nudge_events — 넛지의 예정·노출·반응 (넛지 연구의 핵심 테이블)
--    예정 시각(scheduled_at)과 실제 노출 시각(displayed_at)을 분리한다:
--    앱을 열지 않으면 예정은 됐어도 노출되지 않기 때문.
-- ─────────────────────────────────────────────────────────────
create table if not exists nudge_events (
    nudge_id          uuid        primary key default gen_random_uuid(),
    participant_id    text        not null references participants(participant_id),
    session_id        uuid,
    system_version_id uuid        not null references system_versions(system_version_id),
    message_id        uuid        references messages(message_id),   -- 실제로 보여준 메시지
    trigger_type      text        not null
                      check (trigger_type in ('app_open', 'scheduled', 'behavior_based')),
    health_domain     text        not null
                      check (health_domain in ('meal', 'exercise', 'medication', 'glucose')),
    nudge_type        text        not null
                      check (nudge_type in ('info', 'choice', 'small_action', 'self_efficacy')),
    template_key      text        not null,     -- 어떤 템플릿이 떴는지 (템플릿별 반응률 분석용)
    template_version  text        not null,
    scheduled_at      timestamptz not null default now(),
    displayed_at      timestamptz,
    responded_at      timestamptz,
    response          text,
    action_commitment text,
    status            text        not null default 'scheduled'
                      check (status in ('scheduled', 'displayed', 'answered', 'no_response', 'completed')),
    context_json      jsonb,      -- 노출 당시 맥락 (수집 우선 원칙)
    constraint nudge_session_participant_fk
        foreign key (session_id, participant_id)
        references sessions (session_id, participant_id)
);

create index if not exists idx_nudge_participant_time on nudge_events (participant_id, scheduled_at);
create index if not exists idx_nudge_status on nudge_events (participant_id, status);

-- ─────────────────────────────────────────────────────────────
-- 7. technical_errors — 기술 오류 (연구 행동 데이터와 분리)
--    사용자의 무응답이 '실제 무관심'인지 '시스템 실패'인지 구분하기 위함.
-- ─────────────────────────────────────────────────────────────
create table if not exists technical_errors (
    error_id        uuid        primary key default gen_random_uuid(),
    participant_id  text        references participants(participant_id),
    session_id      uuid        references sessions(session_id),
    error_type      text        not null,
    error_message   text        not null,
    occurred_at     timestamptz not null default now(),
    resolved_status text        not null default 'open'
                    check (resolved_status in ('open', 'investigating', 'resolved', 'ignored'))
);

create index if not exists idx_tech_errors_time on technical_errors (occurred_at);
create index if not exists idx_tech_errors_type on technical_errors (error_type);

-- ─────────────────────────────────────────────────────────────
-- RLS: 전 테이블 활성화 (정책 없음 = 외부 접근 전면 차단)
-- ─────────────────────────────────────────────────────────────
alter table system_versions  enable row level security;
alter table participants     enable row level security;
alter table sessions         enable row level security;
alter table events           enable row level security;
alter table messages         enable row level security;
alter table nudge_events     enable row level security;
alter table technical_errors enable row level security;

-- ─────────────────────────────────────────────────────────────
-- 초기 시스템 버전 1건 (현재 활성)
-- ─────────────────────────────────────────────────────────────
insert into system_versions (app_version, nudge_rule_version, safety_rule_version, change_note)
select '0.1.0', 'v0.1', 'v0.1', 'Phase 1 초기 골격 (참여자·세션·이벤트)'
where not exists (select 1 from system_versions where deactivated_at is null);
