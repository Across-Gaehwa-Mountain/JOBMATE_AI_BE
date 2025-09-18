import logging
import os
import json
from openai import AzureOpenAI
from shared_code.models import Feedback

async def main(request: dict) -> dict:
    """
    이해도 점수와 피드백을 생성하는 에이전트입니다.
    """
    logging.info("Executing Comprehension Evaluation Agent.")
    logging.info(f"Request data: {request}")

    try:
        # 환경 변수 확인
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_KEY")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        logging.info(f"Environment variables - Endpoint: {endpoint}, Key: {api_key[:10] if api_key else 'None'}..., Deployment: {deployment}")
        
        if not all([endpoint, api_key, deployment]):
            raise ValueError("Missing required environment variables")
        
        # Azure OpenAI 클라이언트 초기화
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-02-15-preview"
        )
        
        logging.info("Azure OpenAI client initialized successfully")

        # 요청 데이터 추출
        document_content = request.get("document_content", "")
        user_summary = request.get("user_summary", "")

        # 시스템 프롬프트
        system_prompt = """당신은 전문적인 문서 이해도 평가자입니다. 
        주어진 문서와 사용자의 요약을 분석하여 **반드시** 다음 형식의 JSON 응답만 제공해주세요:
        
        {
            "score": 85,
            "good_points": ["잘 파악한 점들"],
            "improvement_points": ["개선이 필요한 점들"],
            "missed_points": ["놓친 중요한 점들"]
        }
        
        **중요**: 
        - 점수는 0-100 사이의 정수
        - good_points, improvement_points, missed_points는 문자열 배열
        - 다른 텍스트나 설명 없이 JSON만 응답
        - JSON 형식을 정확히 지켜주세요
        - 응답은 반드시 유효한 JSON 형식이어야 합니다
        - 예시: {"score": 75, "good_points": ["점1"], "improvement_points": ["점2"], "missed_points": ["점3"]}"""

        # 사용자 프롬프트
        user_prompt = f"""문서 내용:
        {document_content}
        
        사용자 요약:
        {user_summary}
        
        위 문서와 사용자 요약을 분석하여 이해도를 평가해주세요."""

        # Azure OpenAI API 호출
        logging.info("Making Azure OpenAI API call...")
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=1000
        )
        logging.info("Azure OpenAI API call completed successfully")

        # 응답 파싱
        ai_response = response.choices[0].message.content
        logging.info(f"AI Response: {ai_response}")
        
        # JSON 파싱 시도
        try:
            # AI 응답에서 JSON 부분만 추출
            ai_response_clean = ai_response.strip()
            
            # 다양한 마크다운 형식 제거
            if ai_response_clean.startswith('```json'):
                ai_response_clean = ai_response_clean[7:]
            elif ai_response_clean.startswith('```'):
                ai_response_clean = ai_response_clean[3:]
            
            if ai_response_clean.endswith('```'):
                ai_response_clean = ai_response_clean[:-3]
            
            ai_response_clean = ai_response_clean.strip()
            
            # JSON 객체 찾기
            start_idx = ai_response_clean.find('{')
            end_idx = ai_response_clean.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                ai_response_clean = ai_response_clean[start_idx:end_idx+1]
            
            evaluation_data = json.loads(ai_response_clean)
            feedback = Feedback(
                score=evaluation_data.get("score", 0),
                good_points=evaluation_data.get("good_points", []),
                improvement_points=evaluation_data.get("improvement_points", []),
                missed_points=evaluation_data.get("missed_points", [])
            )
            logging.info("Successfully parsed AI response as JSON")
        except json.JSONDecodeError as e:
            # JSON 파싱 실패 시 기본값 사용
            logging.warning(f"Failed to parse AI response as JSON: {e}")
            logging.warning(f"Raw AI response: {ai_response}")
            logging.warning(f"Cleaned AI response: {ai_response_clean}")
            feedback = Feedback(
                score=75,
                good_points=["AI 응답을 처리하는 중 오류가 발생했습니다."],
                improvement_points=["응답 형식을 확인해주세요."],
                missed_points=["JSON 파싱 오류가 발생했습니다."]
            )

        return feedback.to_dict()

    except Exception as e:
        logging.error(f"Error in ComprehensionEvaluationAgent: {str(e)}")
        # 오류 발생 시 기본 피드백 반환
        feedback = Feedback(
            score=0,
            good_points=[],
            improvement_points=[f"API 호출 중 오류가 발생했습니다: {str(e)}"],
            missed_points=["서비스 연결을 확인해주세요."]
        )
        return feedback.to_dict()
