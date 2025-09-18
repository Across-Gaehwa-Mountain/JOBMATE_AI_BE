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
        
        # 요청 데이터 구조 검증 (SAS URL 또는 Base64 중 하나 허용)
        user_summary = request_data.get('user_summary')
        files = request_data.get('files', []) or []
        blob_urls = request_data.get('blob_urls', []) or []
        file_names = request_data.get('file_names', []) or []

        if not user_summary:
            logging.warning("Missing required field: user_summary")
            return func.HttpResponse(
                "Missing required field: user_summary", 
                status_code=400
            )

        if (not files) and (not blob_urls):
            logging.warning("Either 'files' (base64) or 'blob_urls' (SAS) must be provided")
            return func.HttpResponse(
                "Either 'files' (base64) or 'blob_urls' (SAS) must be provided", 
                status_code=400
            )

        # file_names가 제공되면 길이 일치 검증 (제공 안하면 에이전트에서 유추)
        payload_count = len(files) if files else len(blob_urls)
        if file_names and len(file_names) != payload_count:
            logging.warning("Length of file_names must match files/blob_urls")
            return func.HttpResponse(
                "Length of file_names must match files/blob_urls", 
                status_code=400
            )

        logging.info(
            f"Request data validated. files={len(files)}, blob_urls={len(blob_urls)}, file_names={len(file_names)}"
        )
        
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
