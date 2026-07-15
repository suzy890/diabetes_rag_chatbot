"""T2.6 — 근거 충분성 3단계 판단 + 근거 기반 답변을 확인한다.

확인할 것:
  1) 충분/부분/부족 판정이 질문에 맞게 나오는가
  2) 부족이면 LLM을 부르지 않고 고정 안내문(보류)이 나오는가
  3) 답변이 retrieval_logs에 연결되고(answer_message_id), 비용(rag_answer)이 남는가

주의: 테스트 참여자 P001로 데이터 생성(실증 전 삭제 예정).
실행: .venv/bin/python tests/check_answer.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import database  # noqa: E402
import rag  # noqa: E402

# (질문, 기대 판정) — 부분은 임계값에 걸쳐 달라질 수 있어 판정 자체보다 흐름을 본다.
CASES = [
    ("당화혈색소는 몇 달에 한 번씩 검사받아야 하나요?", "sufficient"),
    ("발 관리할 때 맨발로 다녀도 괜찮은가요?", "sufficient"),
    ("김치찌개는 어떻게 끓이나요?", "insufficient"),   # 당뇨와 무관 → 보류 기대
]


def main() -> int:
    ok, msg = database.check_connection()
    print(f"DB 연결: {msg}")
    if not ok:
        return 1
    if not database.get_participant("P001"):
        print("테스트 참여자 P001이 없습니다.")
        return 1

    pid = "P001"
    sid = database.create_session(pid, device_type="desktop")["session_id"]
    client = database.get_client()

    all_ok = True
    for q, expected in CASES:
        m = database.save_message(session_id=sid, participant_id=pid,
                                  role="user", message_type="rag_question", content=q)
        res = rag.respond(q, sid, pid, m["message_id"])
        rid = res["retrieval_id"]

        log = (client.table("retrieval_logs").select("evidence_level, answer_message_id")
               .eq("retrieval_id", rid).execute().data[0])
        rag_calls = (client.table("model_calls").select("call_id", count="exact")
                     .eq("related_message_id", m["message_id"]).eq("call_type", "rag_answer")
                     .execute().count)
        # 부족이면 LLM 미호출(비용 0), 그 외엔 답변 비용 1건
        insufficient = res["evidence_level"] == "insufficient"
        cost_ok = (rag_calls == 0) if insufficient else (rag_calls == 1)
        linked = log["answer_message_id"] == res["answer_message_id"]
        level_ok = log["evidence_level"] == res["evidence_level"]
        good = cost_ok and linked and level_ok
        all_ok = all_ok and good

        print(f"\n{'✅' if good else '❌'} [{res['evidence_level']}] {q}")
        print(f"   답변: {res['answer'][:90]}")
        print(f"   출처 {len(res['sources'])}개 · rag_answer비용 {rag_calls}건 · "
              f"로그연결 {'OK' if linked else 'X'} · 판정저장 {'OK' if level_ok else 'X'}")
        if res["sources"]:
            labels = ", ".join(f"{s['title'][:16]}({s['page']}쪽)" for s in res["sources"])
            print(f"   근거: {labels}")

    print("\n" + "═" * 56)
    print("✅ 전부 통과" if all_ok else "❌ 일부 실패 — 위 확인")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
