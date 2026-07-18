"""외부 LLM·임베딩 API(NVIDIA NIM) 호출 배관 — 기계적 인프라(로직 아님).

모든 호출의 토큰·지연·상태를 model_calls에 남긴다(비용 추적). rag.py 등은
이 모듈을 거쳐 API를 부른다. 모델·제공사가 바뀌어도 여기만 고치면 된다.
(database.py=DB 배관, ui.py=화면 배관과 같은 취지로 별도 관리 — D41)
"""

import json
import time

import httpx

import config
import database


def call(path: str, payload: dict, call_type: str, system_version_id: str,
         participant_id: str | None = None, message_id: str | None = None) -> dict:
    """NVIDIA API를 한 번 호출하고 응답 본문(dict)을 돌려준다. 비용은 model_calls에 기록."""
    started = time.perf_counter()
    status, itok, otok = "success", 0, 0
    try:
        r = httpx.post(f"{config.NVIDIA_BASE_URL}/{path}",
                       headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                       json=payload, timeout=90.0)
        r.raise_for_status()
        body = r.json()
        usage = body.get("usage", {})
        itok = usage.get("prompt_tokens") or usage.get("total_tokens", 0)
        otok = usage.get("completion_tokens", 0)
        return body
    except Exception:
        status = "failure"
        raise
    finally:
        database.log_model_call(
            call_type=call_type, system_version_id=system_version_id, provider="nvidia",
            model_name=payload.get("model"), input_tokens=itok, output_tokens=otok,
            latency_ms=int((time.perf_counter() - started) * 1000), status=status,
            participant_id=participant_id, related_message_id=message_id)


def stream(payload: dict, call_type: str, system_version_id: str,
           participant_id: str | None, message_id: str | None):
    """LLM 답변을 스트리밍으로 받아 텍스트 조각을 하나씩 내보낸다(generator).

    끝나면(성공·실패 모두) 토큰·지연·상태를 model_calls에 기록한다.
    """
    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    started = time.perf_counter()
    status, itok, otok = "success", 0, 0
    try:
        with httpx.stream("POST", f"{config.NVIDIA_BASE_URL}/chat/completions",
                          headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                          json=payload, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                obj = json.loads(data)
                if obj.get("usage"):
                    itok = obj["usage"].get("prompt_tokens", 0)
                    otok = obj["usage"].get("completion_tokens", 0)
                for choice in obj.get("choices", []):
                    delta = choice.get("delta", {}).get("content")
                    if delta:
                        yield delta
    except Exception:
        status = "failure"
        raise
    finally:
        database.log_model_call(
            call_type=call_type, system_version_id=system_version_id, provider="nvidia",
            model_name=payload.get("model"), input_tokens=itok, output_tokens=otok,
            latency_ms=int((time.perf_counter() - started) * 1000), status=status,
            participant_id=participant_id, related_message_id=message_id)
