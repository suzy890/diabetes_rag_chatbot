"""T1.4 시나리오 테스트 — 접속 시간대 넛지 (규칙·템플릿·반복 제한).

완료 기준(TASKS.md T1.4)을 실제 DB에 대고 검증한다.
테스트 참여자 P002의 넛지·메시지를 먼저 비워 반복 실행이 가능하게 한다.

실행:  .venv/bin/python tests/test_t1_4.py
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import database
import nudge

PID = "P002"  # 테스트 전용 참여자 (실제 참여자 데이터는 건드리지 않는다)
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok))
    print(f"{'✅ 통과' if ok else '❌ 실패'}  {name}" + (f"  — {detail}" if detail else ""))


def at(hour: int) -> datetime:
    """오늘 해당 시각(한국시간). 시간대별 규칙을 검증하기 위한 가상 시각."""
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    return datetime(today.year, today.month, today.day, hour, 30, tzinfo=ZoneInfo("Asia/Seoul"))


def reset_test_participant() -> None:
    """P002의 데이터를 비운다 (테스트를 반복 실행 가능하게).

    Phase 2에서 model_calls·retrieval_*가 messages를 참조하므로,
    FK 위반이 없도록 자식(참조) 테이블부터 지운다.
    """
    client = database.get_client()
    rids = [r["retrieval_id"] for r in
            client.table("retrieval_logs").select("retrieval_id")
            .eq("participant_id", PID).execute().data]
    for rid in rids:
        client.table("retrieval_chunks").delete().eq("retrieval_id", rid).execute()
    client.table("retrieval_logs").delete().eq("participant_id", PID).execute()
    client.table("model_calls").delete().eq("participant_id", PID).execute()
    client.table("nudge_events").delete().eq("participant_id", PID).execute()
    client.table("events").delete().eq("participant_id", PID).execute()
    client.table("messages").delete().eq("participant_id", PID).execute()
    client.table("sessions").delete().eq("participant_id", PID).execute()


def show_nudge(session_id: str, template: dict) -> dict:
    """넛지를 실제로 노출한 것처럼 기록한다."""
    message = database.save_message(session_id, PID, "assistant", "nudge", template["text"])
    return database.create_nudge(
        PID, session_id, {**template, "template_version": nudge.TEMPLATE_VERSION},
        message["message_id"],
    )


def main() -> int:
    print("── T1.4 시나리오 테스트 ──\n")
    reset_test_participant()

    participant = database.get_participant(PID)
    session = database.find_open_session(PID) or database.create_session(PID)
    sid = session["session_id"]

    # 1. 시간대별로 올바른 템플릿이 선택되는가
    expected = {8: "meal_breakfast", 12: "meal_lunch", 15: "snack_afternoon",
                18: "meal_dinner", 22: "snack_late"}
    check("1. 시간대별 템플릿 선택",
          all((nudge.find_template(at(h)) or {}).get("key") == k for h, k in expected.items()),
          "아침/점심/간식/저녁/야식")

    # 2. 넛지 없는 시간대에는 띄우지 않는다
    check("2. 넛지 없는 시간대엔 안 띄움",
          all(nudge.find_template(at(h)) is None for h in (3, 10, 20)),
          "새벽 3시 / 10시 / 20시")

    # 3. 승인 문구가 규칙을 지키는가 (죄책감·공포·강압 금지, 질문형, 거절/나중 선택지)
    banned = ["안 돼", "위험", "반드시", "꼭 ", "해야", "하지 마", "또 "]
    check("3. 문구 규칙 준수",
          not any(b in t["text"] for t in nudge.TEMPLATES for b in banned)
          and all(t["text"].endswith("?") for t in nudge.TEMPLATES)
          and all(nudge.DEFERRED in t["options"] for t in nudge.TEMPLATES),
          "강압 없음 · 질문형 · '나중에' 선택지")

    # 4. 점심 시간대에 접속 → 점심 넛지가 선택된다
    picked = nudge.select_nudge(participant, now=at(12))
    check("4. 점심 접속 → 점심 넛지 선택", picked is not None and picked["key"] == "meal_lunch")

    record = show_nudge(sid, picked)
    check("5. 넛지 기록 (예정·노출 시각 분리 저장)",
          record["scheduled_at"] and record["displayed_at"] and record["status"] == "displayed")

    # 6. ⭐ 같은 넛지 재노출 차단 — 규칙이 실제로 막는가
    check("6. 같은 넛지 하루 1회 제한 (재노출 차단)",
          nudge.select_nudge(participant, now=at(12)) is None,
          "오늘 이미 점심 넛지를 봤으므로 안 띄움")

    # 7. 다른 시간대 넛지는 아직 허용된다
    check("7. 다른 시간대 넛지는 허용",
          (nudge.select_nudge(participant, now=at(15)) or {}).get("key") == "snack_afternoon")

    # 8. ⭐ 하루 상한(3회) — 3개를 채우면 더는 안 띄운다
    show_nudge(sid, nudge.find_template(at(15)))   # 2번째
    show_nudge(sid, nudge.find_template(at(18)))   # 3번째
    check("8. 하루 최대 3회 상한 (초과 차단)",
          nudge.select_nudge(participant, now=at(22)) is None,
          f"오늘 {nudge.MAX_NUDGES_PER_DAY}회 채움 → 야식 넛지 안 띄움")

    # 9. 새로고침해도 답 안 한 넛지가 살아있다
    pending = database.get_unanswered_nudge(PID, sid)
    check("9. 새로고침 후 미응답 넛지 복원", pending is not None)

    # 10. 응답 저장
    database.save_message(sid, PID, "user", "nudge_response", "네, 먹었어요")
    database.record_nudge_response(pending["nudge_id"], "네, 먹었어요")
    check("10. 응답 저장 후 status=answered",
          database.get_unanswered_nudge(PID, sid)["nudge_id"] != pending["nudge_id"]
          if database.get_unanswered_nudge(PID, sid) else True)

    failed = [n for n, ok in results if not ok]
    print(f"\n── 결과: {len(results) - len(failed)}/{len(results)} 통과 ──")
    if failed:
        print("실패:", ", ".join(failed))
    # 테스트가 만든 P002 데이터를 스스로 치운다 (실제 사용/데모에 잔여물이 섞이지 않도록).
    reset_test_participant()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
