import logging
import json
import azure.functions as func
from shared_code.mongodb_storage import AnalysisResultStorage
from shared_code.json_utils import create_korean_json_response, create_korean_error_response

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Next Action의 체크 상태를 업데이트하는 API
    
    Request Parameters:
    - user_id (required): 사용자 ID
    - report_id (required): 리포트 ID  
    - next_action_idx (required): 업데이트할 next_action의 인덱스
    - is_checked (optional): 체크 상태 (True/False), 기본값은 False
    """
    logging.info('CheckedApi function processed a request.')
    
    try:
        # 요청 파라미터 추출
        user_id = req.params.get('user_id')
        report_id = req.params.get('report_id')
        next_action_idx = req.params.get('next_action_idx')
        is_checked_param = req.params.get('is_checked')
        
        # 필수 파라미터 검증
        if not user_id:
            return create_korean_error_response(
                "user_id is required",
                status_code=400,
                additional_data={"error": "Missing required parameter"}
            )
        
        if not report_id:
            return create_korean_error_response(
                "report_id is required",
                status_code=400,
                additional_data={"error": "Missing required parameter"}
            )
        
        if not next_action_idx:
            return create_korean_error_response(
                "next_action_idx is required",
                status_code=400,
                additional_data={"error": "Missing required parameter"}
            )
        
        # next_action_idx를 정수로 변환
        try:
            next_action_idx = int(next_action_idx)
        except ValueError:
            return create_korean_error_response(
                "next_action_idx must be an integer",
                status_code=400,
                additional_data={"error": "Invalid parameter type"}
            )
        
        # is_checked 파라미터 처리 (기본값: False)
        if is_checked_param is None:
            is_checked = False
        else:
            # Boolean 타입으로 변환
            if is_checked_param.lower() == 'true':
                is_checked = True
            elif is_checked_param.lower() == 'false':
                is_checked = False
            else:
                return create_korean_error_response(
                    "is_checked must be a boolean value (true/false)",
                    status_code=400,
                    additional_data={"error": "Invalid parameter value"}
                )
        
        # MongoDB 저장소 초기화 및 체크 상태 업데이트
        storage = AnalysisResultStorage()
        update_result = storage.update_next_action_checked_status(
            user_id=user_id,
            report_id=report_id,
            next_action_idx=next_action_idx,
            is_checked=is_checked
        )
        
        if update_result.get("success"):
            return create_korean_json_response(update_result, status_code=200)
        else:
            # 에러 메시지에 따라 적절한 HTTP 상태 코드 설정
            error = update_result.get("error", "")
            if "not found" in error.lower():
                status_code = 404
            elif "invalid" in error.lower() or "out of range" in error.lower():
                status_code = 400
            else:
                status_code = 500
            
            return create_korean_json_response(update_result, status_code=status_code)
            
    except Exception as e:
        logging.error(f"Unexpected error in CheckedApi: {str(e)}")
        return create_korean_error_response(
            f"An unexpected error occurred: {str(e)}",
            status_code=500
        )
