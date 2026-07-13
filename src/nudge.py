"""넛지 트리거 조건과 승인 템플릿 선택.

규칙: NUDGE_RULES.md
- 연구자가 승인한 템플릿을 우선 사용한다. (MVP는 LLM 문장화 없음 — 모든 참여자가 동일한 자극)
- 화면을 그리지 않는다. app.py가 결과를 받아 렌더링한다.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import database

TEMPLATE_VERSION = "v0.1"

# 하루 전체 넛지 최대 노출 횟수 (연구팀 확정: 3회)
MAX_NUDGES_PER_DAY = 3

# 승인 템플릿 (연구팀 승인 v0.1 — 임의 수정 금지. 바꾸려면 TEMPLATE_VERSION을 올린다)
# 문구 원칙: 한 번에 하나의 질문 · 짧고 쉬운 문장 · 제안형 · 죄책감/공포/강압 금지 · 거절·나중 선택지 제공
DEFERRED = "나중에 답할게요"

TEMPLATES = [
    {
        "key": "meal_breakfast", "start_hour": 6, "end_hour": 10,
        "health_domain": "meal", "nudge_type": "choice",
        "text": "안녕하세요. 오늘 아침 식사는 하셨어요?",
        "options": ["네, 먹었어요", "아직이요", DEFERRED],
    },
    {
        "key": "meal_lunch", "start_hour": 11, "end_hour": 14,
        "health_domain": "meal", "nudge_type": "choice",
        "text": "점심 식사는 하셨어요?",
        "options": ["네, 먹었어요", "아직이요", DEFERRED],
    },
    {
        "key": "snack_afternoon", "start_hour": 14, "end_hour": 17,
        "health_domain": "meal", "nudge_type": "choice",
        "text": "오후에 간식 드셨어요?",
        "options": ["네, 먹었어요", "아니요", DEFERRED],
    },
    {
        "key": "meal_dinner", "start_hour": 17, "end_hour": 20,
        "health_domain": "meal", "nudge_type": "choice",
        "text": "저녁 식사는 하셨어요?",
        "options": ["네, 먹었어요", "아직이요", DEFERRED],
    },
    {
        # 판단·훈계로 들리지 않도록 사실만 묻는다 (죄책감 유발 금지 규칙).
        "key": "snack_late", "start_hour": 21, "end_hour": 24,
        "health_domain": "meal", "nudge_type": "choice",
        "text": "저녁 드신 뒤에 뭔가 더 드셨어요?",
        "options": ["네, 먹었어요", "아니요", DEFERRED],
    },
]


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
