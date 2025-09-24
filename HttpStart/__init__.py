import logging
import azure.functions as func
import azure.durable_functions as df
import json
import base64

# 파일 크기 제한 상수 (10MB)
MAX_TOTAL_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

def validate_file_sizes(file_objects):
    """
    모든 파일의 총 크기가 10MB를 넘는지 검사합니다.
    
    Args:
        file_objects: 업로드된 파일 객체들의 리스트
        
    Raises:
        ValueError: 총 파일 크기가 10MB를 넘을 때
    """
    total_size = 0
    file_sizes = []
    
    for file_obj in file_objects:
        if file_obj.filename:  # 파일이 실제로 업로드된 경우
            # 파일 크기 계산 (파일 포인터를 처음으로 이동)
            file_obj.seek(0, 2)  # 파일 끝으로 이동
            file_size = file_obj.tell()  # 현재 위치 (파일 크기)
            file_obj.seek(0)  # 파일 시작으로 다시 이동
            
            total_size += file_size
            file_sizes.append({
                'filename': file_obj.filename,
                'size': file_size
            })
    
    logging.info(f"Total file size: {total_size} bytes ({total_size / (1024*1024):.2f} MB)")
    logging.info(f"File sizes: {file_sizes}")
    
    if total_size > MAX_TOTAL_FILE_SIZE:
        error_msg = f"Total file size ({total_size} bytes, {total_size / (1024*1024):.2f} MB) exceeds the maximum allowed size of {MAX_TOTAL_FILE_SIZE} bytes ({MAX_TOTAL_FILE_SIZE / (1024*1024):.2f} MB)"
        logging.error(error_msg)
        logging.error(f"Individual file sizes: {file_sizes}")
        raise ValueError(error_msg)

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    프론트엔드로부터 최초의 분석 요청을 받는 API 진입점입니다.
    """
    client = df.DurableOrchestrationClient(starter)
    
    # 요청 정보 로깅
    logging.info(f"Received HTTP request: Method={req.method}, URL={req.url}")
    logging.info(f"Request headers: {dict(req.headers)}")
    
    # Content-Type 확인 (multipart/form-data 또는 application/json 모두 허용)
    content_type = req.headers.get('content-type', '')
    
    try:
        if content_type.startswith('multipart/form-data'):
            # Form-data 처리
            form_data = req.form
            logging.info(f"Processing multipart/form-data request")
            
            # file_names 파싱 (JSON 문자열로 전송됨)
            file_names_str = form_data.get('file_names')
            if not file_names_str:
                logging.warning("Missing file_names in form data")
                return func.HttpResponse(
                    "Missing required field: file_names", 
                    status_code=400
                )
            
            try:
                file_names = json.loads(file_names_str)
            except json.JSONDecodeError:
                logging.warning("Invalid JSON format for file_names")
                return func.HttpResponse(
                    "file_names must be a valid JSON array", 
                    status_code=400
                )
            
            # user_summary 가져오기
            user_summary = form_data.get('user_summary')
            if not user_summary:
                logging.warning("Missing user_summary in form data")
                return func.HttpResponse(
                    "Missing required field: user_summary", 
                    status_code=400
                )
            
            # user_id 가져오기 (선택적)
            user_id = form_data.get('user_id', 'anonymous_user')
            
            # files 처리 (File 객체들을 base64로 변환)
            files = []
            
            if not req.files:
                logging.warning("No files provided in form data")
                return func.HttpResponse(
                    "Missing required field: files", 
                    status_code=400
                )
            
            # req.files에서 'files' 키로 파일들을 가져오기
            file_objects = req.files.getlist('files')
            logging.info(f"file_objects type: {type(file_objects)}")
            
            if not file_objects:
                logging.warning("No files found with key 'files'")
                return func.HttpResponse(
                    "Missing required field: files", 
                    status_code=400
                )
            
            # 파일 크기 검증 (10MB 제한)
            try:
                validate_file_sizes(file_objects)
            except ValueError as e:
                logging.error(f"File size validation failed: {str(e)}")
                return func.HttpResponse(
                    str(e), 
                    status_code=413  # Payload Too Large
                )
            
            for file_obj in file_objects:
                if file_obj.filename:  # 파일이 실제로 업로드된 경우
                    file_content = file_obj.read()
                    file_base64 = base64.b64encode(file_content).decode('utf-8')
                    files.append(file_base64)
                    logging.info(f"Processed file: {file_obj.filename}, size: {len(file_content)} bytes")
            
            request_data = {
                'file_names': file_names,
                'files': files,
                'user_summary': user_summary,
                'user_id': user_id
            }
            
        elif content_type.startswith('application/json'):
            # 기존 JSON 처리 로직 유지
            request_data = req.get_json()
            if not request_data:
                logging.warning("Empty request body")
                return func.HttpResponse(
                    "Request body cannot be empty", 
                    status_code=400
                )
            
            # user_id가 없으면 기본값 설정
            if 'user_id' not in request_data:
                request_data['user_id'] = 'anonymous_user'
        else:
            logging.warning(f"Unsupported content-type: {content_type}")
            return func.HttpResponse(
                "Content-Type must be application/json or multipart/form-data", 
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
        
        logging.info(f"Request data validated successfully. Files count: {len(request_data.get('files', []))}, User ID: {request_data.get('user_id', 'not provided')}")
        
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
