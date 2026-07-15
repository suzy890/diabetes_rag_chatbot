"""검색 및 근거 기반 답변 (architecture.md).

책임: 질문 임베딩 → 청크 검색 → 근거 충분성 판단(3단계) → 근거 기반 답변.
- 화면 렌더링은 하지 않는다.
- 외부 임베딩·LLM 호출은 이 모듈 안에 감싼다. 저장은 반드시 database.py를 거친다.
- 질문은 문서 청크와 **같은 임베딩 모델**로 벡터화해야 검색이 된다 (config.EMBED_MODEL).
- 답변은 검색된 근거 범위 안에서만 하고, 근거에 없는 수치는 말하지 않는다 (D31).
"""

import time
from functools import lru_cache
from pathlib import Path

import httpx

import config
import database

# 근거 부족(보류) 시 고정 안내문. ⚠️ 문구는 의료전문가 검토 대상 (SAFETY_RULES).
INSUFFICIENT_MSG = (
    "현재 안내 자료에서 이 질문에 대한 충분한 근거를 찾지 못했습니다. "
    "정확한 내용은 담당 의료진이나 약사와 상의해 주세요."
)


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    """답변 생성용 시스템 프롬프트를 파일에서 읽는다 (HTML 주석 헤더는 제외)."""
    text = (Path(__file__).resolve().parent.parent / "prompts" / "rag_answer_system.md").read_text(encoding="utf-8")
    return text.split("-->", 1)[-1].strip()


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


def judge_evidence(chunks: list[dict]) -> str:
    """최상위 청크 유사도로 근거 충분성을 3단계로 가른다 (RAG_RULES §3)."""
    if not chunks:
        return "insufficient"
    top = chunks[0].get("similarity", 0.0)
    if top < config.EVIDENCE_LOWER:
        return "insufficient"
    if top >= config.EVIDENCE_UPPER:
        return "sufficient"
    return "partial"


def retrieve(
    query_text: str,
    session_id: str,
    participant_id: str,
    question_message_id: str,
    top_k: int | None = None,
) -> dict:
    """질문 → 임베딩 → 검색 → 충분성 판단 → 검색 로그 기록.

    검색 1회는 retrieval_logs 1행, 검색된 청크는 청크당 retrieval_chunks 1행으로 남긴다(D15).
    답변에 넣을 청크(하한 이상 상위 N개)는 was_selected=true로 표시한다.
    """
    top_k = top_k or config.RAG_TOP_K
    sysver = database.get_active_system_version_id()
    vec = embed_query(query_text, participant_id, question_message_id, sysver)
    chunks = database.search_chunks(vec, top_k)
    level = judge_evidence(chunks)
    # 근거가 '부족'이면 아무것도 선택하지 않는다(보류). 아니면 하한 이상 상위 N개.
    selected = ([] if level == "insufficient" else
                [c for c in chunks if c.get("similarity", 0.0) >= config.EVIDENCE_LOWER][:config.RAG_SELECT_N])
    selected_ids = {c["chunk_id"] for c in selected}
    retrieval_id = database.save_retrieval_log(
        session_id=session_id, participant_id=participant_id,
        question_message_id=question_message_id, system_version_id=sysver,
        query_text=query_text, embedding_model=config.EMBED_MODEL, top_k=top_k,
        knowledge_base_version=config.EMBED_VERSION, evidence_level=level)
    database.save_retrieval_chunks(retrieval_id, chunks, selected_ids=selected_ids)
    return {"retrieval_id": retrieval_id, "chunks": chunks,
            "evidence_level": level, "selected": selected}


def generate_answer(
    query_text: str,
    selected: list[dict],
    level: str,
    participant_id: str | None,
    question_message_id: str | None,
    system_version_id: str,
) -> str:
    """선택된 근거로 답변을 만든다. 근거 부족이면 LLM을 부르지 않고 고정 안내문을 돌려준다."""
    if level == "insufficient" or not selected:
        return INSUFFICIENT_MSG

    evidence = "\n\n".join(
        f"[근거{i}] (출처: {c.get('title', '문서')} {c.get('page_number', '')}쪽)\n{c['content']}"
        for i, c in enumerate(selected, 1))
    messages = [
        {"role": "system", "content": _system_prompt() + "\n\n[근거]\n" + evidence},
        {"role": "user", "content": query_text},
    ]
    payload = {"model": config.LLM_MODEL, "messages": messages,
               "temperature": config.LLM_TEMPERATURE, "max_tokens": 500}
    started = time.perf_counter()
    status, itok, otok, answer = "success", 0, 0, ""
    try:
        r = httpx.post(f"{config.NVIDIA_BASE_URL}/chat/completions",
                       headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                       json=payload, timeout=90.0)
        r.raise_for_status()
        body = r.json()
        answer = body["choices"][0]["message"]["content"].strip()
        usage = body.get("usage", {})
        itok, otok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception:
        status = "failure"
        raise
    finally:
        database.log_model_call(
            call_type="rag_answer", system_version_id=system_version_id,
            provider="nvidia", model_name=config.LLM_MODEL, input_tokens=itok,
            output_tokens=otok, latency_ms=int((time.perf_counter() - started) * 1000),
            status=status, participant_id=participant_id, related_message_id=question_message_id)
    return answer


def respond(
    query_text: str,
    session_id: str,
    participant_id: str,
    question_message_id: str,
) -> dict:
    """검색+판단+답변까지의 전체 흐름. {answer, evidence_level, sources, ...} 를 돌려준다."""
    sysver = database.get_active_system_version_id()
    r = retrieve(query_text, session_id, participant_id, question_message_id)
    # 선택 청크에 문서 제목을 붙인다(출처 표시·근거 라벨용).
    titles = {d["document_id"]: d["title"] for d in database.list_documents()}
    selected = [{**c, "title": titles.get(c["document_id"], "문서")} for c in r["selected"]]

    answer = generate_answer(query_text, selected, r["evidence_level"],
                             participant_id, question_message_id, sysver)
    msg = database.save_message(session_id=session_id, participant_id=participant_id,
                                role="assistant", message_type="rag_answer", content=answer)
    database.update_retrieval_answer(r["retrieval_id"], msg["message_id"])

    sources = [{"title": c["title"], "page": c.get("page_number")} for c in selected]
    return {"answer": answer, "evidence_level": r["evidence_level"], "sources": sources,
            "retrieval_id": r["retrieval_id"], "answer_message_id": msg["message_id"]}
