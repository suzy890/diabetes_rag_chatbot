"""Supabase 저장·조회 담당. 다른 모듈은 여기를 거쳐서만 DB에 접근한다 (architecture.md 규칙)."""

from functools import lru_cache

from supabase import Client, create_client

import config

# PostgREST가 "테이블 없음"을 알릴 때 쓰는 신호들.
# 이 오류가 나면 접속·인증은 성공했고 스키마만 아직 없다는 뜻이다.
_TABLE_MISSING_HINTS = ("PGRST205", "does not exist", "Could not find the table")


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Supabase 클라이언트를 만든다 (한 번만 생성해 재사용)."""
    config.check_secrets()
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def check_connection() -> tuple[bool, str]:
    """DB에 실제로 붙는지 확인한다. (연결 성공 여부, 설명) 을 돌려준다."""
    try:
        client = get_client()
    except Exception as exc:
        return False, f"설정 오류: {exc}"

    try:
        client.table("participants").select("participant_id").limit(1).execute()
        return True, "연결 성공 — participants 테이블 조회됨"
    except Exception as exc:
        message = str(exc)
        if any(hint in message for hint in _TABLE_MISSING_HINTS):
            return True, "연결 성공 — 인증 통과, 아직 테이블 없음(Step 2에서 생성 예정)"
        return False, f"연결 실패: {message}"
