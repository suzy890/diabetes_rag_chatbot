"""T2.4 — 선정된 청크(basic_512, 정제 적용)를 nemotron으로 임베딩해 저장한다.

파이프라인:
  청크 로드(정제) → 문서 매핑 → nemotron 임베딩(비용 기록) → document_chunks 저장

선정 근거: tests/compare_chunking.py 비교에서 basic_512가 최적
  (정제 후 Recall@5 100% · Top-1 75% · MRR 0.85).

여러 번 실행해도 같은 임베딩 버전이 이미 있으면 저장하지 않는다(중복 방지).

실행: .venv/bin/python scripts/embed_chunks.py
"""

import glob
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

import database  # noqa: E402
import ingest_db  # 시딩 전용 DB 쓰기 (코어 밖)  # noqa: E402
from compare_chunking import clean  # 정제 규칙 재사용  # noqa: E402

load_dotenv()

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
MODEL = "nvidia/llama-nemotron-embed-1b-v2"
EMBEDDING_VERSION = "nemotron-2048-basic512-clean-v1"
CHUNK_DIR = os.path.join(os.path.dirname(__file__), "..",
                         "data", "source_docs", "chunk__embeddings", "chunk_jsons")

# 청크의 source 파일명 → 등록된 문서 제목. (표준교육자료는 청크명 DMhmenu ≠ PDF명 DMmenu)
SOURCE_TO_TITLE = {
    "[당뇨병]권고 요약정보_전자.pdf": "일차 의료용 근거기반 당뇨병 권고 요약 정보",
    "근거기반 당뇨병 환자 관리 정보.pdf": "근거기반 당뇨병 환자 관리 정보",
    "당뇨병 환자에게 필요한 정보_65세 이상.pdf": "노년 당뇨병 환자에게 필요한 정보 (65세 이상)",
    "DMhmenu180514.pdf": "고혈압·당뇨병 표준교육자료: 당뇨병 고급실습과정 교육지침서",
}


def load_basic512() -> dict[str, list[dict]]:
    """basic_512 청크를 문서(source)별로 모아 정제한다. {source: [{index, page, content, n_tokens}]}"""
    docs: dict[str, list[dict]] = {}
    for f in sorted(glob.glob(os.path.join(CHUNK_DIR, "*_512.json"))):
        base = os.path.basename(f)
        if "document" in base or "page" in base:
            continue
        for c in json.load(open(f, encoding="utf-8")):
            cleaned = clean(c["text"])
            if len(cleaned) < 10:            # 순수 잡음 조각은 제외 (비교 실험과 동일 기준)
                continue
            docs.setdefault(c["source"], []).append({
                "index": c["id"], "page": c.get("page"),
                "content": cleaned, "n_tokens": c.get("n_tokens"),
            })
    return docs


def embed(texts: list[str]) -> tuple[list[list[float]], int, float]:
    """텍스트를 nemotron 벡터로 만든다. (벡터목록, 사용토큰, 걸린시간초)"""
    vecs, tokens, elapsed = [], 0, 0.0
    for i in range(0, len(texts), 32):
        payload = {"model": MODEL, "input": texts[i:i + 32], "encoding_format": "float",
                   "input_type": "passage", "truncate": "END"}
        started = time.perf_counter()
        r = httpx.post(f"{BASE_URL}/embeddings",
                       headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=180.0)
        r.raise_for_status()
        elapsed += time.perf_counter() - started
        body = r.json()
        vecs.extend(row["embedding"] for row in sorted(body["data"], key=lambda d: d["index"]))
        tokens += body.get("usage", {}).get("total_tokens", 0)
    return vecs, tokens, elapsed


def to_pgvector(vec: list[float]) -> str:
    """pgvector 입력형식 '[v1,v2,...]' 문자열로 바꾼다."""
    return "[" + ",".join(repr(x) for x in vec) + "]"


def main() -> int:
    if not API_KEY:
        print("LLM_API_KEY가 비어 있습니다.")
        return 1

    ok, msg = database.check_connection()
    print(f"DB 연결: {msg}")
    if not ok:
        return 1

    already = ingest_db.count_chunks(EMBEDDING_VERSION)
    if already:
        print(f"임베딩 버전 '{EMBEDDING_VERSION}'로 이미 {already}청크 저장됨 → 중복 방지로 종료.")
        return 0

    sysver = database.get_active_system_version_id()
    title_to_id = {d["title"]: d["document_id"] for d in database.list_documents()}
    docs = load_basic512()

    total_saved = 0
    for source, chunks in docs.items():
        title = SOURCE_TO_TITLE.get(source)
        doc_id = title_to_id.get(title) if title else None
        if not doc_id:
            print(f"  ⚠️ '{source}' → 매칭되는 문서 없음, 건너뜀")
            continue

        vecs, tokens, elapsed = embed([c["content"] for c in chunks])
        database.log_model_call(
            call_type="document_embedding", system_version_id=sysver,
            provider="nvidia", model_name=MODEL, input_tokens=tokens,
            latency_ms=int(elapsed * 1000), status="success",
        )
        rows = [{
            "document_id": doc_id, "chunk_index": c["index"], "page_number": c["page"],
            "content": c["content"], "embedding": to_pgvector(v),
            "embedding_model": MODEL, "embedding_version": EMBEDDING_VERSION,
            "token_count": c["n_tokens"],
        } for c, v in zip(chunks, vecs)]
        saved = ingest_db.insert_document_chunks(rows)
        total_saved += saved
        print(f"  ✅ {title[:30]:30} {saved}청크 · {tokens}토큰 · {elapsed:.1f}s")

    print(f"\n총 {total_saved}청크 저장 (임베딩 버전 {EMBEDDING_VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
