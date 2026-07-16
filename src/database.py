"""Supabase 저장·조회 담당. 다른 모듈은 여기를 거쳐서만 DB에 접근한다 (architecture.md 규칙)."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

import config

# PostgREST가 "테이블 없음"을 알릴 때 쓰는 신호들.
# 이 오류가 나면 접속·인증은 성공했고 스키마만 아직 없다는 뜻이다.
_TABLE_MISSING_HINTS = ("PGRST205", "does not exist", "Could not find the table")


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Supabase 클라이언트를 만든다 (한 번만 생성해 재사용)."""
    config.check_secrets()
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def check_connection() -> tuple[bool, str]:
    """DB에 실제로 붙는지 확인한다. (연결 성공 여부, 설명) 을 돌려준다."""
    try:
        client = get_client()
    except Exception as exc:
        return False, f"설정 오류: {exc}"

    try:
        client.table("participants").select("participant_id").limit(1).execute()
        return True, "연결 성공 — participants 테이블 조회됨"
    except Exception as exc:
        message = str(exc)
        if any(hint in message for hint in _TABLE_MISSING_HINTS):
            return True, "연결 성공 — 인증 통과, 아직 테이블 없음"
        return False, f"연결 실패: {message}"


@lru_cache(maxsize=1)
def get_active_system_version_id() -> str:
    """현재 활성 시스템 버전. 모든 연구 기록에 붙는다 (research-data.md 필수 규칙)."""
    rows = (
        get_client().table("system_versions").select("system_version_id")
        .is_("deactivated_at", "null").order("activated_at", desc=True).limit(1)
        .execute().data
    )
    if not rows:
        raise RuntimeError("활성 system_versions 행이 없습니다.")
    return rows[0]["system_version_id"]


def get_participant(participant_id: str) -> dict | None:
    """참여자 명단에서 코드를 찾는다. 없으면 None."""
    rows = (
        get_client().table("participants").select("*")
        .eq("participant_id", participant_id).limit(1)
        .execute().data
    )
    return rows[0] if rows else None


