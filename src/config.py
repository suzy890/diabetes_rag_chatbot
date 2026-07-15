"""환경설정과 버전값 로딩. 비밀정보는 코드가 아닌 외부에서 읽는다 (CLAUDE.md 규칙).

두 환경 모두에서 동작한다:
  - 로컬 개발: 프로젝트 루트의 .env 파일
  - 배포(Streamlit Cloud): 앱 시크릿 (환경변수 또는 st.secrets)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 로컬 개발용 .env를 읽는다. 배포 환경에는 이 파일이 없으며(=커밋 금지), 그때는 시크릿을 쓴다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _read_secret(name: str) -> str:
    """환경변수 → Streamlit 시크릿 순으로 찾는다. 없으면 빈 문자열."""
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


SUPABASE_URL = _read_secret("SUPABASE_URL")
SUPABASE_KEY = _read_secret("SUPABASE_KEY")

# 외부 LLM·임베딩 (NVIDIA NIM — 키 1개로 둘 다, D29/D32). OpenAI 호환 엔드포인트.
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
LLM_API_KEY = _read_secret("LLM_API_KEY").strip().strip('"').strip("'")
LLM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
EMBED_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
# 문서 청크를 임베딩한 버전 — 질문도 같은 모델로 임베딩해야 검색이 된다.
EMBED_VERSION = "nemotron-2048-basic512-clean-v1"

# 모든 연구 데이터에 기록할 버전값 (research-data.md 규칙)
APP_VERSION = "0.1.0"

# 이 시간 안에 시작되고 아직 끝나지 않은 세션은 '같은 접속'으로 보고 이어받는다.
# 새로고침으로 세션이 중복 생성되는 것을 막는다. (값은 파일럿에서 조정 — 미결정)
SESSION_RESUME_HOURS = 2


def check_secrets() -> None:
    """필수 접속정보가 없으면 즉시 알린다. (실패를 성공으로 보고하지 않기 위함)"""
    missing = [n for n, v in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY)) if not v]
    if missing:
        raise RuntimeError(f"접속정보가 비어 있습니다: {', '.join(missing)} (로컬은 .env, 배포는 앱 시크릿)")
