"""T2.3 — 청크 정제 + 크기·전략 비교 (어떤 청킹이 검색이 제일 잘 되나).

배경:
  실제 문서(check_nemotron_realdocs.py)에서 Top-1이 낮았던 원인은 임베딩이 아니라
  **청크에 섞인 잡음**(머리말·쪽번호·"구분(시간) 슬라이드"·워터마크)이었다.
  그래서 ① 잡음을 제거하고 ② 여러 청크 크기·전략을 같은 기준으로 비교해 최적을 고른다.

핵심 설계 — 정답을 '청크 번호'가 아니라 '내용'으로 정의한다:
  청크 크기가 바뀌면 번호가 바뀌므로, "정답 청크 안에 이 핵심 문구가 있는가"로 판정한다.
  이렇게 하면 256·512·page·document 어떤 청킹이든 똑같은 잣대로 잴 수 있다.

실행: .venv/bin/python tests/compare_chunking.py
"""

import glob
import json
import os
import re
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
MODEL = "nvidia/llama-nemotron-embed-1b-v2"
CHUNK_DIR = os.path.join(
    os.path.dirname(__file__), "..",
    "data", "source_docs", "chunk__embeddings", "chunk_jsons",
)

# ── 정제 규칙: 문서마다 반복되는 잡음을 지운다 ──────────────────────────────
# 본문 내용(수치·문장)은 건드리지 않고, 페이지 장식·머리말·워터마크만 없앤다.
_NOISE_PATTERNS = [
    r"당뇨병\s*\|\s*고급실습과정\s*■?\s*(교육지침서\s*\(매뉴얼\))?\s*\d*",  # DMhmenu 머리말
    r"구분\s*\(시간\)\s*슬라이드\s*페이지\s*내용\s*보조자료\s*및\s*학습\s*활동",  # 강의표 머리말
    r"Quick\s*Reference\s*Guide\s*\d*\s*당뇨병\s*\d*",                      # 권고요약 머리말
    r"근거기반\s*당뇨병\s*환자\s*관리\s*정보\s*\d*",                          # 근거기반 머리말
    r"\d+\s*/\s*(?=근거기반|자가관리|당뇨병|응급|참고문헌|부록)",              # "18/ 근거기반…" 쪽번호
    r"(?:관리하기|실천하기|대처하기|알기)\s*\d+\s*/",                          # "…실천하기 20/" 쪽번호
    r"D\s*ia\s*b\s*e\s*t\s*e\s*s",                                          # 띄어쓴 워터마크
    r"https?://\S+",                                                        # URL
    r"보조자료\s*및\s*학습\s*활동",
]
_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]


def clean(text: str) -> str:
    """청크 텍스트에서 반복 잡음을 제거하고 공백을 정리한다."""
    for rx in _NOISE_RE:
        text = rx.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── 고령 구어체 질문 + '정답 문구'(이 중 하나라도 포함하면 정답 청크) ──────────
# 문구는 정제해도 남는 실제 내용이라, 청킹이 바뀌어도 판정이 유지된다.
QUERIES = [
    ("당화혈색소는 몇 달에 한 번씩 검사받아야 하나요?", ["3개월마다"]),
    ("갑자기 어지럽고 식은땀 나면 뭘 먹어야 하나요?", ["단당류", "15g", "꿀 1", "사탕 3알"]),
    ("발 관리할 때 맨발로 다녀도 괜찮은가요?", ["맨발"]),
    ("운동하려는데 혈당이 너무 높으면 어떻게 해요?", ["300 mg/dL", "혈당이 300"]),
    ("혈당이 얼마나 높아야 당뇨병이라고 하나요?", ["6.5% 이상", "당화혈색소 ≥ 6.5", "126"]),
    ("약을 깜빡하고 안 먹었는데 다음에 두 배로 먹어도 되나요?", ["2배", "두 배"]),
    ("집에서 혈당 잴 때 손을 꼭 씻어야 하나요?", ["손을 잘 씻", "손을 씻", "손 씻"]),
    ("밖에서 밥 사 먹을 때 조심할 게 있을까요?", ["외식"]),
    ("당뇨가 있는데 술은 마셔도 되나요?", ["음주"]),
    ("저혈당은 도대체 왜 생기는 건가요?", ["용량이 너무 많", "식사량이 모자"]),
    ("손발이 저리고 아픈데 왜 그런 건가요?", ["신경병증", "저림"]),
    ("당뇨가 있으면 혈압은 얼마로 맞춰야 하나요?", ["140/85", "목표혈압"]),
]