def find_open_session(participant_id: str) -> dict | None:
    """아직 끝나지 않았고 최근에 시작된 세션을 찾는다.

    새로고침으로 세션이 중복 생성되는 것을 막는 핵심 장치다 (research-data.md).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.SESSION_RESUME_HOURS)
    rows = (
        get_client().table("sessions").select("*")
        .eq("participant_id", participant_id)
        .is_("ended_at", "null")
        .gte("started_at", cutoff.isoformat())
        .order("started_at", desc=True).limit(1)
        .execute().data
    )
    return rows[0] if rows else None


def create_session(participant_id: str, device_type: str | None = None) -> dict:
    """새 접속 세션을 만든다."""
    row: dict[str, Any] = {
        "participant_id": participant_id,
        "system_version_id": get_active_system_version_id(),
    }
    if device_type:
        row["device_type"] = device_type
    return get_client().table("sessions").insert(row).execute().data[0]


def save_message(
    session_id: str,
    participant_id: str,
    role: str,
    message_type: str,
    content: str,
) -> dict:
    """대화 메시지를 저장한다.

    role(누가 보냈나)과 message_type(연구적으로 어떤 성격인가)을 분리해 기록한다.
    """
    row = {
        "session_id": session_id,
        "participant_id": participant_id,
        "system_version_id": get_active_system_version_id(),
        "role": role,
        "message_type": message_type,
        "content": content,
    }
    return get_client().table("messages").insert(row).execute().data[0]


def get_messages(session_id: str) -> list[dict]:
    """세션의 대화를 시간순으로 불러온다.

    화면 상태가 아니라 DB를 진실의 원천으로 삼는다 → 새로고침해도 대화가 복원된다.
    """
    return (
        get_client().table("messages").select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute().data
    )


def log_event(
    event_type: str,
    participant_id: str | None = None,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
    related_message_id: str | None = None,
) -> None:
    """행동 이벤트를 기록한다.

    participant_id·session_id는 인증 전 이벤트(app_opened)에서는 비어 있을 수 있다.
    """
    row: dict[str, Any] = {
        "event_type": event_type,
        "system_version_id": get_active_system_version_id(),
    }
    if participant_id:
        row["participant_id"] = participant_id
    if session_id:
        row["session_id"] = session_id
    if payload:
        row["payload_json"] = payload
    if related_message_id:
        row["related_message_id"] = related_message_id
    get_client().table("events").insert(row).execute()


def count_nudges_today(
    participant_id: str, day_start: datetime, template_key: str | None = None
) -> int:
    """참여자 기준 '오늘' 이미 노출된 넛지 수. 반복 제한 판단에 쓴다 (NUDGE_RULES.md)."""
    query = (
        get_client().table("nudge_events").select("nudge_id", count="exact")
        .eq("participant_id", participant_id)
        .not_.is_("displayed_at", "null")
        .gte("scheduled_at", day_start.isoformat())
    )
    if template_key:
        query = query.eq("template_key", template_key)
    return query.execute().count or 0


def create_nudge(
    participant_id: str, session_id: str, template: dict, message_id: str
) -> dict:
    """넛지를 기록한다. 예정(scheduled_at)과 실제 노출(displayed_at)을 함께 남긴다.

    MVP는 접속 시점 트리거라 예정과 노출이 사실상 동시지만, 두 시각을 분리해 저장한다.
    (향후 예약 넛지에서는 '예정됐지만 앱을 안 열어 노출 안 됨'이 생기기 때문)
    """
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "participant_id": participant_id,
        "session_id": session_id,
        "system_version_id": get_active_system_version_id(),
        "message_id": message_id,
        "trigger_type": "app_open",
        "health_domain": template["health_domain"],
        "nudge_type": template["nudge_type"],
        "template_key": template["key"],
        "template_version": template["template_version"],
        "scheduled_at": now,
        "displayed_at": now,
        "status": "displayed",
        "context_json": template.get("context") or {},
    }
    return get_client().table("nudge_events").insert(row).execute().data[0]


def set_action_commitment(nudge_id: str, action: str) -> None:
    """넛지의 행동 제안에 참여자가 '하겠다'고 약속한 행동을 기록한다 (종단 추적의 출발점).

    행동의도(하겠다)와 실제 수행(했다)을 분리 기록한다는 원칙에서, 여기는 '의도' 쪽이다.
    (추후 확인은 Phase 3의 action_followups)
    """
    (get_client().table("nudge_events")
     .update({"action_commitment": action}).eq("nudge_id", nudge_id).execute())


def get_unanswered_nudge(participant_id: str, session_id: str) -> dict | None:
    """이 세션에서 노출됐지만 아직 답하지 않은 넛지. 새로고침해도 선택지가 살아있게 한다."""
    rows = (
        get_client().table("nudge_events").select("*")
        .eq("participant_id", participant_id)
        .eq("session_id", session_id)
        .eq("status", "displayed")
        .order("displayed_at", desc=True).limit(1)
        .execute().data
    )
    return rows[0] if rows else None


def record_nudge_response(nudge_id: str, response: str) -> None:
    """넛지에 대한 사용자의 반응을 기록한다."""
    (
        get_client().table("nudge_events")
        .update({
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "response": response,
            "status": "answered",
        })
        .eq("nudge_id", nudge_id)
        .execute()
    )


def log_technical_error(
    error_type: str,
    error_message: str,
    participant_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """기술 오류를 연구 행동 데이터와 분리해 기록한다 (research-data.md).

    사용자의 무응답이 '무관심'인지 '시스템 실패'인지 구분하기 위함이다.
    오류 기록 자체가 실패해도 앱을 멈추지는 않는다.
    """
    row: dict[str, Any] = {"error_type": error_type, "error_message": error_message[:2000]}
    if participant_id:
        row["participant_id"] = participant_id
    if session_id:
        row["session_id"] = session_id
    try:
        get_client().table("technical_errors").insert(row).execute()
    except Exception:
        pass


def list_documents() -> list[dict]:
    """등록된 문서 목록을 돌려준다 (출처 표시·매핑 등 실행 앱에서 사용)."""
    return get_client().table("documents").select("*").execute().data


def log_model_call(
    call_type: str,
    system_version_id: str,
    provider: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    status: str = "success",
    participant_id: str | None = None,
    related_message_id: str | None = None,
) -> None:
    """외부 API 호출의 토큰·지연시간·상태를 model_calls에 남긴다 (비용 추적)."""
    row: dict[str, Any] = {
        "call_type": call_type, "system_version_id": system_version_id,
        "provider": provider, "model_name": model_name,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "latency_ms": latency_ms, "status": status,
    }
    if participant_id:
        row["participant_id"] = participant_id
    if related_message_id:
        row["related_message_id"] = related_message_id
    get_client().table("model_calls").insert(row).execute()


def search_chunks(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """질문 벡터로 가장 가까운 활성 청크 top-k를 찾는다 (pgvector 검색 함수 호출).
    각 결과: chunk_id·document_id·content·page_number·similarity(코사인, 1이 가장 가까움).
    """
    vec = "[" + ",".join(repr(x) for x in query_embedding) + "]"
    return get_client().rpc(
        "match_document_chunks", {"query_embedding": vec, "match_count": top_k}
    ).execute().data


def hybrid_search(query_embedding: list[float], keywords: list[str],
                  top_k: int = 5, vec_weight: float = 0.7) -> list[dict]:
    """벡터 유사도 + 키워드 일치를 합쳐 청크를 찾는다 (하이브리드, T2.9).
    각 결과에 similarity(코사인, 근거 판단용)와 score(융합, 정렬용)가 함께 온다.
    keywords가 비면 벡터 검색과 동일하게 동작한다.
    """
    vec = "[" + ",".join(repr(x) for x in query_embedding) + "]"
    return get_client().rpc("hybrid_match_chunks", {
        "query_embedding": vec, "keywords": keywords,
        "match_count": top_k, "vec_weight": vec_weight,
    }).execute().data


def save_retrieval_log(
    session_id: str,
    participant_id: str,
    question_message_id: str,
    system_version_id: str,
    query_text: str,
    embedding_model: str,
    top_k: int,
    knowledge_base_version: str,
    evidence_level: str | None = None,
    answer_message_id: str | None = None,
) -> str:
    """검색 1회를 retrieval_logs에 1행 저장하고 retrieval_id를 돌려준다 (D15)."""
    row: dict[str, Any] = {
        "session_id": session_id, "participant_id": participant_id,
        "question_message_id": question_message_id, "system_version_id": system_version_id,
        "query_text": query_text, "embedding_model": embedding_model, "top_k": top_k,
        "knowledge_base_version": knowledge_base_version, "evidence_level": evidence_level,
    }
    if answer_message_id:
        row["answer_message_id"] = answer_message_id
    return get_client().table("retrieval_logs").insert(row).execute().data[0]["retrieval_id"]


def update_retrieval_answer(retrieval_id: str, answer_message_id: str) -> None:
    """검색 로그에 생성된 답변 메시지를 연결한다 (검색↔답변 연결, D15)."""
    (get_client().table("retrieval_logs")
     .update({"answer_message_id": answer_message_id})
     .eq("retrieval_id", retrieval_id).execute())


def save_retrieval_chunks(retrieval_id: str, ranked: list[dict],
                          selected_ids: set[str] | None = None) -> int:
    """검색된 청크를 청크당 1행으로 저장한다 (순위·유사도·채택여부, D15)."""
    selected = selected_ids or set()
    rows = [{
        "retrieval_id": retrieval_id, "chunk_id": r["chunk_id"], "rank": i + 1,
        "similarity_score": r.get("similarity"),
        "was_selected": r["chunk_id"] in selected,
    } for i, r in enumerate(ranked)]
    if not rows:
        return 0
    return len(get_client().table("retrieval_chunks").insert(rows).execute().data)
