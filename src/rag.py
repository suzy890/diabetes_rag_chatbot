"""검색 및 근거 기반 답변 (architecture.md).

책임: 질문 임베딩 요청 → 청크 검색 → (T2.6에서) 근거 기반 답변.
- 화면 렌더링은 하지 않는다.
- 외부 임베딩·LLM 호출은 이 모듈 안에 감싼다. 저장은 반드시 database.py를 거친다.
- 질문은 문서 청크와 **같은 임베딩 모델**로 벡터화해야 검색이 된다 (config.EMBED_MODEL).
"""

import time

import httpx

import config
import database


def embed_query(
    text: str,
    participant_id: str | None = None,
    question_message_id: str | None = None,
    system_version_id: str | None = None,
) -> list[float]:
    """질문을 nemotron으로 임베딩한다. 성공·실패와 관계없이 비용을 model_calls에 남긴다."""
    sysver = system_version_id or database.get_active_system_version_id()
    payload = {"model": config.EMBED_MODEL, "input": [text],
               "encoding_format": "float", "input_type": "query", "truncate": "END"}
    started = time.perf_counter()
    status, tokens, vec = "success", 0, None
    try:
        r = httpx.post(f"{config.NVIDIA_BASE_URL}/embeddings",
                       headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                       json=payload, timeout=60.0)
        r.raise_for_status()
        body = r.json()
        vec = body["data"][0]["embedding"]
        tokens = body.get("usage", {}).get("total_tokens", 0)
    except Exception:
        status = "failure"
        raise
    finally:
        database.log_model_call(
            call_type="query_embedding", system_version_id=sysver,
            provider="nvidia", model_name=config.EMBED_MODEL, input_tokens=tokens,
            latency_ms=int((time.perf_counter() - started) * 1000), status=status,
            participant_id=participant_id, related_message_id=question_message_id)
    return vec


def retrieve(
    query_text: str,
    session_id: str,
    participant_id: str,
    question_message_id: str,
    top_k: int = 5,
) -> dict:
    """질문 → 임베딩 → 검색 → 검색 로그 기록. {retrieval_id, chunks} 를 돌려준다.

    검색 1회는 retrieval_logs 1행, 검색된 청크는 청크당 retrieval_chunks 1행으로 남긴다(D15).
    근거 충분성 판단(evidence_level)과 답변 생성은 다음 단계(T2.6)에서 채운다.
    """
    sysver = database.get_active_system_version_id()
    vec = embed_query(query_text, participant_id, question_message_id, sysver)
    chunks = database.search_chunks(vec, top_k)
    retrieval_id = database.save_retrieval_log(
        session_id=session_id, participant_id=participant_id,
        question_message_id=question_message_id, system_version_id=sysver,
        query_text=query_text, embedding_model=config.EMBED_MODEL, top_k=top_k,
        knowledge_base_version=config.EMBED_VERSION)
    database.save_retrieval_chunks(retrieval_id, chunks)
    return {"retrieval_id": retrieval_id, "chunks": chunks}
