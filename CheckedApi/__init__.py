import logging
import json
import azure.functions as func
from shared_code.azure_search_storage import AnalysisResultStorage

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
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Missing required parameter",
                    "message": "user_id is required"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        if not report_id:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Missing required parameter", 
                    "message": "report_id is required"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        if not next_action_idx:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Missing required parameter",
                    "message": "next_action_idx is required"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # next_action_idx를 정수로 변환
        try:
            next_action_idx = int(next_action_idx)
        except ValueError:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Invalid parameter type",
                    "message": "next_action_idx must be an integer"
                }),
                status_code=400,
                mimetype="application/json"
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
                return func.HttpResponse(
                    json.dumps({
                        "success": False,
                        "error": "Invalid parameter value",
                        "message": "is_checked must be a boolean value (true/false)"
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
        
        # Cosmos DB 저장소 초기화 및 체크 상태 업데이트
        storage = AnalysisResultStorage()
        update_result = storage.update_next_action_checked_status(
            user_id=user_id,
            report_id=report_id,
            next_action_idx=next_action_idx,
            is_checked=is_checked
        )
        
        if update_result.get("success"):
            return func.HttpResponse(
                json.dumps(update_result),
                status_code=200,
                mimetype="application/json"
            )
        else:
            # 에러 메시지에 따라 적절한 HTTP 상태 코드 설정
            error = update_result.get("error", "")
            if "not found" in error.lower():
                status_code = 404
            elif "invalid" in error.lower() or "out of range" in error.lower():
                status_code = 400
            else:
                status_code = 500
            
            return func.HttpResponse(
                json.dumps(update_result),
                status_code=status_code,
                mimetype="application/json"
            )
            
    except Exception as e:
        logging.error(f"Unexpected error in CheckedApi: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": "Internal server error",
                "message": f"An unexpected error occurred: {str(e)}"
            }),
            status_code=500,
            mimetype="application/json"
        )
