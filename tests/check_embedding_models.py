"""T2.0 — 임베딩 모델 3종 한국어 검색 성능 비교 (Phase 2 착수 실험)

왜 이걸 먼저 하는가:
  임베딩 모델이 벡터 '차원'을 결정하고, 그 차원이 `document_chunks`의 vector(N) 컬럼
  크기를 결정한다. 즉 **모델을 정하기 전에는 테이블을 만들 수 없다.**
  그리고 이 시스템의 사용자는 고령 참여자다. "3개월마다 병원에서 재는 수치" 같은
  구어체 질문이 "당화혈색소(HbA1c)"라고 적힌 문어체 문서를 찾아내야 한다.
  이게 안 되면 RAG는 그냥 작동하지 않는다.

무엇을 재는가 (판정 기준):
  1) Top-1 정확도  — 정답 청크를 '1등'으로 찾았는가            ← 가장 중요
  2) MRR           — 1등이 아니어도 몇 등에 있는가 (2등이면 0.5)
  3) 분리도(margin)— 1등과 2등의 점수 차. 작으면 청크가 늘었을 때 순위가 뒤집힌다
  4) 지연시간      — 참여자가 기다리는 시간
  5) 차원          — 저장·검색 비용 (클수록 비쌈)

실행: .venv/bin/python tests/check_embedding_models.py
"""

import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")

# 계정 권한으로 실제 호출이 확인된 3종 (나머지는 404) — phase2-kickoff.md
MODELS = [
    "nvidia/nv-embedqa-e5-v5",            # 1024차원 · 다국어 E5 계열
    "nvidia/llama-nemotron-embed-1b-v2",  # 2048차원
    "nvidia/nv-embed-v1",                 # 4096차원 · 영어 중심 추정
]

# ── 문서 청크 (승인 문서를 흉내낸 '문어체·표준용어' 텍스트) ─────────────────
# 실제 가이드라인처럼 표준 의료 용어로 쓰여 있다. 참여자는 이렇게 말하지 않는다.
# 그 간극을 임베딩이 메워주는지 보는 것이 이 실험의 핵심이다.
CHUNKS = {
    "hba1c": "당화혈색소(HbA1c)는 적혈구의 혈색소에 포도당이 결합한 비율로, 최근 2~3개월간의 "
             "평균적인 혈당 상태를 반영하는 지표이다. 일반적으로 3개월 간격으로 측정한다.",
    "fasting": "공복혈당은 최소 8시간 이상 열량 섭취를 하지 않은 상태에서 측정한 혈장 포도당 "
               "농도를 말한다. 주로 아침 식전에 측정한다.",
    "postmeal": "식후혈당은 식사 시작 후 2시간이 지난 시점에 측정하는 혈당을 의미하며, "
                "식사의 종류와 양에 따라 변동한다.",
    "hypo": "저혈당은 혈당이 정상보다 낮아지는 상태로 식은땀, 어지럼증, 손 떨림, 심계항진, "
            "공복감 등의 증상이 나타날 수 있다. 증상이 있으면 즉시 당분을 섭취한다.",
    "smbg": "자가혈당측정은 환자가 혈당측정기를 이용해 스스로 모세혈관 혈당을 측정하는 것이다. "
            "측정 전 손을 씻고, 채혈침은 매번 새것을 사용한다.",
    "insulin": "인슐린 주사는 피하지방층에 투여하며 복부, 대퇴부, 상완부 등을 이용한다. "
               "동일 부위에 반복 주사하면 지방이영양증이 생길 수 있으므로 주사 부위를 교체한다.",
    "exercise": "제2형 당뇨병 환자에게는 유산소 운동을 주당 150분 이상, 최소 3일 이상에 걸쳐 "
                "시행할 것을 권고한다. 걷기, 자전거 타기 등이 해당된다.",
    "diet": "식사요법의 기본은 규칙적인 식사 시간과 적절한 열량 섭취이다. 탄수화물의 총량을 "
            "조절하고 식이섬유가 풍부한 식품을 선택한다.",
    "foot": "당뇨병성 족부병변 예방을 위해 매일 발을 관찰하고 상처, 물집, 발적이 있는지 확인한다. "
            "맨발로 다니지 않으며 발에 맞는 신발을 착용한다.",
    "eye": "당뇨병망막병증은 초기에 자각 증상이 없을 수 있으므로 정기적인 안저검사가 필요하다. "
           "시야 흐림이나 비문증이 나타나면 안과 진료를 받는다.",
}

# ── 고령 참여자의 실제 말투로 된 질문 + 찾아야 할 정답 청크 ──────────────────
QUERIES = [
    # ⭐ 인수인계서가 지목한 핵심 케이스: 구어체 → 당화혈색소
    ("3개월마다 병원에서 재는 그 수치가 뭔가요?", "hba1c"),
    ("에이원씨가 높다는데 그게 무슨 말이에요?", "hba1c"),
    # ⚠️ 혼동 유도: '아침에 재는 거'는 당화혈색소가 아니라 공복혈당이어야 한다
    ("아침에 밥 먹기 전에 재는 건 뭐라고 하나요?", "fasting"),
    ("밥 먹고 두 시간 있다가 재라고 하던데 왜 그런가요?", "postmeal"),
    ("갑자기 식은땀 나고 손이 떨리고 어지러워요", "hypo"),
    ("집에서 혈당 재는 기계 쓸 때 주의할 게 있나요?", "smbg"),
    ("주사를 자꾸 같은 자리에 놓으면 안 되나요?", "insulin"),
    ("운동은 일주일에 얼마나 해야 하나요?", "exercise"),
    ("밥은 어떻게 먹어야 좋은가요?", "diet"),
    ("발이 저리고 상처가 잘 안 낫는데 어떻게 관리해요?", "foot"),
]


