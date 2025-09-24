import logging
import uuid
import os
import json
import re  # 추가: 파싱 강화 위해 regex
from typing import List
from openai import AzureOpenAI
from shared_code.models import NextAction

# 개선: 클라이언트 초기화 전에 환경 변수 체크 (CEA 스타일)
try:
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
    AZURE_OPENAI_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version="2024-08-01-preview"  # 수정: 최신 preview 버전으로 업데이트 (2025 기준 확인 필요)
    )
except KeyError as e:
    logging.critical(f"Missing required environment variable: {e}")
    client = None

def main(request: dict) -> List[dict]:  # 수정: async 제거 (Durable Functions 활동 함수는 동기 추천)
    """
    다음 할 일을 제안하는 에이전트입니다.
    """
    logging.info("Executing Action Item Suggestion Agent.")
    logging.info(f"Request data: {request}")

    if not client:
        logging.error("Azure OpenAI client is not initialized.")
        return [NextAction(id=str(uuid.uuid4()), title="클라이언트 초기화 실패", description="환경 변수를 확인하세요.", category="기타", estimatedTime="즉시", completed=False, priority="high").to_dict()]

    # Initialize ai_response to avoid UnboundLocalError
    ai_response = None

    try:
        # 요청 데이터 추출
        document_content = request.get("document_content", "")
        user_summary = request.get("user_summary", "")
        evaluation = request.get("evaluation", {})  # Orchestrator에서 전달 가정 (CEA 결과)
        evaluation_str = json.dumps(evaluation) if evaluation else "No evaluation data provided."
        logging.info(f"Evaluation data: {evaluation_str}")  # 추가: 디버깅 위해 로깅

        # 시스템 프롬프트 (CoT 적용: 명시적 스텝 지시, Few-Shot 추가)
        system_prompt = """당신은 도움이 되는 프로젝트 시니어 매니저입니다.
        
        주어진 문서, 사용자 요약, 그리고 이해도 평가 결과를 분석하여 구체적이고 실행 가능한 다음 할 일을 아래의 JSON 배열 형식으로만 제안해주세요.
        Think step by step internally to reason through the process, but only output the pure JSON array. No additional text.

        **반드시** 다음 형식의 JSON 배열만 응답해주세요:
        [
            {
                "id": "string (고유 식별자)",
                "title": "간단한 할 일 제목",
                "description": "구체적인 설명",
                "category": "카테고리",
                "estimatedTime": "예상 소요 시간 (예: 30분, 1시간, 2-3시간)",
                "completed": false,
                "priority": "high|medium|low"
            },
            ... (2~6개)
        ]

        ---

        ### 생성 절차 (내부적으로 step by step으로 따르세요)
        Step 1: 문서와 요약을 분석해 핵심 개념과 지식 갭을 식별하세요 (CEA의 good_points, improvement_points, missed_points, mentor_comment 참조).
        Step 2: 갭과 강점에 초점 맞춰 액션 아이디어 brainstorm (e.g., 약점 보완, 강점 강화, 추가 학습/실습).
        Step 3: 각 액션의 priority, category, estimatedTime을 판단 (e.g., missed_points 기반은 high priority, 시간은 현실적 추정).
        Step 4: 2-6개로 필터링, 중복 제거, 실행 가능성 확인.
        Step 5: 최종 JSON 배열 출력 (id는 임의 생성, completed 항상 false).

        **중요**:
        - CEA 약점(improvement_points/missed_points)을 우선 타겟팅한 액션 (보고서 품질 향상).
        - 각 할 일은 구체적이고 실행 가능한 행동이어야 합니다 (e.g., "X 자료 검색" 대신 "Google에서 'Y 주제' 검색 후 3개 기사 요약").
        - priority는 "high", "medium", "low" 중 하나여야 합니다.
        - estimatedTime은 각 할 일의 예상 소요 시간을 나타내야 합니다. 범위가 아닌 시간(1시간)이거나, 범위(예: 2-3시간)일 수 있습니다. 4시간을 초과하는 경우 "4시간 이상"로 표현하세요.
        - completed는 항상 false로 설정하세요.
        - 다른 텍스트나 설명 없이 반드시 JSON만 응답하세요.

        ---

        ### Few-Shot 예시 (이 패턴을 따르세요)
        예시 입력: [문서]: "기후 변화는 CO2 증가로 발생." [요약]: "CO2 때문." [CEA]: {"score":70, "improvement_points":["예측 누락"], "missed_points":["2100년 2도 상승"], "mentor_comment":"깊이 부족"}

        내부 CoT (출력 금지): Step 1: 갭 - 예측 누락. Step 2: 액션 아이디어 - 예측 자료 조사, 적용 계획. Step 3: high for missed, category '조사', time 1시간. Step 4: 3개 선정.

        출력 JSON:
        [
            {"id": "1", "title": "예측 자료 조사", "description": "문서의 2100년 기온 상승 예측 관련 자료를 온라인에서 검색하고 요약하세요.", "category": "조사", "estimatedTime": "1시간", "completed": false, "priority": "high"},
            {"id": "2", "title": "CO2 감소 계획 세우기", "description": "개인 차원에서 CO2 줄이는 방법 3가지를 나열하고 실천 계획을 세우세요.", "category": "실습", "estimatedTime": "30분", "completed": false, "priority": "medium"},
            {"id": "3", "title": "관련 책 읽기", "description": "기후 변화 관련 책 한 챕터를 읽고 노트하세요.", "category": "학습", "estimatedTime": "2시간", "completed": false, "priority": "low"}
        ]
        """

        # 사용자 프롬프트 (CEA 결과 포함)
        user_prompt = f"""문서 내용:
        {document_content}

        사용자 요약:
        {user_summary}

        이해도 평가 결과:
        {evaluation_str}

        위 정보를 바탕으로, 각 할 일에 대해 id, title, description, category, estimatedTime, completed(false), priority(high|medium|low)를 포함하여 2~6개의 구체적인 다음 할 일을 JSON 배열로 제안해주세요. 반드시 JSON만 응답하세요.
        """

        # Azure OpenAI API 호출 (옵션 최적화: CoT 균형)
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=1500,  
            temperature=0.3 
        )

        # 응답 파싱 (강화: regex 사용)
        ai_response = response.choices[0].message.content if response.choices else None
        logging.info(f"AI Response: {ai_response}")
        
        if ai_response:
            ai_response_clean = ai_response.strip()
            # 추가: regex로 JSON 배열 추출 (노이즈 대비)
            match = re.search(r'\[.*?\]', ai_response_clean, re.DOTALL)
            if match:
                ai_response_clean = match.group(0)
            else:
                raise ValueError("No JSON array found in response")

            actions_data = json.loads(ai_response_clean)
            if isinstance(actions_data, list):
                actions: List[dict] = []
                for action_data in actions_data:
                    if isinstance(action_data, dict):
                        # 모든 필드가 없을 경우 기본값 지정 (기존 유지)
                        action = NextAction(
                            id=action_data.get("id", str(uuid.uuid4())),
                            title=action_data.get("title", "문서의 핵심 개념 정리"),
                            description=action_data.get("description", "문서의 주요 내용을 요약하고 정리하세요."),
                            category=action_data.get("category", "기타"),
                            estimatedTime=action_data.get("estimatedTime", "1시간"),
                            completed=action_data.get("completed", False),
                            priority=action_data.get("priority", "high")
                        )
                        actions.append(action)
                if actions:
                    return [action.to_dict() for action in actions]
                else:
                    raise ValueError("No valid actions found")
            else:
                raise ValueError("Response is not a list")
        else:
            raise ValueError("Empty AI response")

    except Exception as e:
        logging.error(f"Error in ActionItemSuggestionAgent: {str(e)}")
        # 기본 액션 반환 (CEA 기반으로 약간 동적화, 하지만 기본 유지)
        actions = [
            NextAction(
                id=str(uuid.uuid4()),
                title="문서 재확인",
                description="문서를 다시 읽어보시기 바랍니다.",
                category="정리",
                estimatedTime="20분",
                completed=False,
                priority="medium"
            ),
            NextAction(
                id=str(uuid.uuid4()),
                title="CEA 약점 보완",
                description="평가 결과의 improvement_points를 검토하고 관련 자료를 찾아보세요.",
                category="조사",
                estimatedTime="1시간",
                completed=False,
                priority="high"
            )
        ]
        return [action.to_dict() for action in actions]