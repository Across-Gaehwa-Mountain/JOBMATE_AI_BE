import json
import azure.functions as func
from typing import Any, Dict, Union


def create_korean_json_response(
    data: Union[Dict[str, Any], list, str], 
    status_code: int = 200
) -> func.HttpResponse:
    """
    한글이 포함된 데이터를 올바르게 인코딩하여 JSON 응답을 생성합니다.
    
    Args:
        data: 응답할 데이터 (딕셔너리, 리스트, 또는 문자열)
        status_code: HTTP 상태 코드 (기본값: 200)
        
    Returns:
        func.HttpResponse: 한글이 올바르게 인코딩된 JSON 응답
    """
    return func.HttpResponse(
        json.dumps(data, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json; charset=utf-8"
    )


def create_korean_error_response(
    error_message: str,
    status_code: int = 500,
    additional_data: Dict[str, Any] = None
) -> func.HttpResponse:
    """
    한글이 포함된 에러 메시지를 올바르게 인코딩하여 JSON 에러 응답을 생성합니다.
    
    Args:
        error_message: 에러 메시지
        status_code: HTTP 상태 코드 (기본값: 500)
        additional_data: 추가 데이터 (선택사항)
        
    Returns:
        func.HttpResponse: 한글이 올바르게 인코딩된 JSON 에러 응답
    """
    error_data = {
        "success": False,
        "error": "Internal server error",
        "message": error_message
    }
    
    if additional_data:
        error_data.update(additional_data)
    
    return create_korean_json_response(error_data, status_code)


def create_korean_success_response(
    data: Dict[str, Any],
    status_code: int = 200
) -> func.HttpResponse:
    """
    한글이 포함된 성공 응답 데이터를 올바르게 인코딩하여 JSON 응답을 생성합니다.
    
    Args:
        data: 응답할 데이터
        status_code: HTTP 상태 코드 (기본값: 200)
        
    Returns:
        func.HttpResponse: 한글이 올바르게 인코딩된 JSON 성공 응답
    """
    success_data = {
        "success": True,
        **data
    }
    
    return create_korean_json_response(success_data, status_code)


def safe_json_dumps(data: Any) -> str:
    """
    한글이 포함된 데이터를 안전하게 JSON 문자열로 변환합니다.
    
    Args:
        data: 변환할 데이터
        
    Returns:
        str: 한글이 올바르게 인코딩된 JSON 문자열
    """
    return json.dumps(data, ensure_ascii=False)