def embed(model: str, texts: list[str], input_type: str) -> tuple[list[list[float]], float]:
    """텍스트 묶음을 벡터로 만든다. (벡터목록, 걸린시간초)

    embedqa 계열은 질문(query)과 문서(passage)를 다르게 임베딩해야 한다.
    이를 지원하지 않는 모델은 400을 내므로, 그때는 input_type 없이 다시 부른다.
    """
    payload = {
        "model": model,
        "input": texts,
        "encoding_format": "float",
        "input_type": input_type,
    }
    started = time.perf_counter()
    r = httpx.post(
        f"{BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
        timeout=120.0,
    )
    if r.status_code == 400:  # input_type 미지원 모델
        payload.pop("input_type")
        r = httpx.post(
            f"{BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=120.0,
        )
    r.raise_for_status()
    elapsed = time.perf_counter() - started
    # API가 순서를 보장하지 않을 수 있으므로 index로 정렬한다
    rows = sorted(r.json()["data"], key=lambda d: d["index"])
    return [row["embedding"] for row in rows], elapsed


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def evaluate(model: str) -> dict | None:
    """한 모델로 10개 질문을 검색해보고 성적을 낸다."""
    keys = list(CHUNKS)
    try:
        # 문서는 passage로, 질문은 query로 임베딩한다 (embedqa 계열의 요구사항)
        chunk_vecs, _ = embed(model, [CHUNKS[k] for k in keys], "passage")
        query_vecs, query_time = embed(model, [q for q, _ in QUERIES], "query")
    except httpx.HTTPStatusError as e:
        print(f"  ❌ 호출 실패: HTTP {e.response.status_code} — {e.response.text[:200]}")
        return None
    except Exception as e:  # noqa: BLE001 — 실험 스크립트라 원인을 그대로 보여준다
        print(f"  ❌ 호출 실패: {type(e).__name__} — {e}")
        return None

    dim = len(chunk_vecs[0])
    hits = 0
    reciprocal_ranks: list[float] = []
    margins: list[float] = []

    for (question, answer_key), qvec in zip(QUERIES, query_vecs):
        scores = sorted(
            ((cosine(qvec, cv), k) for cv, k in zip(chunk_vecs, keys)),
            reverse=True,
        )
        top_key = scores[0][1]
        rank = [k for _, k in scores].index(answer_key) + 1
        margin = scores[0][0] - scores[1][0]  # 1등과 2등의 점수 차 = 확신의 정도

        hits += rank == 1
        reciprocal_ranks.append(1 / rank)
        margins.append(margin)

        mark = "✅" if rank == 1 else "❌"
        print(f"  {mark} {question}")
        if rank != 1:
            # 틀렸으면 무엇을 대신 집었는지 봐야 원인을 안다
            print(f"       정답={answer_key}({rank}등) · 1등으로 집은 것={top_key}")

    n = len(QUERIES)
    return {
        "model": model,
        "dim": dim,
        "top1": hits / n,
        "mrr": sum(reciprocal_ranks) / n,
        "margin": sum(margins) / n,
        # 질문 10개를 한 번에 임베딩한 시간 → 1건당 환산 (참여자 체감 지연의 근사)
        "latency_ms": query_time / n * 1000,
    }


def main() -> int:
    if not API_KEY:
        print("LLM_API_KEY가 비어 있습니다. .env를 확인하세요.")
        return 1

    print(f"고령 구어체 질문 {len(QUERIES)}개 × 문서 청크 {len(CHUNKS)}개 · 모델 {len(MODELS)}종\n")

    results = []
    for model in MODELS:
        print(f"── {model} " + "─" * max(0, 44 - len(model)))
        result = evaluate(model)
        if result:
            results.append(result)
            print(f"  → 차원={result['dim']} · Top-1={result['top1']:.0%} · "
                  f"MRR={result['mrr']:.2f} · 분리도={result['margin']:.3f} · "
                  f"{result['latency_ms']:.0f}ms/건")
        print()

    if not results:
        print("세 모델 모두 호출에 실패했습니다.")
        return 1

    print("═" * 62)
    print(f"{'모델':<36}{'차원':>6}{'Top-1':>7}{'MRR':>6}{'분리도':>7}")
    print("─" * 62)
    for r in sorted(results, key=lambda x: (-x["top1"], -x["mrr"])):
        name = r["model"].replace("nvidia/", "")
        print(f"{name:<36}{r['dim']:>6}{r['top1']:>7.0%}{r['mrr']:>6.2f}{r['margin']:>7.3f}")
    print("═" * 62)
    print("\n판정: Top-1이 가장 높은 모델을 고른다. 동률이면 분리도가 큰 쪽,")
    print("      그래도 동률이면 차원이 작은 쪽(저장·검색 비용이 싸다)을 고른다.")
    print("→ 정한 모델의 '차원'이 document_chunks의 vector(N) 크기가 된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
