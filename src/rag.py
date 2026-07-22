"""검색 및 근거 기반 답변 (architecture.md).

책임: 질문 임베딩 → 청크 검색 → 근거 충분성 판단(3단계) → 근거 기반 답변.
- 화면 렌더링은 하지 않는다.
- 외부 임베딩·LLM 호출은 이 모듈 안에 감싼다. 저장은 반드시 database.py를 거친다.
- 질문은 문서 청크와 **같은 임베딩 모델**로 벡터화해야 검색이 된다 (config.EMBED_MODEL).
- 답변은 검색된 근거 범위 안에서만 하고, 근거에 없는 수치는 말하지 않는다 (D31).
"""

import json
import re
from functools import lru_cache
from pathlib import Path

import config
import database
import llm_client

# 키워드 추출 시 떼어낼 흔한 조사 (긴 것부터 — "으로"를 "로"보다 먼저 검사)
_JOSA = ("으로", "에서", "에게", "까지", "부터", "이나", "라고", "은", "는", "이", "가",
         "을", "를", "의", "에", "도", "만", "과", "와", "로")

# 근거 부족(보류) 시 고정 안내문. ⚠️ 문구는 의료전문가 검토 대상 (SAFETY_RULES).
INSUFFICIENT_MSG = (
    "현재 안내 자료에서 이 질문에 대한 충분한 근거를 찾지 못했습니다. "
    "정확한 내용은 담당 의료진이나 약사와 상의해 주세요."
)


@lru_cache(maxsize=1)
def _social() -> dict:
    """잡담 응답 템플릿을 파일에서 읽는다 (친근한 대화용)."""
    return json.loads((Path(__file__).resolve().parent.parent
                       / "prompts" / "social_replies.json").read_text(encoding="utf-8"))


def detect_social(text: str) -> str | None:
    """질문이 아니라 '사회적 인사·잡담'이면 따뜻한 응답 문구를 돌려준다.

    건강 관련 단어가 섞이면(guard) 잡담으로 처리하지 않고 그대로 RAG로 보낸다(안전 우선).
    짧은 발화만 대상으로 해 실제 질문을 잘못 가로채지 않는다.
    """
    data = _social()
    if len(text) > data["max_len"] or any(h in text for h in data["health_guard"]):
        return None
    for entry in data["replies"]:
        if any(k in text for k in entry["keys"]):
            return entry["reply"]
    return None


def is_health_related(text: str) -> bool:
    """질문에 건강/당뇨 관련 단어가 있는지. 없으면 '당뇨와 완전 무관한 질문'으로 본다."""
    return any(h in text for h in _social()["health_guard"])


