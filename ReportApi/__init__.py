import logging
import azure.functions as func
import json
from shared_code.azure_search_storage import AnalysisResultStorage
from shared_code.json_utils import create_korean_json_response, create_korean_error_response


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    특정 리포트의 분석 결과를 조회하는 API입니다.
    URL: /api/report/{report_id}
    Method: GET
    Required Parameters: 
        - report_id (path parameter)
        - user_id (query parameter)
    """
    logging.info(f"Report API called: Method={req.method}, URL={req.url}")
    
    try:
        # report_id 파라미터 검증 (path parameter)
        report_id = req.route_params.get('report_id')
        if not report_id:
            logging.warning("Missing required path parameter: report_id")
            return create_korean_error_response(
                "report_id is required in the URL path",
                status_code=400,
                additional_data={"error": "Missing required path parameter: report_id"}
            )
        
        # user_id 파라미터 검증 (query parameter)
        user_id = req.params.get('user_id')
        if not user_id:
            logging.warning("Missing required parameter: user_id")
            return create_korean_error_response(
                "user_id is required as a query parameter",
                status_code=400,
                additional_data={"error": "Missing required parameter: user_id"}
            )
        
        logging.info(f"Retrieving report for user_id: {user_id}, report_id: {report_id}")
        
        # Cosmos DB에서 특정 리포트의 분석 결과 조회
        storage = AnalysisResultStorage()
        result = storage.get_analysis_result_by_report(user_id, report_id)
        
        if result is None:
            logging.info(f"No report found for user_id: {user_id}, report_id: {report_id}")
            return create_korean_error_response(
                f"No report found for user_id: {user_id} and report_id: {report_id}",
                status_code=404,
                additional_data={"error": "Report not found"}
            )
        
        # 결과 포맷팅
        formatted_result = {
            "document_id": result.get("id"),
            "user_id": result.get("userId"),
            "report_id": result.get("reportId"),
            "analysis_result": result.get("value"),
            "creation_datetime": result.get("creation_datetime")
        }
        
        logging.info(f"Successfully retrieved report for user: {user_id}, report: {report_id}")
        
        return create_korean_json_response({
            "success": True,
            "report": formatted_result
        }, status_code=200)
        
    except Exception as e:
        logging.error(f"Error retrieving report for user {user_id}, report {report_id}: {str(e)}")
        return create_korean_error_response(
            str(e),
            status_code=500
        )
