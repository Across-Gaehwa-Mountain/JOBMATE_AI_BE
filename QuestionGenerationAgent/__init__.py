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
        
        출력은 반드시 **순수 JSON 배열** 형식만 허용됩니다. 
        아무런 추가 설명, 코드블록, 텍스트를 붙이지 마세요.

        출력 예시:
        ["질문1", "질문2", "질문3"]

        생성 규칙:
        - 문서 핵심 개념을 깊게 이해할 수 있는 질문
        - 실제 적용/실무와 연결되는 질문
        - 비판적 사고를 유도하는 질문
        - 최소 2개, 최대 4개 질문 생성
        """

        # 사용자 프롬프트
        user_prompt = f"""문서 내용:
        {document_content}

        사용자 요약:
        {user_summary}

        위 정보를 바탕으로 질문을 작성해주세요.
        출력은 반드시 JSON 배열이어야 하며, 질문 문자열만 포함해야 합니다.
        """

        # Azure OpenAI API 호출
        try:
            response = client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=800
            )
            print(f"response: {response}")
            print(f"response.choices: {getattr(response, 'choices', None)}")
            ai_response = None
            if response and hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                print(f"choice: {choice}")
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    ai_response = choice.message.content
            print(f"ai_response: {ai_response}")
        except Exception as e:
            print(f"OpenAI API 호출 중 예외 발생: {e}")
            logging.error(f"OpenAI API 호출 중 예외 발생: {e}")
            ai_response = None

        def _extract_json_array(text: str):
            first = text.find('[')
            last = text.rfind(']')
            if first == -1 or last == -1 or first > last:
                raise ValueError("No JSON array found")
            return json.loads(text[first:last+1])
        
        # JSON 파싱 시도
        try:
            questions = _extract_json_array(ai_response)
            if isinstance(questions, list):
                return questions
            else:
                raise ValueError("Response is not a list")
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Failed to parse AI response as JSON: {e}")
            logging.warning(f"AI response content: {ai_response}")
            return [
                "오류가 발생하여 기본 질문을 출력하였습니다.",
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
