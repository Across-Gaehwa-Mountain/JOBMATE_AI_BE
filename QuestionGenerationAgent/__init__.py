import logging
import asyncio
from typing import List

async def main(request: dict) -> List[str]:
    """
    심층적인 질문을 생성하는 에이전트입니다.
    """
    logging.info("Executing Question Generation Agent.")

    # --- Gemini API 호출 로직 (질문 생성 전용) ---
    # System Prompt: "You are a senior colleague. Based on the document, create 2-3 insightful questions."
    
    await asyncio.sleep(0.8) # Simulate API call latency

    questions = [
        "문서에서 언급된 리스크 A를 완화할 다른 방법은 무엇일까요?",
        "핵심 개념 B가 실제 업무에 적용될 때 발생할 수 있는 잠재적인 문제는 무엇이라고 생각하나요?"
    ]

    return questions
