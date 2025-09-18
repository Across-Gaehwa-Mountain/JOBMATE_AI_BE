import logging
import os
import json
from typing import List
from openai import AzureOpenAI
from shared_code.models import NextAction

async def main(request: dict) -> List[dict]:
    """
    다음 할 일을 제안하는 에이전트입니다.
    """
    logging.info("Executing Action Item Suggestion Agent.")
    logging.info(f"Request data: {request}")

    # Initialize ai_response to avoid UnboundLocalError
    ai_response = None

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
        system_prompt = """당신은 도움이 되는 프로젝트 매니저입니다.
        
        주어진 문서와 사용자 요약을 분석하여 구체적이고 실행 가능한 다음 할 일을 아래의 JSON 배열 형식으로만 제안해주세요.
        
        **반드시** 다음 형식의 JSON 배열만 응답해주세요:
        [
            {
                \"id\": \"string (고유 식별자)\",
                \"title\": \"간단한 할 일 제목\",
                \"description\": \"구체적인 설명\",
                \"category\": \"카테고리\",
                \"estimatedTime\": \"예상 소요 시간 (예: 30분, 1시간, 2-3시간)\",
                \"completed\": false,
                \"priority\": \"high|medium|low\"
            },
            ... (2~6개)
        ]

        **중요**:
        - 각 할 일은 구체적이고 실행 가능한 행동이어야 합니다.
        - priority는 \"high\", \"medium\", \"low\" 중 하나여야 합니다.
        - estimatedTime은 각 할 일의 예상 소요 시간을 나타내야 합니다. 범위가 아닌 시간(1시간)이거나, 범위(예: 2-3시간)일 수 있습니다. 4시간을 초과하는 경우 \"4시간 이상\"로 표현하세요.
        - completed는 항상 false로 설정하세요.
        - 다른 텍스트나 설명 없이 반드시 JSON만 응답하세요."""

        # 사용자 프롬프트
        user_prompt = f"""문서 내용:
        {document_content}

        사용자 요약:
        {user_summary}

        위 문서와 사용자 요약을 바탕으로, 각 할 일에 대해 id, title, description, category, estimatedTime, completed(false), priority(high|medium|low)를 포함하여 2~6개의 구체적인 다음 할 일을 JSON 배열로 제안해주세요. 반드시 JSON만 응답하세요.
        
        """

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
            # AI 응답에서 JSON 부분만 추출
            ai_response_clean = ai_response.strip()
            if ai_response_clean.startswith('```json'):
                ai_response_clean = ai_response_clean[7:]
            if ai_response_clean.endswith('```'):
                ai_response_clean = ai_response_clean[:-3]
            ai_response_clean = ai_response_clean.strip()
            
            actions_data = json.loads(ai_response_clean)
            if isinstance(actions_data, list):
                actions: List[dict] = []
                for action_data in actions_data:
                    if isinstance(action_data, dict) and "action" in action_data and "priority" in action_data:
                        actions.append({
                            "action": action_data["action"],
                            "priority": action_data["priority"]
                        })
                
                if actions:
                    logging.info("Successfully parsed AI response as JSON")
                    return actions
                else:
                    raise ValueError("No valid actions found")
            else:
                raise ValueError("Response is not a list")
        except (json.JSONDecodeError, ValueError) as e:
            # JSON 파싱 실패 시 기본 할 일 반환
            logging.warning(f"Failed to parse AI response as JSON: {e}")
            # Check if ai_response was set before logging
            response_info = f"Raw AI response: {ai_response}" if ai_response is not None else "No response received"
            logging.warning(response_info)
            actions = [
                {"action": "문서의 핵심 개념을 다시 한번 정리해보기", "priority": "높음"},
                {"action": "이해가 부족한 부분에 대한 추가 자료 찾아보기", "priority": "중간"},
                {"action": "학습한 내용을 실제 상황에 적용해보기", "priority": "낮음"}
            ]
            return actions

    except Exception as e:
        logging.error(f"Error in ActionItemSuggestionAgent: {str(e)}")
        # 오류 발생 시 기본 할 일 반환
        actions = [
            {"action": "API 호출 중 오류가 발생했습니다. 서비스 연결을 확인해주세요.", "priority": "높음"},
            {"action": "문서를 다시 읽어보시기 바랍니다.", "priority": "중간"}
        ]
        return actions
