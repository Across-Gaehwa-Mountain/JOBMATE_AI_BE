import logging
import asyncio
from shared_code.models import Feedback

async def main(request: dict) -> dict:
    """
    이해도 점수와 피드백을 생성하는 에이전트입니다.
    """
    logging.info("Executing Comprehension Evaluation Agent.")

    # --- Gemini API 호출 로직 (평가 전용) ---
    # System Prompt: "You are an expert evaluator. Analyze the document and summary, then provide a score and detailed feedback."
    # 이 에이전트는 점수와 피드백 생성에만 집중합니다.
    
    await asyncio.sleep(1) # Simulate API call latency
    
    feedback = Feedback(
        score=85,
        good_points=["핵심 개념 A를 정확히 파악했습니다."],
        improvement_points=["개념 B와 C의 관계 설명이 부족합니다."],
        missed_points=["문서의 중요한 결론 부분을 놓쳤습니다."]
    )

    return feedback.to_dict()
