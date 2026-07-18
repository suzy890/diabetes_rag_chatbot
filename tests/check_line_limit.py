"""핵심 실행 코드가 줄수 제한을 지키는지 확인한다 (CLAUDE.md).

기준: 빈 줄과 주석·독스트링을 제외한 실제 코드 줄 수.
규칙(D36): 500줄 제한은 **로직 5개 모듈**에만 적용한다.
  database.py는 13개 테이블의 기계적 DB 배관이라 로직이 아니므로,
  500 계산에서 빼고 **별도 상한(250)**으로 따로 관리한다.
  (시딩 등 1회성 관리용 DB 쓰기는 코어 밖 scripts/ingest_db.py에 둔다.)
실행:  .venv/bin/python tests/check_line_limit.py
"""

import io
import tokenize
from pathlib import Path

LOGIC_LIMIT = 500       # 로직 5개 모듈 합계 상한
DATA_LIMIT = 250        # database.py 단독 상한
UI_LIMIT = 250          # ui.py 단독 상한 (화면 그리기 = 프레젠테이션, 로직 아님 — D41)
LLM_LIMIT = 150         # llm_client.py 단독 상한 (외부 API 호출 배관, 로직 아님)
SRC = Path(__file__).resolve().parent.parent / "src"

# 로직 모듈 (500 적용) — 비개발자 연구자가 읽는 '무엇을·왜'
LOGIC_MODULES = ["app.py", "rag.py", "nudge.py", "safety.py", "config.py"]
# 배관 모듈들 (각자 별도 상한 — 기계적 인프라, 로직 아님)
DATA_MODULE = "database.py"     # DB 저장·조회
UI_MODULE = "ui.py"             # 화면 그리기
LLM_MODULE = "llm_client.py"    # 외부 LLM·임베딩 API 호출


def code_lines(path: Path) -> int:
    """빈 줄·주석·독스트링을 뺀 실제 코드 줄 수."""
    source = path.read_text(encoding="utf-8")
    skip: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        is_comment = token.type == tokenize.COMMENT
        is_docstring = token.type == tokenize.STRING and token.line.strip().startswith(('"""', "'''"))
        if is_comment or is_docstring:
            skip.update(range(token.start[0], token.end[0] + 1))

    return sum(
        1
        for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and number not in skip
    )


def _count(name: str) -> int | None:
    path = SRC / name
    return code_lines(path) if path.exists() else None


def main() -> int:
    print(f"{'파일':<14}{'실제 코드':>10}")
    print("─" * 24)

    # ① 로직 5개 모듈 → 합계 500 제한
    total = 0
    for name in LOGIC_MODULES:
        count = _count(name)
        if count is None:
            print(f"{name:<14}{'(아직 없음)':>10}")
            continue
        total += count
        print(f"{name:<14}{count:>10}")
    print("─" * 24)
    print(f"{'로직 합계':<14}{total:>10}  / 제한 {LOGIC_LIMIT}")

    # ② database.py → 단독 상한 (별도 관리)
    data_count = _count(DATA_MODULE) or 0
    print(f"{DATA_MODULE + ' (배관)':<14}{data_count:>10}  / 상한 {DATA_LIMIT}")
    # ③ ui.py → 단독 상한 (화면 그리기)
    ui_count = _count(UI_MODULE) or 0
    print(f"{UI_MODULE + ' (화면)':<14}{ui_count:>10}  / 상한 {UI_LIMIT}")
    # ④ llm_client.py → 단독 상한 (외부 API 배관)
    llm_count = _count(LLM_MODULE) or 0
    print(f"{LLM_MODULE + ' (API)':<16}{llm_count:>8}  / 상한 {LLM_LIMIT}")

    logic_ok = total <= LOGIC_LIMIT
    data_ok = data_count <= DATA_LIMIT
    ui_ok = ui_count <= UI_LIMIT
    llm_ok = llm_count <= LLM_LIMIT
    print()
    if logic_ok:
        print(f"✅ 로직 통과 — 여유 {LOGIC_LIMIT - total}줄")
    else:
        print(f"❌ 로직 초과 — {total - LOGIC_LIMIT}줄 넘음. 코드를 단순화해야 합니다.")
    if data_ok:
        print(f"✅ database.py 통과 — 여유 {DATA_LIMIT - data_count}줄")
    else:
        print(f"❌ database.py 초과 — {data_count - DATA_LIMIT}줄. 읽기/쓰기 분리 등 검토.")
    if ui_ok:
        print(f"✅ ui.py 통과 — 여유 {UI_LIMIT - ui_count}줄")
    else:
        print(f"❌ ui.py 초과 — {ui_count - UI_LIMIT}줄. CSS로 옮기거나 분리 검토.")
    if llm_ok:
        print(f"✅ llm_client.py 통과 — 여유 {LLM_LIMIT - llm_count}줄")
    else:
        print(f"❌ llm_client.py 초과 — {llm_count - LLM_LIMIT}줄.")

    return 0 if (logic_ok and data_ok and ui_ok and llm_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
