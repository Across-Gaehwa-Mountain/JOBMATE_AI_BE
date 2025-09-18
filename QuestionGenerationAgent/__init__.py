import logging
import os
import json
from typing import List
from openai import AzureOpenAI

async def main(request: dict) -> List[str]:
    """
    심층적인 질문을 생성하는 에이전트입니다.
    """
    logging.info("Executing Question Generation Agent.")
    logging.info(f"Request data: {request}")

    try:
        # Azure OpenAI 클라이언트 초기화
        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version="2024-02-15-preview"
        )

        # 요청 데이터 추출
        document_content = request.get("document_content", "")
        user_summary = request.get("user_summary", "")

        # 시스템 프롬프트
        system_prompt = """당신은 경험이 풍부한 동료입니다. 
        주어진 문서를 바탕으로 사용자의 이해도를 더 깊게 할 수 있는 2-3개의 통찰력 있는 질문을 생성해주세요.
        
        질문은 다음 형식의 JSON 배열로 응답해주세요:
        ["질문1", "질문2", "질문3"]
        
        질문은 다음과 같은 특징을 가져야 합니다:
        - 문서의 핵심 개념을 더 깊이 이해할 수 있도록 하는 질문
        - 실제 적용이나 실무와 연결되는 질문
        - 비판적 사고를 유도하는 질문"""

        # 사용자 프롬프트
        user_prompt = f"""문서 내용:
        {document_content}
        
        사용자 요약:
        {user_summary}
        
        위 문서를 바탕으로 사용자의 이해도를 더 깊게 할 수 있는 질문을 생성해주세요."""

        # Azure OpenAI API 호출
        response = client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=800
        )

        # 응답 파싱
        ai_response = response.choices[0].message.content
        logging.info(f"AI Response: {ai_response}")
        
        # JSON 파싱 시도
        try:
            questions = json.loads(ai_response)
            if isinstance(questions, list):
                return questions
            else:
                raise ValueError("Response is not a list")
        except (json.JSONDecodeError, ValueError):
            # JSON 파싱 실패 시 기본 질문 반환
            logging.warning("Failed to parse AI response as JSON, using default questions")
            return [
                "이 문서의 핵심 개념을 실제 상황에 어떻게 적용할 수 있을까요?",
                "문서에서 제시된 내용에 대해 다른 관점에서 생각해볼 수 있는 부분은 무엇인가요?",
                "이 내용을 바탕으로 추가로 학습해야 할 영역은 무엇이라고 생각하시나요?"
            ]

    except Exception as e:
        logging.error(f"Error in QuestionGenerationAgent: {str(e)}")
        # 오류 발생 시 기본 질문 반환
        return [
            "API 호출 중 오류가 발생했습니다. 서비스 연결을 확인해주세요.",
            "문서의 핵심 내용을 다시 한번 정리해보시겠어요?",
            "추가로 궁금한 점이 있으시면 언제든 말씀해주세요."
        ]
