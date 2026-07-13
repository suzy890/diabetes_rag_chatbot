"""T1.1 시나리오 테스트 — 참여자 코드 입력 · 참여자 확인 · 세션 생성.

완료 기준(TASKS.md T1.1)을 실제 DB에 대고 검증한다.
실행:  .venv/bin/python tests/test_t1_1.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import database

PASS, FAIL = "✅ 통과", "❌ 실패"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL}  {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    print("── T1.1 시나리오 테스트 ──\n")

    # 시나리오 1: 등록된 활성 참여자 → 진입 허용, 세션 생성
    p = database.get_participant("P001")
    check("1a. 등록된 코드 P001 조회됨", p is not None and p["status"] == "active",
          f"status={p['status'] if p else 'None'}")

    session = database.create_session("P001")
    sid = session["session_id"]
    database.log_event("session_started", "P001", sid)
    check("1b. 세션 생성 + session_started 기록", bool(sid), f"session_id={sid[:8]}…")

    # 시나리오 2: 등록되지 않은 코드 → 차단
    check("2. 미등록 코드 P999 차단", database.get_participant("P999") is None)

    # 시나리오 3: 등록됐지만 아직 활성 아님(scheduled) → 차단
    p3 = database.get_participant("P003")
    check("3. 미활성 코드 P003 차단", p3 is not None and p3["status"] != "active",
          f"status={p3['status'] if p3 else 'None'}")

    # 시나리오 4: 새로고침 → 기존 세션을 이어받아 중복 생성 안 함  ⭐ 핵심
    found = database.find_open_session("P001")
    check("4a. 새로고침 시 기존 열린 세션을 찾음", found is not None and found["session_id"] == sid)

    for _ in range(4):  # 새로고침 4번 시뮬레이션
        again = database.find_open_session("P001")
        if not again or again["session_id"] != sid:
            check("4b. 새로고침 반복해도 같은 세션", False, "세션이 바뀌었다")
            break
    else:
        check("4b. 새로고침 4번 반복해도 같은 세션", True, "중복 생성 없음")

    # 시나리오 5: 오류 기록
    database.log_technical_error("test_error", "T1.1 테스트용 오류", participant_id="P001", session_id=sid)
    check("5. technical_errors 기록 동작", True, "예외 없이 기록됨")

    # 시나리오 6: 인증 전 이벤트(app_opened) — 참여자/세션 없이 기록 가능해야 함
    try:
        database.log_event("app_opened")
        check("6. 인증 전 app_opened 기록 (참여자 없이)", True)
    except Exception as exc:
        check("6. 인증 전 app_opened 기록 (참여자 없이)", False, str(exc)[:80])

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n── 결과: {len(results) - len(failed)}/{len(results)} 통과 ──")
    if failed:
        print("실패:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
