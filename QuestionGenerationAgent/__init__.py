import logging
import os
import json
import uuid
import re  # 추가: 파싱 강화 위해 regex
from typing import List
from openai import AzureOpenAI
from shared_code.models import Question

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
    심층적인 질문을 생성하는 에이전트입니다.
    """
    logging.info("Executing Question Generation Agent.")
    logging.info(f"Request data: {request}")

    if not client:
        logging.error("Azure OpenAI client is not initialized.")
        return [Question(id=str(uuid.uuid4()), question="클라이언트 초기화 실패. 환경 변수를 확인하세요.", importance="medium", category="기타").to_dict()]

    try:
        # 요청 데이터 추출
        document_content = request.get("document_content", "")
        user_summary = request.get("user_summary", "")
        evaluation = request.get("evaluation", {})  # Orchestrator에서 전달 가정
        evaluation_str = json.dumps(evaluation) if evaluation else "No evaluation data provided."
        logging.info(f"Evaluation data: {evaluation_str}")  # 추가: 디버깅 위해 로깅

        # 시스템 프롬프트 (기존 유지, CoT 잘 적용됨)
        system_prompt = """
            당신은 경험이 풍부한 동료입니다.
            주어진 문서, 사용자 요약, 그리고 이해도 평가 결과를 바탕으로 사용자의 이해도를 더 깊게 할 수 있는 2-4개의 통찰력 있는 질문을 생성해주세요.
            Think step by step internally to reason through the process, but only output the pure JSON array. No additional text.

            출력은 반드시 **순수 JSON 배열** 형식만 허용됩니다.
            아무런 추가 설명, 코드블록, 텍스트를 붙이지 마세요.

            각 질문은 다음과 같은 JSON 객체로 구성되어야 합니다:
            {
                "question": "질문 내용",
                "importance": "high|medium|low",  // 중요도: high, medium, low 중 하나
                "category": "카테고리명"           // 예: 개념, 적용, 비판적 사고 등
            }

            출력 예시:
            [
                {"question": "이 문서의 핵심 개념은 무엇인가요?", "importance": "high", "category": "개념"},
                {"question": "이 내용을 실제 업무에 어떻게 적용할 수 있을까요?", "importance": "medium", "category": "적용"}
            ]

            ---

            ### 생성 절차 (내부적으로 step by step으로 따르세요)
            Step 1: 문서와 요약을 분석해 핵심 개념과 지식 갭을 식별하세요 (CEA의 good_points, improvement_points, missed_points 참조).
            Step 2: 갭에 초점 맞춰 질문 아이디어 brainstorm (문서 핵심 이해, 실제 적용, 비판적 사고 유도).
            Step 3: 각 질문의 importance와 category를 판단 (e.g., missed_points 기반은 high).
            Step 4: 2-4개로 필터링, 중복 제거.
            Step 5: 최종 JSON 배열 출력.

            생성 규칙:
            - CEA 약점(improvement_points/missed_points)을 우선 타겟팅한 질문 (보고서 품질 향상).
            - 문서 핵심 개념을 깊게 이해할 수 있는 질문.
            - 실제 적용/실무와 연결되는 질문.
            - 비판적 사고를 유도하는 질문.
            - 최소 2개, 최대 4개 질문 생성.
            - importance는 반드시 high, medium, low 중 하나로 지정.
            - category는 질문의 성격에 맞게 자유롭게 지정.

            ---

            ### Few-Shot 예시 (이 패턴을 따르세요)
            예시 입력: [문서]: "기후 변화는 CO2 증가로 발생." [요약]: "CO2 때문." [CEA]: {"score":70, "improvement_points":["예측 누락"], "missed_points":["2100년 2도 상승"]}

            내부 CoT (출력 금지): Step 1: 갭 - 예측 누락. Step 2: 질문 아이디어 - 예측 관련, 적용. Step 3: high for missed. Step 4: 3개 선정.

            출력 JSON:
            [
                {"question": "문서에서 언급된 2100년 기온 상승 예측에 대해 어떻게 생각하나요?", "importance": "high", "category": "개념"},
                {"question": "CO2 증가를 줄이기 위한 실무 적용 방안은 무엇일까요?", "importance": "medium", "category": "적용"},
                {"question": "이 예측의 한계점은 무엇일 수 있을까요?", "importance": "low", "category": "비판적 사고"}
            ]
        """

        user_prompt = f"""
            문서 내용: {document_content}
            사용자 요약: {user_summary}

            이해도 평가 결과: {evaluation_str}

            위 정보를 바탕으로 질문을 작성해주세요.
            출력은 반드시 JSON 배열이어야 하며, 각 질문은 question, importance, category 필드를 포함해야 합니다.
        """

        # Azure OpenAI API 호출 (기존 유지, 옵션 최적화)
        try:
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=1500,  
                temperature=0.5  
            )
            ai_response = response.choices[0].message.content if response.choices else None  
        except Exception as e:
            logging.error(f"OpenAI API 호출 중 예외 발생: {e}")
            ai_response = None

        def _extract_json_array_of_questions(text: str):
            if not text:
                raise ValueError("Empty response")
            text = text.strip()  # 추가: 앞뒤 공백 제거
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if not match:
                raise ValueError("No JSON array found")
            return json.loads(match.group(0))

        # JSON 파싱 시도 (기존 유지)
        try:
            questions_data = _extract_json_array_of_questions(ai_response)
            if not isinstance(questions_data, list):
                raise ValueError("Response is not a list")
            questions = []
            for q in questions_data:
                questions.append(
                    Question(
                        id=str(uuid.uuid4()),
                        question=q.get("question", ""),
                        importance=q.get("importance", "medium"),
                        category=q.get("category", "기타")
                    )
                )
            return [q.to_dict() for q in questions]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logging.warning(f"Failed to parse AI response as JSON: {e}")
            logging.warning(f"AI response content: {ai_response}")
            # 기본 질문 예시 (기존 유지)
            return [
                Question(id=str(uuid.uuid4()), question="오류가 발생하여 기본 질문을 출력하였습니다.", importance="medium", category="기타").to_dict(),
                Question(id=str(uuid.uuid4()), question="이 문서의 핵심 개념을 실제 상황에 어떻게 적용할 수 있을까요?", importance="high", category="적용").to_dict(),
                Question(id=str(uuid.uuid4()), question="문서에서 제시된 내용에 대해 다른 관점에서 생각해볼 수 있는 부분은 무엇인가요?", importance="medium", category="비판적 사고").to_dict(),
                Question(id=str(uuid.uuid4()), question="이 내용을 바탕으로 추가로 학습해야 할 영역은 무엇이라고 생각하시나요?", importance="low", category="학습").to_dict()
            ]

    except Exception as e:
        logging.error(f"Error in QuestionGenerationAgent: {str(e)}")
        # 오류 발생 시 기본 질문 반환 (기존 유지)
        return [
            Question(id=str(uuid.uuid4()), question="API 호출 중 오류가 발생했습니다. 서비스 연결을 확인해주세요.", importance="medium", category="기타").to_dict(),
            Question(id=str(uuid.uuid4()), question="문서의 핵심 내용을 다시 한번 정리해보시겠어요?", importance="high", category="개념").to_dict(),
            Question(id=str(uuid.uuid4()), question="추가로 궁금한 점이 있으시면 언제든 말씀해주세요.", importance="low", category="기타").to_dict()
        ]