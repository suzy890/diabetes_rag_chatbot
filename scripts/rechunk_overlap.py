"""재청킹 (overlap) — 청크 경계에서 문맥이 잘리는 문제 해결.

배경: basic_512는 겹침 없이 잘라서, "먹지 않은 약을 …2배로 먹으면 안 됩니다"처럼
한 개념이 두 청크로 쪼개져 검색이 실패하는 경우가 있었다(약 질문 버그).
→ 문장 단위로 **겹치게(overlap)** 다시 나눠, 각 창(window)이 앞뒤 문맥을 함께 담게 한다.

파이프라인: basic_512 청크로 문서 원문 복원 → 문장 분리 → 겹치는 창으로 묶기
            → 정제(clean) → nemotron 임베딩 → document_chunks 저장(새 embedding_version)
            → 기존 청크 비활성화(is_active=false, 재현성 위해 삭제 안 함)

실행:  .venv/bin/python scripts/rechunk_overlap.py --dry     (미리보기만)
       .venv/bin/python scripts/rechunk_overlap.py           (임베딩·저장까지)
"""

import glob
import json
import os
import re
import sys
import time

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

import database  # noqa: E402
import ingest_db  # noqa: E402
from compare_chunking import clean  # 정제 규칙 재사용  # noqa: E402

load_dotenv()
BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
MODEL = "nvidia/llama-nemotron-embed-1b-v2"
NEW_VERSION = "nemotron-2048-overlap-v1"
OLD_VERSION = "nemotron-2048-basic512-clean-v1"
CHUNK_DIR = os.path.join(os.path.dirname(__file__), "..",
                         "data", "source_docs", "chunk__embeddings", "chunk_jsons")
WINDOW_CHARS = 700      # 한 창의 목표 글자 수 (정제 전 기준, ≈ 450~550 토큰)
OVERLAP_SENTS = 2       # 창끼리 겹칠 문장 수 (경계 문맥 보존)

SOURCE_TO_TITLE = {
    "[당뇨병]권고 요약정보_전자.pdf": "일차 의료용 근거기반 당뇨병 권고 요약 정보",
    "근거기반 당뇨병 환자 관리 정보.pdf": "근거기반 당뇨병 환자 관리 정보",
    "당뇨병 환자에게 필요한 정보_65세 이상.pdf": "노년 당뇨병 환자에게 필요한 정보 (65세 이상)",
    "DMhmenu180514.pdf": "고혈압·당뇨병 표준교육자료: 당뇨병 고급실습과정 교육지침서",
}


def load_docs() -> dict[str, list[dict]]:
    """basic_512 청크를 문서별로 순서대로 모은다 {source: [{page, text}]}."""
    docs: dict[str, list[dict]] = {}
    for f in sorted(glob.glob(os.path.join(CHUNK_DIR, "*_512.json"))):
        base = os.path.basename(f)
        if "document" in base or "page" in base:
            continue
        for c in json.load(open(f, encoding="utf-8")):
            docs.setdefault(c["source"], []).append({"page": c.get("page"), "text": c["text"]})
    return docs


def sentences(chunks: list[dict]) -> list[tuple[str, int]]:
    """문서를 (문장, 페이지) 목록으로 편다. 문장은 종결부호 뒤에서 나눈다."""
    out = []
    for ch in chunks:
        for s in re.split(r"(?<=[.!?。])\s+", ch["text"]):
            s = s.strip()
            if s:
                out.append((s, ch["page"]))
    return out


