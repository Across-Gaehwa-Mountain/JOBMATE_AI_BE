import logging
import azure.functions as func
import json
from shared_code.mongodb_storage import AnalysisResultStorage


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    특정 사용자의 모든 분석 결과를 조회하는 API입니다.
    URL: /api/reports
    Method: GET
    Required Parameters: user_id (query parameter)
    """
    logging.info(f"Reports API called: Method={req.method}, URL={req.url}")
    
    try:
        # user_id 파라미터 검증
        user_id = req.params.get('user_id')
        if not user_id:
            logging.warning("Missing required parameter: user_id")
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required parameter: user_id",
                    "message": "user_id is required as a query parameter"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f"Retrieving reports for user_id: {user_id}")
        
        # MongoDB에서 사용자의 모든 분석 결과 조회
        storage = AnalysisResultStorage()
        results = storage.get_analysis_results_by_user(user_id)
        
        # 결과 포맷팅
        formatted_results = []
        for result in results:
            formatted_result = {
                "document_id": result.get("id"),
                "user_id": result.get("userId"),
                "report_id": result.get("reportId"),
                "analysis_result": result.get("value"),
                "creation_datetime": result.get("creation_datetime")
            }
            formatted_results.append(formatted_result)
        
        logging.info(f"Successfully retrieved {len(formatted_results)} reports for user: {user_id}")
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "user_id": user_id,
                "total_count": len(formatted_results),
                "reports": formatted_results
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error retrieving reports for user {user_id}: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "error": "Internal server error",
                "message": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
