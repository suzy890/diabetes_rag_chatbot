"""실제 승인문서로 nemotron 임베딩의 한국어 검색 성능을 확인한다 (T2.4 직전 검증).

왜 이걸 하는가:
  지난 T2.0은 '내가 지어낸 예시 문장 10개'로 재서 nemotron이 Top-1 100%가 나왔다.
  이번에는 **연구팀이 실제로 준 문서 3~4개**를 그대로 청킹한 것(139청크)에 대고,
  고령 참여자 말투 질문이 정답 청크를 1등으로 찾아내는지 다시 확인한다.
  여기서도 잘 찾으면 "한글이 걱정된다"는 문제는 데이터로 종결된다.

판정:
  - Top-1 : 정답 청크(여러 개 중 하나면 인정)를 1등으로 집었는가  ← 핵심
  - MRR   : 1등이 아니어도 첫 정답 청크가 몇 등에 있었는가

실행: .venv/bin/python tests/check_nemotron_realdocs.py
"""

import glob
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
MODEL = "nvidia/llama-nemotron-embed-1b-v2"  # D32에서 정한 임베딩 모델 (2048차원)

# 사용자가 만들어 둔 청크(512토큰·기본 전략) 위치
CHUNK_DIR = os.path.join(
    os.path.dirname(__file__), "..",
    "data", "source_docs", "chunk__embeddings", "chunk_jsons",
)

# ── 고령 참여자 말투 질문 + 정답 청크(gid) 집합 ─────────────────────────────
# 정답 gid는 청크를 직접 읽고 "이 질문의 답이 실제로 여기 있다"고 확인해 붙였다.
# 같은 주제가 여러 청크에 걸쳐 있으면 모두 정답으로 인정한다(실제 문서의 특성).
QUERIES = [
    ("당화혈색소는 몇 달에 한 번씩 검사받아야 하나요?", {86}),
    ("갑자기 어지럽고 식은땀 나면 뭘 먹어야 하나요?", {124, 22, 19}),
    ("발 관리할 때 맨발로 다녀도 괜찮은가요?", {98, 15}),
    ("운동하려는데 혈당이 너무 높으면 어떻게 해요?", {112}),
    ("혈당이 얼마나 높아야 당뇨병이라고 하나요?", {63, 65, 40}),
    ("약을 깜빡하고 안 먹었는데 다음에 두 배로 먹어도 되나요?", {99}),
    ("집에서 혈당 잴 때 손을 꼭 씻어야 하나요?", {97, 96}),
    ("밖에서 밥 사 먹을 때 조심할 게 있을까요?", {109}),
    ("당뇨가 있는데 술은 마셔도 되나요?", {115}),
    ("저혈당은 도대체 왜 생기는 건가요?", {122, 136}),
    ("손발이 저리고 아픈데 왜 그런 건가요?", {92}),
    ("당뇨가 있으면 혈압은 얼마로 맞춰야 하나요?", {46}),
]


def load_chunks() -> list[dict]:
    """512토큰·기본 전략 청크를 파일명 정렬 순서로 모아 gid를 0부터 붙인다.
    (정답표의 gid가 이 순서에 맞춰져 있으므로 순서를 바꾸면 안 된다.)
    """
    files = [
        f for f in sorted(glob.glob(os.path.join(CHUNK_DIR, "chunk_*_512.json")))
        if "document" not in f and "page" not in f
    ]
    chunks = []
    for f in files:
        for c in json.load(open(f, encoding="utf-8")):
            chunks.append({"gid": len(chunks), "source": c["source"],
                           "page": c["page"], "text": c["text"]})
    return chunks


def embed(texts: list[str], input_type: str) -> tuple[list[list[float]], float]:
    """텍스트 묶음을 nemotron 벡터로 만든다. (벡터목록, 걸린시간초)

    nemotron 임베딩은 질문(query)과 문서(passage)를 다르게 임베딩한다.
    긴 청크에서 오류가 나지 않도록 초과분은 끝에서 자른다(truncate=END).
    입력 개수가 많으면 나눠서 부른다(배치).
    """
    out: list[list[float]] = []
    elapsed = 0.0
    for i in range(0, len(texts), 32):
        batch = texts[i:i + 32]
        payload = {"model": MODEL, "input": batch, "encoding_format": "float",
                   "input_type": input_type, "truncate": "END"}
        started = time.perf_counter()
        r = httpx.post(f"{BASE_URL}/embeddings",
                       headers={"Authorization": f"Bearer {API_KEY}"},
                       json=payload, timeout=180.0)
        if r.status_code == 400:  # input_type 미지원이면 빼고 재시도
            payload.pop("input_type")
            r = httpx.post(f"{BASE_URL}/embeddings",
                           headers={"Authorization": f"Bearer {API_KEY}"},
                           json=payload, timeout=180.0)
        r.raise_for_status()
        elapsed += time.perf_counter() - started
        rows = sorted(r.json()["data"], key=lambda d: d["index"])
        out.extend(row["embedding"] for row in rows)
    return out, elapsed


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    if not API_KEY:
        print("LLM_API_KEY가 비어 있습니다. .env를 확인하세요.")
        return 1

    chunks = load_chunks()
    print(f"실제 문서 청크 {len(chunks)}개 · 고령 구어체 질문 {len(QUERIES)}개 · 모델 {MODEL}\n")

    chunk_vecs, _ = embed([c["text"] for c in chunks], "passage")
    query_vecs, qtime = embed([q for q, _ in QUERIES], "query")
    dim = len(chunk_vecs[0])

    hits = at3 = at5 = 0  # Top-1 / 정답이 상위3·5 안에 들었는가
    reciprocal_ranks: list[float] = []
    for (question, gold), qvec in zip(QUERIES, query_vecs):
        scored = sorted(
            ((cosine(qvec, cv), c["gid"]) for cv, c in zip(chunk_vecs, chunks)),
            reverse=True,
        )
        ranked_gids = [gid for _, gid in scored]
        top_gid = ranked_gids[0]
        # 여러 정답 중 가장 앞선 것의 등수
        rank = min(ranked_gids.index(g) + 1 for g in gold)

        hits += top_gid in gold
        at3 += rank <= 3
        at5 += rank <= 5
        reciprocal_ranks.append(1 / rank)

        mark = "✅" if top_gid in gold else f"{rank}등"
        print(f"  {mark:>4} {question}")
        if top_gid not in gold:
            picked = next(c for c in chunks if c["gid"] == top_gid)
            print(f"        정답={sorted(gold)} · 1등으로 집은 것=[{top_gid}] "
                  f"{picked['source'][:16]} p{picked['page']}: {picked['text'][:46]}")

    n = len(QUERIES)
    print("\n" + "═" * 60)
    print(f"차원={dim} · {qtime / n * 1000:.0f}ms/건")
    print(f"Top-1(1등이 정답)       = {hits}/{n} = {hits / n:.0%}")
    print(f"Recall@3(상위3에 정답)  = {at3}/{n} = {at3 / n:.0%}   ← RAG는 top-k를 쓴다")
    print(f"Recall@5(상위5에 정답)  = {at5}/{n} = {at5 / n:.0%}")
    print(f"MRR                     = {sum(reciprocal_ranks) / n:.2f}")
    print("═" * 60)
    print("해석: 실제 RAG는 상위 몇 개를 LLM에 넣으므로 Recall@k가 더 현실적인 지표다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
