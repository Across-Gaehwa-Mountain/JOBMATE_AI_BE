import logging
import json
import uuid
import azure.functions as func
import azure.durable_functions as df
from shared_code.models import AnalysisResult, Feedback, NextAction, FileAnalysisResult
from shared_code.mongodb_storage import AnalysisResultStorage

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
    
    # --- 2단계: CEA 순차 실행 ---
    logging.info("Starting ComprehensionEvaluationAgent execution.")
    analysis_data = {
        "user_summary": user_summary,
        "file_analysis": processed_content.get("file_analysis", []),
        "document_content": processed_content.get("extracted_content", ""),
    }
    
    try:
        evaluation_result = yield context.call_activity("ComprehensionEvaluationAgent", analysis_data)
    except Exception as e:
        logging.error(f"ComprehensionEvaluationAgent failed: {str(e)}")
        # Fallback: 기본 평가 결과 생성
        evaluation_result = {
            "title": "분석 오류",
            "score": 0,
            "good_points": [],
            "improvement_points": ["CEA 실행 중 오류 발생"],
            "missed_points": ["오류로 인해 분석 불가"],
            "mentor_comment": "시스템 오류, 재시도 필요",
            "reasoning_summary": ["CEA 호출 실패"]
        }

    # --- 3단계: 후속 에이전트 병렬 실행 (CEA 결과 포함) ---
    logging.info("Starting parallel execution of QuestionGenerationAgent and ActionItemSuggestionAgent.")
    
    # CEA 결과를 analysis_data에 추가
    extended_analysis_data = analysis_data.copy()
    extended_analysis_data["evaluation"] = evaluation_result
    
    question_generation_task = context.call_activity("QuestionGenerationAgent", extended_analysis_data)
    action_item_task = context.call_activity("ActionItemSuggestionAgent", extended_analysis_data)

    # 병렬 작업 대기
    parallel_results = yield context.task_all([question_generation_task, action_item_task])
    logging.info("Parallel agent execution completed.")

    # --- 4단계: 결과 취합 ---
    question_result = parallel_results[0]
    action_item_result = parallel_results[1]

    # 파일 분석 결과 추출
    file_analysis_results = processed_content.get("file_analysis", [])

    analysis_result = AnalysisResult(
        title=evaluation_result['title'],
        score=evaluation_result['score'],
        feedback=Feedback(**evaluation_result),
        suggested_questions=question_result,
        next_actions=action_item_result,
        file_analysis=file_analysis_results
    )

    # next_actions의 각 item에 key와 isChecked 필드 추가
    analysis_result_dict = analysis_result.to_dict()
    if 'next_actions' in analysis_result_dict:
        for index, action in enumerate(analysis_result_dict['next_actions']):
            action['key'] = index
            action['isChecked'] = False

    # --- 5단계: 분석 결과를 Cosmos DB에 저장 ---
    try:
        user_id = analysis_request.get("user_id", "anonymous_user")
        report_id = str(uuid.uuid4())
        logging.info(f"[Orch] Saving analysis result for user_id: '{user_id}', report_id: '{report_id}'")
        
        storage = AnalysisResultStorage()
        save_result = storage.save_analysis_result(
            user_id=user_id,
            report_id=report_id,
            analysis_result=analysis_result_dict
        )
        
        if save_result.get("success"):
            logging.info(f"Analysis result saved successfully to MongoDB: {save_result.get('document_id')}")
        else:
            logging.warning(f"Failed to save analysis result to MongoDB: {save_result.get('error')}")
            
    except Exception as e:
        logging.error(f"Error saving analysis result to MongoDB: {str(e)}")
        logging.info("Continuing with analysis result return despite storage error")

    logging.info("Orchestration completed successfully.")
    
    # Durable Functions 출력 준비
    analysis_result_dict["report_id"] = report_id
    analysis_result_dict.pop("file_analysis")
    
    return analysis_result_dict

main = df.Orchestrator.create(orchestrator_function)