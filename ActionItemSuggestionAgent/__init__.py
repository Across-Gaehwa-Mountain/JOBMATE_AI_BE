import logging
import asyncio
from typing import List
from shared_code.models import NextAction

async def main(request: dict) -> List[dict]:
    """
    다음 할 일을 제안하는 에이전트입니다.
    """
    logging.info("Executing Action Item Suggestion Agent.")

    # --- Gemini API 호출 로직 (할 일 제안 전용) ---
    # System Prompt: "You are a helpful project manager. Suggest concrete next actions with priorities."

    await asyncio.sleep(0.9) # Simulate API call latency

    actions = [
        NextAction(action="개념 B와 C의 관계에 대한 자료 찾아보기", priority="높음"),
        NextAction(action="문서 결론 부분 다시 읽고 한 문장으로 요약하기", priority="중간"),
    ]

    return [action.to_dict() for action in actions]
