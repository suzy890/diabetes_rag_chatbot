"""Supabase 연결 점검 스크립트.

실행:  .venv/bin/python tests/check_connection.py
비밀키는 절대 출력하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config
import database


def main() -> int:
    print("── Supabase 연결 점검 ──")
    print(f"URL        : {config.SUPABASE_URL or '(비어 있음)'}")
    print(f"KEY        : {'설정됨 (' + str(len(config.SUPABASE_KEY)) + '자)' if config.SUPABASE_KEY else '(비어 있음)'}")
    print(f"APP_VERSION: {config.APP_VERSION}")

    ok, message = database.check_connection()
    print(f"\n결과: {'✅ ' if ok else '❌ '}{message}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
