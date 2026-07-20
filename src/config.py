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
EMBED_VERSION = "nemotron-2048-overlap-v1"

# 답변 생성 설정 (연구 표준화 — D30: 창의성보다 일관성)
LLM_TEMPERATURE = 0.2
# 근거 충분성 3단계 임계값 (RAG_RULES §3, 잠정값 — 파일럿에서 튜닝, U4)
#   최상위 청크 유사도 ≥ 상한=충분 / 하한~상한=부분 / < 하한=부족(보류)
EVIDENCE_UPPER = 0.45
EVIDENCE_LOWER = 0.30
RAG_TOP_K = 5          # 검색해 올 청크 수
RAG_SELECT_N = 3       # 답변 생성에 실제로 넣을 상위 청크 수

# 모든 연구 데이터에 기록할 버전값 (research-data.md 규칙)
APP_VERSION = "0.1.0"


def check_secrets() -> None:
    """필수 접속정보가 없으면 즉시 알린다. (실패를 성공으로 보고하지 않기 위함)"""
    missing = [n for n, v in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY)) if not v]
    if missing:
        raise RuntimeError(f"접속정보가 비어 있습니다: {', '.join(missing)} (로컬은 .env, 배포는 앱 시크릿)")