def windows(sents: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """문장들을 겹치는 창으로 묶는다. (창 텍스트, 시작 페이지) 목록을 돌려준다."""
    out, cur = [], []
    for s in sents:
        cur.append(s)
        if sum(len(t) for t, _ in cur) >= WINDOW_CHARS:
            out.append((" ".join(t for t, _ in cur), cur[0][1]))
            cur = cur[-OVERLAP_SENTS:]      # 뒤쪽 몇 문장을 다음 창의 앞에 겹쳐 남긴다
    if cur and (not out or " ".join(t for t, _ in cur) != out[-1][0]):
        out.append((" ".join(t for t, _ in cur), cur[0][1]))
    return out


def build() -> dict[str, list[dict]]:
    """문서별 겹치는 청크(정제본)를 만든다 {source: [{index, page, content}]}."""
    result = {}
    for source, chunks in load_docs().items():
        rows = []
        for i, (text, page) in enumerate(windows(sentences(chunks))):
            cleaned = clean(text)
            if len(cleaned) >= 10:
                rows.append({"index": i, "page": page, "content": cleaned})
        result[source] = rows
    return result


def embed(texts: list[str]) -> tuple[list[list[float]], int, float]:
    vecs, tokens, elapsed = [], 0, 0.0
    for i in range(0, len(texts), 32):
        payload = {"model": MODEL, "input": texts[i:i + 32], "encoding_format": "float",
                   "input_type": "passage", "truncate": "END"}
        started = time.perf_counter()
        r = httpx.post(f"{BASE_URL}/embeddings",
                       headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=180)
        r.raise_for_status()
        elapsed += time.perf_counter() - started
        body = r.json()
        vecs.extend(row["embedding"] for row in sorted(body["data"], key=lambda d: d["index"]))
        tokens += body.get("usage", {}).get("total_tokens", 0)
    return vecs, tokens, elapsed


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


def main() -> int:
    dry = "--dry" in sys.argv
    docs = build()
    total = sum(len(v) for v in docs.values())
    print(f"겹치는 청크 총 {total}개 (기존 basic_512는 135개)\n")

    # 약 질문 케이스 점검: '빼먹은 약'과 '2배로 먹으면 안 됨'이 한 청크에 함께 있는가
    hit = None
    for rows in docs.values():
        for r in rows:
            if "2배로" in r["content"] and ("빼먹" in r["content"] or "먹지 않은" in r["content"]
                                          or "복용하지 못" in r["content"]):
                hit = r["content"]
    print("■ 약 질문 케이스 — '빼먹은 약 ↔ 2배 금지'가 한 청크에 함께?:",
          "✅ 예" if hit else "❌ 아니오")
    if hit:
        print("   →", hit[:150], "\n")

    if dry:
        print("(dry-run: 저장하지 않음)")
        return 0

    if not API_KEY:
        print("LLM_API_KEY가 비어 있습니다."); return 1
    already = ingest_db.count_chunks(NEW_VERSION)
    if already:
        print(f"이미 '{NEW_VERSION}'로 {already}청크 저장됨 → 종료."); return 0

    sysver = database.get_active_system_version_id()
    title_to_id = {d["title"]: d["document_id"] for d in database.list_documents()}
    saved_total = 0
    for source, rows in docs.items():
        doc_id = title_to_id.get(SOURCE_TO_TITLE.get(source, ""))
        if not doc_id:
            print(f"  ⚠️ '{source}' 매칭 문서 없음, 건너뜀"); continue
        vecs, tokens, elapsed = embed([r["content"] for r in rows])
        database.log_model_call(call_type="document_embedding", system_version_id=sysver,
                                provider="nvidia", model_name=MODEL, input_tokens=tokens,
                                latency_ms=int(elapsed * 1000), status="success")
        db_rows = [{"document_id": doc_id, "chunk_index": r["index"], "page_number": r["page"],
                    "content": r["content"], "embedding": to_pgvector(v),
                    "embedding_model": MODEL, "embedding_version": NEW_VERSION} for r, v in zip(rows, vecs)]
        saved_total += ingest_db.insert_document_chunks(db_rows)
        print(f"  ✅ {source[:28]:28} {len(rows)}청크 · {tokens}토큰 · {elapsed:.1f}s")

    # 기존 청크 비활성화 (삭제 아님 — 재현성 보존). 새 청크만 검색 대상이 된다.
    database.get_client().table("document_chunks").update({"is_active": False}) \
        .eq("embedding_version", OLD_VERSION).execute()
    print(f"\n총 {saved_total}청크 저장 · 기존({OLD_VERSION}) 비활성화 완료")
    print(f"→ config.EMBED_VERSION 을 '{NEW_VERSION}' 로 바꿔야 knowledge_base_version 로그가 맞습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
