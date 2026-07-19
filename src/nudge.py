"""넛지 트리거 조건과 승인 템플릿 선택.

규칙: NUDGE_RULES.md
- 연구자가 승인한 템플릿을 우선 사용한다. (MVP는 LLM 문장화 없음 — 모든 참여자가 동일한 자극)
- 화면을 그리지 않는다. app.py가 결과를 받아 렌더링한다.
"""

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import database

# 승인 템플릿은 코드가 아니라 편집 가능한 데이터 파일에서 읽는다(연구자가 문구 수정·의료검토 용이).
# 문구 원칙: 한 번에 하나 · 짧고 쉬움 · 제안형 · 죄책감/공포/강압 금지 · 거절·나중 선택지 제공.
_DATA = json.loads((Path(__file__).resolve().parent.parent
                    / "prompts" / "nudge_templates.json").read_text(encoding="utf-8"))

TEMPLATE_VERSION = _DATA["template_version"]
MAX_NUDGES_PER_DAY = _DATA["max_per_day"]      # 하루 전체 넛지 최대 노출 (연구팀 확정: 3회)
DEFERRED = _DATA["deferred_label"]
COMMIT_OPTIONS = _DATA["commit_options"]        # 행동 제안에 대한 약속 선택지
TEMPLATES = _DATA["templates"]


def get_commit_feedback(committed: bool) -> str:
    """행동 약속 응답 뒤에 보여줄 격려 문구. committed=True면 칭찬, 아니면 위로.

    끝에 질문을 유도한다("궁금한 점이 있으면 물어봐 주세요"). 승인 템플릿(자유생성 아님).
    """
    return _DATA["commit_feedback"]["committed" if committed else "declined"]


def get_followup(template_key: str, response: str) -> str | None:
    """넛지 응답에 이어질 '행동 제안' 문구를 찾는다. 없으면 None (예: 거절·미완료 응답).

    넛지의 핵심은 질문이 아니라 행동 유도다. 참여자가 먹었다고 하면
    '식후 가볍게 걷기' 같은 작은 행동을 제안한다(운동요법 상기 수준, 의료 판단 금지).
    """
    template = next((t for t in TEMPLATES if t["key"] == template_key), None)
    if not template:
        return None
    return template.get("followups", {}).get(response)


def find_template(now: datetime) -> dict | None:
    """현재 시간대에 해당하는 승인 템플릿을 찾는다. 해당 시간대가 없으면 넛지를 띄우지 않는다."""
    hour = now.hour
    for template in TEMPLATES:
        if template["start_hour"] <= hour < template["end_hour"]:
            return template
    return None


def local_day_start(timezone_name: str) -> datetime:
    """참여자 기준 시간대의 '오늘 0시'. 하루 제한을 참여자 현지 기준으로 계산하기 위함."""
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    return datetime.combine(now_local.date(), time.min, tzinfo=tz)


def select_nudge(participant: dict, now: datetime | None = None) -> dict | None:
    """지금 이 참여자에게 보여줄 넛지를 규칙에 따라 고른다. 없으면 None.

    반복 제한(NUDGE_RULES.md):
      - 해당 시간대가 아니면 띄우지 않는다
      - 같은 넛지는 하루 1회만
      - 하루 전체 최대 MAX_NUDGES_PER_DAY 회

    now는 테스트에서 시간대를 지정하기 위한 것이다. 평소에는 현재 시각을 쓴다.
    """
    timezone_name = participant.get("timezone") or "Asia/Seoul"
    tz = ZoneInfo(timezone_name)
    now_local = now.astimezone(tz) if now else datetime.now(tz)

    template = find_template(now_local)
    if template is None:
        return None

    day_start = local_day_start(timezone_name)
    participant_id = participant["participant_id"]

    # 같은 넛지를 오늘 이미 보여줬으면 다시 띄우지 않는다
    if database.count_nudges_today(participant_id, day_start, template_key=template["key"]) > 0:
        return None

    # 하루 전체 노출 상한
    if database.count_nudges_today(participant_id, day_start) >= MAX_NUDGES_PER_DAY:
        return None

    return template
