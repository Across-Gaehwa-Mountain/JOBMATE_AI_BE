import logging
import os
import json
import re
from openai import AzureOpenAI, APIError
from shared_code.models import Feedback

# 개선점 1: 클라이언트 초기화를 함수 밖으로 이동
# Azure Function은 실행 간 상태를 유지하지 않지만, 인스턴스가 살아있는 동안 (Warm Start) 클라이언트를 재사용할 수 있습니다.
# 또한, 설정 로딩을 한 곳으로 모아 관리합니다.
try:
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
    AZURE_OPENAI_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version="2024-02-15-preview"
    )
except KeyError as e:
    # 필수 환경 변수가 없는 경우, 시작 시점에 에러를 발생시켜 문제를 빨리 파악
    logging.critical(f"Missing required environment variable: {e}")
    client = None

def main(request: dict) -> dict:
    """
    [개선됨] 이해도 점수와 피드백을 생성하는 에이전트
    """
    logging.info("Executing Comprehension Evaluation Agent.")

    if not client:
        # 클라이언트 초기화 실패 시, 명확한 에러 반환
        return _create_error_feedback("Azure OpenAI client is not initialized. Check environment variables.")

    # Initialize ai_response_content to avoid UnboundLocalError
    ai_response_content = None
    
    try:
        document_content = request.get("document_content", "")
        user_summary = request.get("user_summary", "")

        if not document_content or not user_summary:
            return _create_error_feedback("Document content or user summary is missing.")

        # 개선점 2: 더욱 정교하고 구조화된 프롬프트 (Chain of Thought + Persona + Few-Shot)
        system_prompt = """
        당신은 주니어 사원의 보고(문서 + 사용자의 요약)를 검토하는 시니어 분석가(사수)입니다.
        목표는 단순히 점수를 매기는 것이 아니라, 주니어가 무엇을 잘했고 무엇을 놓쳤는지 명확히 알려주어 실질적으로 성장할 수 있게 돕는 것입니다.

        주의: 모델의 내부 사적 추론(Chain-of-Thought)은 절대 출력하지 마십시오.
        대신 'reasoning_summary' 항목에 **간결한 판단 근거(핵심 포인트 3~5개)**만 제공하세요. Think step by step internally, but only output the final JSON.

        ---

        ### 평가 절차 (내부적으로 step by step으로 따르세요)
        Step 1: 문서 내용을 읽고 핵심 개념(주장/데이터/결론)을 3~5개 식별하세요. 각 개념의 중요도를 고려.
        Step 2: 사용자 요약을 분석해 각 핵심 개념이 얼마나 정확히/깊이 있게 반영되었는지 비교하세요 (맞는 점, 왜곡된 점, 누락된 점 분류).
        Step 3: 비교 결과로 강점(good_points), 개선점(improvement_points), 누락점(missed_points)을 brainstorm하세요. 각 포인트에 구체적 예시와 행동 제안 포함.
        Step 4: 전체 이해도를 바탕으로 점수 산정 (보수적). 멘토 코멘트와 reasoning_summary 요약.
        Step 5: 최종 JSON 형식으로 출력. reasoning_summary는 위 스텝들의 핵심 근거만 3-5개 bullet으로.

        ---

        ### 점수 가이드라인
        - 90–100: 핵심 개념 거의 완벽 반영, 깊이 있는 설명 포함  
        - 75–89: 핵심 대부분 반영, 일부 깊이 부족  
        - 60–74: 중요 포인트 일부 누락 또는 오해  
        - 0–59: 핵심 다수 누락 또는 근본적 오해  

        ---

        ### Few-Shot 예시 (이 패턴을 따르세요)
        예시 입력: [문서 내용]: "기후 변화는 CO2 증가로 인해 발생하며, 2100년까지 2도 상승 예상." [사용자 요약]: "기후 변화는 CO2 때문."

        내부 CoT (출력 금지): Step 1: 핵심 - CO2 원인, 2100년 2도 상승. Step 2: 요약은 원인만, 상승 예측 누락. Step 3: 강점 - 원인 파악; 개선 - 예측 추가; 누락 - 없음. Step 4: 점수 70 (부분 이해).

        출력 JSON:
        {
            "title": "기후 변화 개요",
            "score": 70,
            "good_points": ["CO2 증가를 원인으로 정확히 파악함."],
            "improvement_points": ["예측 부분(2100년 2도 상승)을 추가로 설명하면 더 좋음 - 다음에 데이터 기반 예측 포함."],
            "missed_points": [],
            "mentor_comment": "기본 이해는 좋으나 깊이 부족. 더 공부하세요.",
            "reasoning_summary": ["핵심 개념 2개 중 1개만 반영", "예측 누락으로 점수 하향", "개선 제안 행동 중심"]
        }

        ---

        ### 출력 형식 (반드시 JSON만 사용)
        ```json
        {   "title": "<문서의 핵심을 제목으로 붙여주세요>",
            "score": <0-100 정수>,
            "good_points": ["<구체적 칭찬 — 무엇을 잘했는가>"],
            "improvement_points": ["<구체적 지적 + 개선 방법 — 행동 가능한 문장>"],
            "missed_points": ["<완전히 누락된 핵심 개념>"],
            "mentor_comment": "<짧은 멘토 총평 (1-2문장)>",
            "reasoning_summary": ["<판단 근거 1 — 간결>", "<판단 근거 2 — 간결>", ...]
        }
        """

        user_prompt = f"아래 문서와 주니어 사원의 요약문을 검토하고 평가해주세요.\n\n[문서 내용]:\n{document_content}\n\n[사용자 요약]:\n{user_summary}"

        logging.info("Making Azure OpenAI API call...")
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2, # 점수 평가와 같은 작업은 일관된 결과를 위해 온도를 낮게 설정
            max_completion_tokens=1500
        )

        ai_response_content = response.choices[0].message.content
        logging.info("Successfully received AI response.")
        logging.info(f"Raw AI response: {ai_response_content}")
        
        # 개선점 4: 견고한 JSON 파싱 및 예외 처리
        evaluation_data = _parse_ai_response(ai_response_content)
        
        feedback = Feedback(
            title=evaluation_data.get("title", ""),
            score=evaluation_data.get("score", 0),
            good_points=evaluation_data.get("good_points", []),
            improvement_points=evaluation_data.get("improvement_points", []),
            missed_points=evaluation_data.get("missed_points", []),
            mentor_comment=evaluation_data.get("mentor_comment", []),
            reasoning_summary=evaluation_data.get("reasoning_summary", [])
        )
        logging.info("Successfully parsed AI response and created Feedback object.")
        return feedback.to_dict()

    except APIError as e:
        logging.error(f"Azure OpenAI API Error: {e.status_code} - {e.message}")
        return _create_error_feedback(f"서비스 연결 중 오류가 발생했습니다 (API Error: {e.status_code}).")

    except Exception as e:
        # Check if ai_response_content was set before logging
        response_info = f"Response: {ai_response_content}" if ai_response_content is not None else "No response received"
        logging.error(f"Failed to process request: {e}. {response_info}")
        return _create_error_feedback("AI 응답을 처리하는 중 오류가 발생했습니다.")

