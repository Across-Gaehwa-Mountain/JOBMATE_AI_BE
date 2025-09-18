import logging
import azure.functions as func
import azure.durable_functions as df
import json

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    프론트엔드로부터 최초의 분석 요청을 받는 API 진입점입니다.
    """
    client = df.DurableOrchestrationClient(starter)
    
    # 요청 정보 로깅
    logging.info(f"Received HTTP request: Method={req.method}, URL={req.url}")
    logging.info(f"Request headers: {dict(req.headers)}")
    
    # Content-Type 확인
    content_type = req.headers.get('content-type', '')
    if not content_type.startswith('application/json'):
        logging.warning(f"Invalid content-type: {content_type}")
        return func.HttpResponse(
            "Content-Type must be application/json", 
            status_code=400
        )
    
    try:
        request_data = req.get_json()
        if not request_data:
            logging.warning("Empty request body")
            return func.HttpResponse(
                "Request body cannot be empty", 
                status_code=400
            )
        
        # 요청 데이터 구조 검증
        required_fields = ['file_names', 'files', 'user_summary']
        for field in required_fields:
            if field not in request_data:
                logging.warning(f"Missing required field: {field}")
                return func.HttpResponse(
                    f"Missing required field: {field}", 
                    status_code=400
                )
        
        logging.info(f"Request data validated successfully. Files count: {len(request_data.get('files', []))}")
        
    except ValueError as e:
        logging.error(f"JSON parsing error: {str(e)}")
        return func.HttpResponse(
            "Please provide valid JSON data in the request body.", 
            status_code=400
        )
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return func.HttpResponse(
            "Internal server error", 
            status_code=500
        )

    logging.info("Starting orchestration via HTTP request.")
    
    try:
        # 오케스트레이션 시작
        instance_id = await client.start_new("JobMateOrchestrator", client_input=request_data)
        logging.info(f"Started orchestration with ID = '{instance_id}'.")

        # 오케스트레이션 상태를 확인할 수 있는 URL과 함께 응답을 반환합니다.
        return client.create_check_status_response(req, instance_id)
        
    except Exception as e:
        logging.error(f"Failed to start orchestration: {str(e)}")
        return func.HttpResponse(
            "Failed to start analysis process", 
            status_code=500
        )
