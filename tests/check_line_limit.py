"""핵심 실행 코드가 500줄 제한을 지키는지 확인한다 (CLAUDE.md).

기준: 빈 줄과 주석·독스트링을 제외한 실제 코드 줄 수.
실행:  .venv/bin/python tests/check_line_limit.py
"""

import io
import tokenize
from pathlib import Path

LIMIT = 500
SRC = Path(__file__).resolve().parent.parent / "src"

# CLAUDE.md가 정한 6개 핵심 모듈 (아직 없는 파일은 건너뛴다)
MODULES = ["app.py", "rag.py", "nudge.py", "database.py", "safety.py", "config.py"]


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


def main() -> int:
    total = 0
    print(f"{'파일':<14}{'실제 코드':>10}")
    print("─" * 24)
    for name in MODULES:
        path = SRC / name
        if not path.exists():
            print(f"{name:<14}{'(아직 없음)':>10}")
            continue
        count = code_lines(path)
        total += count
        print(f"{name:<14}{count:>10}")

    print("─" * 24)
    print(f"{'합계':<14}{total:>10}  / 제한 {LIMIT}")

    if total <= LIMIT:
        print(f"\n✅ 통과 — 여유 {LIMIT - total}줄")
        return 0
    print(f"\n❌ 초과 — {total - LIMIT}줄 넘음. 코드를 단순화해야 합니다.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
