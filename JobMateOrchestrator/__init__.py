import logging
import json
import uuid
import azure.functions as func
import azure.durable_functions as df
from shared_code.models import AnalysisResult, Feedback, NextAction, FileAnalysisResult
# 이제 오케스트레이터는 Storage 클래스를 직접 알 필요가 없습니다.
# from shared_code.azure_search_storage import AnalysisResultStorage 

def orchestrator_function(context: df.DurableOrchestrationContext):
    """
    전체 작업 흐름을 지휘하는 오케스트레이터 에이전트입니다.
    """
    logging.info("Orchestration started.")
    analysis_request = context.get_input()
    
    # 입력 데이터 분리
    file_names = analysis_request.get("file_names", [])
    files = analysis_request.get("files", [])
    user_summary = analysis_request.get("user_summary", "")

    # --- 1단계: 콘텐츠 인식 에이전트 호출 (파일 정보만 전달) ---
    file_analysis_request = {
        "file_names": file_names,
        "files": files
    }
    processed_content = yield context.call_activity("ContentAwareAgent", file_analysis_request)
    
    # --- 2단계: 핵심 분석 에이전트 병렬 실행 (처리된 콘텐츠 + 사용자 요약 사용) ---
    logging.info("Starting parallel agent execution.")
    
    analysis_data = {
        "user_summary": user_summary,
        "file_analysis": processed_content.get("file_analysis", []),
        "document_content": processed_content.get("extracted_content", ""),
    }
    
    evaluation_task = context.call_activity("ComprehensionEvaluationAgent", analysis_data)
    question_generation_task = context.call_activity("QuestionGenerationAgent", analysis_data)
    action_item_task = context.call_activity("ActionItemSuggestionAgent", analysis_data)

    results = yield context.task_all([evaluation_task, question_generation_task, action_item_task])
    logging.info("Parallel agent execution completed.")

    # --- 3단계: 결과 취합 ---
    evaluation_result = results[0]
    question_result = results[1]
    action_item_result = results[2]
    file_analysis_results = processed_content.get("file_analysis", [])

    analysis_result = AnalysisResult(
        score=evaluation_result['score'],
        feedback=Feedback(**evaluation_result),
        suggested_questions=question_result,
        next_actions=action_item_result,
        file_analysis=file_analysis_results
    )

    analysis_result_dict = analysis_result.to_dict()
    if 'next_actions' in analysis_result_dict:
        for index, action in enumerate(analysis_result_dict['next_actions']):
            action['key'] = index
            action['isChecked'] = False

    # --- 4단계: 액티비티를 호출하여 분석 결과를 DB에 저장 ---
    user_id = analysis_request.get("user_id", "anonymous_user")
    report_id = analysis_request.get("report_id", str(uuid.uuid4()))
    
    save_payload = {
        "user_id": user_id,
        "report_id": report_id,
        "analysis_result": analysis_result_dict
    }
    
    logging.info(f"[Orch] Calling SaveResultActivity for user '{user_id}', report '{report_id}'")
    
    # 액티비티를 호출합니다. 이 작업은 실패 시 예외를 발생시킬 수 있습니다.
    # 저장 실패가 전체 오케스트레이션 실패로 이어지지 않게 하려면 try/except를 사용할 수 있습니다.
    try:
        save_status = yield context.call_activity("SaveResultActivity", save_payload)
        if save_status.get("success"):
            logging.info(f"[Orch] SaveResultActivity completed successfully. DocID: {save_status.get('document_id')}")
        else:
            logging.warning(f"[Orch] SaveResultActivity reported a failure: {save_status.get('error')}")
    except Exception as e:
        # 액티비티 함수에서 발생한 예외를 여기서 처리합니다.
        logging.error(f"[Orch] SaveResultActivity failed with an exception: {str(e)}")
        # 저장 실패가 전체 프로세스를 중단시키지 않도록 계속 진행합니다.
        
    logging.info("Orchestration completed successfully.")
    
    # 최종 결과 반환
    final_output = analysis_result_dict
    final_output["report_id"] = report_id
    final_output.pop("file_analysis", None) # file_analysis가 없을 경우를 대비해 기본값 None 추가
    
    return final_output

main = df.Orchestrator.create(orchestrator_function)
