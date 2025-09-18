import logging
import json
import azure.functions as func
import azure.durable_functions as df
from shared_code.models import AnalysisResult, Feedback, NextAction, FileAnalysisResult

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
    
    # 분석 에이전트에 전달할 데이터 구성 (파일 분석 결과 + 사용자 요약)
    analysis_data = {
        "user_summary": user_summary,
        # "file_analysis": processed_content.get("file_analysis", []),
        "document_content": processed_content.get("extracted_content", ""),
    }
    
    evaluation_task = context.call_activity("ComprehensionEvaluationAgent", analysis_request) #5,6
    question_generation_task = context.call_activity("QuestionGenerationAgent", analysis_request) #7
    action_item_task = context.call_activity("ActionItemSuggestionAgent", analysis_request) #8(개선+actionItem)

    # 모든 병렬 작업이 완료될 때까지 대기
    # results = yield context.task_all([evaluation_task, question_generation_task, action_item_task])
    results = yield context.task_all([question_generation_task, action_item_task])
    logging.info("Parallel agent execution completed.")

    # --- 3단계: 결과 취합 ---
    evaluation_result = results[0]
    question_result = results[1]
    action_item_result = results[2]

    # 파일 분석 결과 추출 (여러 파일 분석 결과)
    file_analysis_results = processed_content.get("file_analysis", [])

    analysis_result = AnalysisResult(
        score=evaluation_result['score'],
        feedback=Feedback(**evaluation_result),
        suggested_questions=question_result,
        next_actions=[NextAction(**action) for action in action_item_result],
        file_analysis=file_analysis_results
    )

    logging.info("Orchestration completed successfully.")
    
    # Durable Function은 결과를 JSON 직렬화 가능한 객체로 반환해야 합니다.
    return analysis_result.to_dict()

main = df.Orchestrator.create(orchestrator_function)
