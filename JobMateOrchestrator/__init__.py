import logging
import json
import azure.functions as func
import azure.durable_functions as df
from shared_code.models import AnalysisResult, Feedback, NextAction

def orchestrator_function(context: df.DurableOrchestrationContext):
    """
    전체 작업 흐름을 지휘하는 오케스트레이터 에이전트입니다.
    """
    logging.info("Orchestration started.")
    analysis_request = context.get_input()

    # --- 1단계: 콘텐츠 인식 에이전트 호출 (향후 확장) ---
    # 향후 PDF/음성 파일 처리 로직을 이 에이전트에 구현할 수 있습니다.
    # processed_content = yield context.call_activity("ContentAwareAgent", analysis_request)
    
    # --- 2단계: 핵심 분석 에이전트 병렬 실행 ---
    logging.info("Starting parallel agent execution.")
    # evaluation_task = context.call_activity("ComprehensionEvaluationAgent", analysis_request) #5,6
    question_generation_task = context.call_activity("QuestionGenerationAgent", analysis_request) #7
    action_item_task = context.call_activity("ActionItemSuggestionAgent", analysis_request) #8(개선+actionItem)

    # 모든 병렬 작업이 완료될 때까지 대기
    # results = yield context.task_all([evaluation_task, question_generation_task, action_item_task])
    results = yield context.task_all([question_generation_task, action_item_task])
    logging.info("Parallel agent execution completed.")

    # --- 3단계: 결과 취합 ---
    # evaluation_result = results[0]
    question_result = results[0]
    action_item_result = results[1]

    analysis_result = AnalysisResult(
        score=0,
        feedback="Some text",
        suggested_questions=question_result,
        next_actions=[NextAction(**action) for action in action_item_result]
    )

    logging.info("Orchestration completed successfully.")
    
    # Durable Function은 결과를 JSON 직렬화 가능한 객체로 반환해야 합니다.
    return analysis_result.to_dict()

main = df.Orchestrator.create(orchestrator_function)
