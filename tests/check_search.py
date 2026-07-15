"""T2.5 — 검색이 규칙대로 작동하고 로그가 쌓이는지 확인한다.

검증 기준 (phase2-kickoff / D15):
  검색 1회 = retrieval_logs **1행**, 검색된 청크 = retrieval_chunks **청크당 1행**.

주의: 테스트 참여자 P001로 세션·메시지·검색 로그를 만든다(실증 전 삭제 예정 데이터).

실행: .venv/bin/python tests/check_search.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import database  # noqa: E402
import rag  # noqa: E402

QUESTIONS = [
    "당화혈색소는 몇 달에 한 번씩 검사받아야 하나요?",
    "갑자기 어지럽고 식은땀 나면 뭘 먹어야 하나요?",
    "발 관리할 때 맨발로 다녀도 괜찮은가요?",
]
TOP_K = 5


def main() -> int:
    ok, msg = database.check_connection()
    print(f"DB 연결: {msg}")
    if not ok:
        return 1

    pid = "P001"
    if not database.get_participant(pid):
        print(f"테스트 참여자 {pid}가 없습니다. 먼저 등록이 필요합니다.")
        return 1

    session = database.create_session(pid, device_type="desktop")
    sid = session["session_id"]
    client = database.get_client()

    all_ok = True
    for q in QUESTIONS:
        # 실제 흐름처럼 질문 메시지를 먼저 남기고, 그 메시지에 검색을 연결한다.
        m = database.save_message(session_id=sid, participant_id=pid,
                                  role="user", message_type="rag_question", content=q)
        result = rag.retrieve(q, sid, pid, m["message_id"], top_k=TOP_K)
        rid = result["retrieval_id"]
        chunks = result["chunks"]

        # 검증: retrieval_logs 1행 + retrieval_chunks = 검색된 청크 수
        n_logs = (client.table("retrieval_logs").select("retrieval_id", count="exact")
                  .eq("retrieval_id", rid).execute().count)
        n_rchunks = (client.table("retrieval_chunks").select("retrieval_chunk_id", count="exact")
                     .eq("retrieval_id", rid).execute().count)
        good = (n_logs == 1 and n_rchunks == len(chunks))
        all_ok = all_ok and good

        print(f"\n{'✅' if good else '❌'} Q: {q}")
        print(f"   retrieval_logs={n_logs}행 · retrieval_chunks={n_rchunks}행 · 검색청크={len(chunks)}개")
        for i, c in enumerate(chunks[:3], 1):
            print(f"   {i}. 유사도 {c['similarity']:.3f} | {c['content'][:60]}")

    print("\n" + "═" * 56)
    print("✅ 전부 통과 — 1검색=로그1행, 청크당 1행" if all_ok else "❌ 일부 실패 — 위 로그 확인")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
