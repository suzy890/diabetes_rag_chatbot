"""T1.3 시나리오 테스트 — 기본 채팅 화면 (메시지 저장 · 복원 · 중복 방지).

완료 기준(TASKS.md T1.3)을 실제 DB에 대고 검증한다.
실행:  .venv/bin/python tests/test_t1_3.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import database

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok))
    print(f"{'✅ 통과' if ok else '❌ 실패'}  {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    print("── T1.3 시나리오 테스트 ──\n")

    session = database.find_open_session("P001") or database.create_session("P001")
    sid, pid = session["session_id"], "P001"

    before = len(database.get_messages(sid))

    # 1. 사용자 메시지 저장 (role · message_type 분리 기록)
    m1 = database.save_message(sid, pid, "user", "free_text", "식후 혈당은 언제 재나요?")
    check("1. 사용자 메시지 저장", m1["role"] == "user" and m1["message_type"] == "free_text")

    # 2. AI 메시지도 같은 표에 저장 가능 (role만 다름)
    m2 = database.save_message(sid, pid, "assistant", "system_notice", "곧 답변 기능이 추가됩니다.")
    check("2. AI 메시지 저장 (role=assistant)", m2["role"] == "assistant")

    # 3. DB에서 대화 복원 — 화면 상태가 아니라 DB가 진실의 원천  ⭐
    restored = database.get_messages(sid)
    check("3. DB에서 대화 복원 (새로고침 대비)", len(restored) == before + 2,
          f"{before} → {len(restored)}건")

    # 4. 시간순 정렬
    check("4. 시간순 정렬", [m["message_id"] for m in restored[-2:]] == [m1["message_id"], m2["message_id"]])

    # 5. 새로고침 반복 — 조회만으로는 메시지가 늘지 않아야 함 (중복 저장 없음) ⭐
    for _ in range(4):
        database.get_messages(sid)
    check("5. 새로고침 4회 반복해도 메시지 수 그대로",
          len(database.get_messages(sid)) == len(restored), "중복 저장 없음")

    # 6. 이벤트에 메시지가 연결되는지 (related_message_id FK)
    try:
        database.log_event("question_asked", pid, sid, related_message_id=m1["message_id"])
        check("6. question_asked 이벤트가 메시지에 연결됨", True)
    except Exception as exc:
        check("6. question_asked 이벤트가 메시지에 연결됨", False, str(exc)[:80])

    # 7. 잘못된 role은 DB가 거부해야 함 (데이터 품질 보호)
    try:
        database.save_message(sid, pid, "robot", "free_text", "잘못된 role")
        check("7. 잘못된 role을 DB가 거부", False, "거부되지 않았다")
    except Exception:
        check("7. 잘못된 role을 DB가 거부", True, "CHECK 제약이 막음")

    failed = [n for n, ok in results if not ok]
    print(f"\n── 결과: {len(results) - len(failed)}/{len(results)} 통과 ──")
    if failed:
        print("실패:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