@lru_cache(maxsize=4)
def _prompt(name: str) -> str:
    """prompts/<name>.md 시스템 프롬프트를 읽는다 (HTML 주석 헤더는 제외)."""
    text = (Path(__file__).resolve().parent.parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    return text.split("-->", 1)[-1].strip()


def embed_query(
    text: str,
    participant_id: str | None = None,
    question_message_id: str | None = None,
    system_version_id: str | None = None,
) -> list[float]:
    """질문을 nemotron으로 임베딩한다. 비용은 공통 배관이 model_calls에 남긴다."""
    sysver = system_version_id or database.get_active_system_version_id()
    payload = {"model": config.EMBED_MODEL, "input": [text],
               "encoding_format": "float", "input_type": "query", "truncate": "END"}
    body = llm_client.call("embeddings", payload, "query_embedding", sysver,
                           participant_id, question_message_id)
    return body["data"][0]["embedding"]


def extract_keywords(text: str) -> list[str]:
    """질문에서 정확 매칭용 키워드를 뽑는다 (하이브리드 검색용).

    3글자 이상 토큰만 쓰고, 흔한 조사를 떼어낸 어간도 함께 넣는다.
    예: "당화혈색소가" → "당화혈색소가"와 "당화혈색소" 둘 다 → 문서의 "당화혈색소는"과도 매칭.
    """
    terms: set[str] = set()
    for tok in re.findall(r"[가-힣A-Za-z0-9]+", text):
        if len(tok) < 3:  # 짧은 토큰은 조사·불용어일 가능성이 커서 버린다
            continue
        terms.add(tok)
        for josa in _JOSA:
            if tok.endswith(josa) and len(tok) - len(josa) >= 2:
                terms.add(tok[:-len(josa)])
                break
    return list(terms)


# 모호 용어 되묻기 규칙 (승인 용어 사전 §1-1, 잠정 — 의료검토 대기).
# "혈당"은 순간 혈당(공복/식후)일 수도, 당화혈색소(3개월 평균)일 수도 있어 답이 달라진다.
_CLARIFY_TERMS = ("혈당", "당수치", "당 수치")
# 이미 구체적으로 특정된 표현이면 되묻지 않는다.
_ALREADY_SPECIFIC = ("공복", "식후", "당화혈색소", "에이원씨", "a1c", "A1C")
_ASKS_JUDGMENT = ("괜찮", "정상", "높은", "낮은", "위험", "괜찬")
CLARIFY_OPTIONS = ["평소에 재시는 혈당", "병원에서 3개월마다 재는 수치 (당화혈색소)", "잘 모르겠어요"]


def detect_clarification(query_text: str) -> dict | None:
    """질문이 '되물어야 하는 모호함'을 담고 있는지 규칙으로 판별한다 (RAG_RULES §3-1).

    되묻는 경우: '혈당'류 표현 + (수치가 있거나 '괜찮은지'를 물음) → 답이 달라지므로.
    되묻지 않는 경우: 이미 공복/식후/당화혈색소로 특정됐거나, 일반 질문.
    반환: {term, options} 또는 None. (LLM이 아니라 규칙으로만 판단한다.)
    """
    if any(t in query_text for t in _ALREADY_SPECIFIC):
        return None
    if not any(t in query_text for t in _CLARIFY_TERMS):
        return None
    has_number = bool(re.search(r"\d", query_text))
    asks_judgment = any(t in query_text for t in _ASKS_JUDGMENT)
    if has_number or asks_judgment:
        return {"term": "혈당", "options": CLARIFY_OPTIONS}
    return None


def judge_evidence(chunks: list[dict]) -> str:
    """검색된 청크 중 코사인 유사도가 가장 높은 값으로 근거 충분성을 3단계로 가른다 (RAG_RULES §3).

    검색은 하이브리드(벡터+키워드)로 하되, 근거 '충분성' 판단은 보정된 코사인
    유사도로 한다. 융합 점수로 판단하면 임계값(코사인 기준)과 어긋나 보류가 흔들린다.
    청크는 융합 점수 순으로 오므로 chunks[0]이 코사인 최고가 아닐 수 있다 → 최댓값으로 본다.
    (키워드로 끌어올린 청크가 1위여도, 실제 근거가 되는 고유사도 청크를 놓치지 않게.)
    → 검색 품질과 판단 임계값의 정합은 파일럿 튜닝 대상(U4).
    """
    if not chunks:
        return "insufficient"
    top = max(c.get("similarity", 0.0) for c in chunks)
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
    # 하이브리드: 벡터 유사도 + 질문 속 정확 용어("당화혈색소" 등) 키워드 매칭 (T2.9)
    chunks = database.hybrid_search(vec, extract_keywords(query_text), top_k)
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


def answer_stream(
    query_text: str,
    selected: list[dict],
    level: str,
    participant_id: str | None,
    question_message_id: str | None,
    system_version_id: str,
    history: list | None = None,
):
    """선택된 근거로 답변을 스트리밍한다(generator). history(최근 대화)를 함께 보내 맥락을 잇는다.
    'detailed thinking off' 프롬프트로 장황한 영어 추론을 억제해 잘림·영어누출을 막는다.
    """
    if level == "insufficient" or not selected:
        if is_health_related(query_text):
            yield INSUFFICIENT_MSG          # 건강 질문인데 근거 없음 → 안전 보류
            return
        # 당뇨와 무관한 질문 → LLM이 친근하게 자연 대화(의료 조언 금지·건강질문 유도, 프롬프트로 제약)
        payload = {"model": config.LLM_MODEL, "temperature": 0.5, "max_tokens": 300,
                   "messages": [{"role": "system", "content": _prompt("offtopic_system")}]
                   + (history or []) + [{"role": "user", "content": query_text}]}
        yield from llm_client.stream(payload, "rag_answer", system_version_id,
                                     participant_id, question_message_id)
        return
    evidence = "\n\n".join(
        f"[근거{i}] (출처: {c.get('title', '문서')} {c.get('page_number', '')}쪽)\n{c['content']}"
        for i, c in enumerate(selected, 1))
    messages = ([{"role": "system", "content": _prompt("rag_answer_system") + "\n\n[근거]\n" + evidence}]
                + (history or []) + [{"role": "user", "content": query_text}])
    payload = {"model": config.LLM_MODEL, "messages": messages,
               "temperature": config.LLM_TEMPERATURE, "max_tokens": 1024}
    yield from llm_client.stream(payload, "rag_answer", system_version_id,
                                 participant_id, question_message_id)


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

    # 비스트리밍 경로(테스트 등): 스트림을 모아 전체 답변을 만든다.
    answer = "".join(answer_stream(query_text, selected, r["evidence_level"],
                                   participant_id, question_message_id, sysver))
    msg = database.save_message(session_id, participant_id, "assistant", "rag_answer", answer)
    database.update_retrieval_answer(r["retrieval_id"], msg["message_id"])

    sources = [{"title": c["title"], "page": c.get("page_number")} for c in selected]
    return {"answer": answer, "evidence_level": r["evidence_level"], "sources": sources,
            "retrieval_id": r["retrieval_id"], "answer_message_id": msg["message_id"]}
