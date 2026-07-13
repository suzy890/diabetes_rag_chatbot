"""환경설정과 버전값 로딩. 비밀정보는 코드가 아닌 .env에서 읽는다 (CLAUDE.md 규칙)."""

from pathlib import Path

from dotenv import load_dotenv
import os

# 프로젝트 루트의 .env를 읽는다 (src/ 안에서 실행해도 동작하도록 경로를 명시)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# 모든 연구 데이터에 기록할 버전값 (research-data.md 규칙)
APP_VERSION = "0.1.0"


def check_secrets() -> None:
    """필수 접속정보가 없으면 즉시 알린다. (실패를 성공으로 보고하지 않기 위함)"""
    missing = [n for n, v in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY)) if not v]
    if missing:
        raise RuntimeError(f".env에 다음 값이 비어 있습니다: {', '.join(missing)}")
