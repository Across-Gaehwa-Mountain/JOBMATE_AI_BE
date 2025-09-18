import logging
import json
from typing import Dict, Any
from shared_code.azure_search_storage import AnalysisResultStorage

def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity: 분석 결과를 Azure AI Search에 저장한다.
    입력 payload: { user_id: str, report_id: str, analysis_result: dict }
    반환: { success: bool, document_id?: str, error?: str }
    """
    try:
        user_id = payload.get("user_id", "anonymous_user")
        report_id = payload.get("report_id")
        analysis_result = payload.get("analysis_result", {})

        if not report_id:
            return {"success": False, "error": "report_id is required"}

        logging.info(f"[Save] Start | user={user_id} | report={report_id}")
        storage = AnalysisResultStorage()
        result = storage.save_analysis_result(user_id=user_id, report_id=report_id, analysis_result=analysis_result)
        try:
            logging.info(f"[Save] Done | result={json.dumps(result)}")
        except Exception:
            logging.info(f"[Save] Done | result(raw)={result}")
        return result
    except Exception as e:
        logging.error(f"[Save] Exception: {str(e)}")
        return {"success": False, "error": str(e)}