# 비교할 청킹 조합 (전략, 토큰크기). 파일명 suffix로 찾는다.
VARIANTS = [
    ("basic", "256"), ("basic", "512"),
    ("page", "256"), ("page", "512"),
    ("document", "256"), ("document", "512"),
]


def load_variant(strategy: str, size: str) -> list[dict]:
    """해당 (전략·크기) 청크를 4개 문서에서 모아 정제해 돌려준다.
    (원문 raw는 정답 판정용, cleaned는 임베딩·검색용.)
    """
    if strategy == "basic":
        suffix, exclude = f"_{size}.json", ("document", "page")
    else:
        suffix, exclude = f"_{strategy}_{size}.json", ()
    out = []
    for f in sorted(glob.glob(os.path.join(CHUNK_DIR, f"*{suffix}"))):
        base = os.path.basename(f)
        if any(x in base for x in exclude):
            continue
        for c in json.load(open(f, encoding="utf-8")):
            cleaned = clean(c["text"])
            # 정제 후 사실상 비는 조각(순수 잡음·표지·목차)은 검색에서 뺀다.
            if len(cleaned) < 10:
                continue
            out.append({"raw": c["text"], "cleaned": cleaned})
    return out


def embed(texts: list[str], input_type: str) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 32):
        payload = {"model": MODEL, "input": texts[i:i + 32], "encoding_format": "float",
                   "input_type": input_type, "truncate": "END"}
        r = httpx.post(f"{BASE_URL}/embeddings",
                       headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=180.0)
        if r.status_code == 400:
            payload.pop("input_type")
            r = httpx.post(f"{BASE_URL}/embeddings",
                           headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=180.0)
        r.raise_for_status()
        out.extend(row["embedding"] for row in sorted(r.json()["data"], key=lambda d: d["index"]))
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def is_gold(text: str, phrases: list[str]) -> bool:
    return any(p in text for p in phrases)


def evaluate(chunks: list[dict], query_vecs: list[list[float]]) -> dict:
    chunk_vecs = embed([c["cleaned"] for c in chunks], "passage")
    top1 = at3 = at5 = 0
    rr = []
    for (_, phrases), qvec in zip(QUERIES, query_vecs):
        ranked = sorted(range(len(chunks)),
                        key=lambda i: cosine(qvec, chunk_vecs[i]), reverse=True)
        gold_ranks = [r + 1 for r, i in enumerate(ranked) if is_gold(chunks[i]["raw"], phrases)]
        rank = gold_ranks[0] if gold_ranks else 999
        top1 += rank == 1
        at3 += rank <= 3
        at5 += rank <= 5
        rr.append(1 / rank if rank < 999 else 0)
    n = len(QUERIES)
    return {"n_chunks": len(chunks), "top1": top1 / n, "r3": at3 / n,
            "r5": at5 / n, "mrr": sum(rr) / n}


def main() -> int:
    if not API_KEY:
        print("LLM_API_KEY가 비어 있습니다.")
        return 1

    query_vecs = embed([q for q, _ in QUERIES], "query")  # 질문은 한 번만 임베딩
    print(f"질문 {len(QUERIES)}개 · 정제 적용 · 모델 {MODEL}\n")

    rows = []
    for strategy, size in VARIANTS:
        chunks = load_variant(strategy, size)
        if not chunks:
            print(f"  ({strategy}_{size}: 청크 없음, 건너뜀)")
            continue
        started = time.perf_counter()
        m = evaluate(chunks, query_vecs)
        m["name"] = f"{strategy}_{size}"
        rows.append(m)
        print(f"  {m['name']:14} 청크{m['n_chunks']:>4} · "
              f"Top-1={m['top1']:.0%} · R@3={m['r3']:.0%} · R@5={m['r5']:.0%} · "
              f"MRR={m['mrr']:.2f}  ({time.perf_counter() - started:.0f}s)")

    print("\n" + "═" * 60)
    print(f"{'청킹조합':<14}{'청크수':>6}{'Top-1':>8}{'R@3':>7}{'R@5':>7}{'MRR':>7}")
    print("─" * 60)
    for m in sorted(rows, key=lambda x: (-x["r5"], -x["top1"], -x["mrr"])):
        print(f"{m['name']:<14}{m['n_chunks']:>6}{m['top1']:>8.0%}"
              f"{m['r3']:>7.0%}{m['r5']:>7.0%}{m['mrr']:>7.2f}")
    print("═" * 60)
    print("판정: Recall@5(정답이 상위5에 있는가) 우선 → 같으면 Top-1 → MRR.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