def _parse_ai_response(response_content: str) -> dict:
    """
    AI 응답을 안전하게 파싱하는 함수
    여러 방법을 시도하여 JSON을 추출합니다.
    """
    if not response_content:
        raise ValueError("응답 내용이 비어있습니다.")
    
    # 방법 1: 직접 JSON 파싱 시도
    try:
        return json.loads(response_content)
    except json.JSONDecodeError:
        logging.warning("직접 JSON 파싱 실패, 정제된 텍스트로 재시도...")
    
    # 방법 2: JSON 블록 추출 (```json ... ``` 또는 ``` ... ```)
    json_patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{.*\}',  # 중괄호로 둘러싸인 JSON 객체
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, response_content, re.DOTALL)
        for match in matches:
            try:
                # 앞뒤 공백 제거
                cleaned_match = match.strip()
                if cleaned_match:
                    parsed_data = json.loads(cleaned_match)
                    logging.info(f"정규식 패턴으로 JSON 파싱 성공: {pattern}")
                    return parsed_data
            except json.JSONDecodeError:
                continue
    
    # 방법 3: 응답에서 JSON 유사 구조 추출
    try:
        # score, good_points, improvement_points, missed_points 키워드로 추출
        extracted_data = _extract_structured_data(response_content)
        if extracted_data:
            logging.info("구조화된 데이터 추출로 파싱 성공")
            return extracted_data
    except Exception as e:
        logging.warning(f"구조화된 데이터 추출 실패: {e}")
    
    # 모든 방법이 실패한 경우
    raise ValueError(f"JSON 파싱에 실패했습니다. 원본 응답: {response_content[:200]}...")

def _extract_structured_data(text: str) -> dict:
    """
    텍스트에서 구조화된 데이터를 추출하는 함수
    """
    result = {
        "score": 0,
        "good_points": [],
        "improvement_points": [],
        "missed_points": []
    }
    
    # 점수 추출 (0-100 사이의 숫자)
    score_match = re.search(r'"score":\s*(\d+)', text)
    if score_match:
        result["score"] = int(score_match.group(1))
    
    # 각 배열 추출
    for key in ["good_points", "improvement_points", "missed_points"]:
        pattern = rf'"{key}":\s*\[(.*?)\]'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            # 배열 내용에서 문자열 추출
            array_content = match.group(1)
            items = re.findall(r'"([^"]*)"', array_content)
            result[key] = items
    
    # 최소한 score가 있으면 유효한 데이터로 간주
    if result["score"] > 0 or any(result[key] for key in ["good_points", "improvement_points", "missed_points"]):
        return result
    
    return None

def _create_error_feedback(message: str) -> dict:
    """오류 발생 시 일관된 피드백 객체를 생성하는 헬퍼 함수"""
    feedback = Feedback(
        title="분석 오류",
        score=0,
        good_points=[],
        improvement_points=[message],
        missed_points=["오류로 인해 분석을 완료할 수 없습니다."]
    )
    return feedback.to_dict()

