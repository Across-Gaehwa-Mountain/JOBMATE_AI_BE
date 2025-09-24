import logging
import json
import uuid
import azure.functions as func
import azure.durable_functions as df
from shared_code.models import AnalysisResult, Feedback, NextAction, FileAnalysisResult
from shared_code.mongodb_storage import AnalysisResultStorage
from SpeechToTextAgent import stt_for_files
import os

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

    # Azure Speech 서비스 설정 (환경변수 또는 설정에서 가져오세요)
    AZURE_SPEECH_KEY = os.environ.get('AZURE_SPEECH_KEY', 'YOUR_SPEECH_KEY')
    AZURE_SPEECH_REGION = os.environ.get('AZURE_SPEECH_REGION', 'YOUR_REGION')
    # files에 음성/영상 파일이 있으면 STT 처리
    stt_texts = stt_for_files(file_names, files, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION)

    # --- 1단계: 콘텐츠 인식 에이전트 호출 (파일 정보만 전달) ---
    file_analysis_request = {
        "file_names": file_names,                                                  
        "files": files
    }
    processed_content = yield context.call_activity("ContentAwareAgent", file_analysis_request)
    # STT 결과를 processed_content에 추가
    if stt_texts:
        processed_content["stt_texts"] = stt_texts
    
    # --- 2단계: 핵심 분석 에이전트 병렬 실행 (처리된 콘텐츠 + 사용자 요약 사용) ---
    logging.info("Starting parallel agent execution.")
    
    # 분석 에이전트에 전달할 데이터 구성 (파일 분석 결과 + 사용자 요약)
    analysis_data = {
        "user_summary": user_summary,
        "file_analysis": processed_content.get("file_analysis", []),
        "document_content": processed_content.get("extracted_content", ""),
        "stt_texts": processed_content.get("stt_texts", []),
    }
    
    evaluation_task = context.call_activity("ComprehensionEvaluationAgent", analysis_data) #5,6
    question_generation_task = context.call_activity("QuestionGenerationAgent", analysis_data) #7
    action_item_task = context.call_activity("ActionItemSuggestionAgent", analysis_data) #8(개선+actionItem)

    # 모든 병렬 작업이 완료될 때까지 대기
    results = yield context.task_all([evaluation_task, question_generation_task, action_item_task])
    logging.info("Parallel agent execution completed.")

    # --- 3단계: 결과 취합 ---
    evaluation_result = results[0]
    question_result = results[1]
    action_item_result = results[2]

    # 파일 분석 결과 추출 (여러 파일 분석 결과)
    file_analysis_results = processed_content.get("file_analysis", [])

    analysis_result = AnalysisResult(
        title= evaluation_result['title'],
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

    # --- 4단계: 분석 결과를 Cosmos DB에 저장 ---
    try:
        # 사용자 ID와 리포트 ID 추출 (요청에서 가져오거나 생성)
        user_id = analysis_request.get("user_id", "anonymous_user")
        report_id = str(uuid.uuid4())
        logging.info(f"[Orch] Saving analysis result for user_id: '{user_id}', report_id: '{report_id}'")
        
        # MongoDB 저장소 초기화 및 저장
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
        # DB 저장 실패가 전체 프로세스를 중단시키지 않도록 예외 처리
        logging.error(f"Error saving analysis result to MongoDB: {str(e)}")
        logging.info("Continuing with analysis result return despite storage error")

    logging.info("Orchestration completed successfully.")
    
    # Durable Function은 결과를 JSON 직렬화 가능한 객체로 반환해야 합니다.
    # return 시에도 key와 isChecked 필드가 포함된 결과를 반환
    # output에 report_id 포함
    analysis_result_dict["report_id"] = report_id
    analysis_result_dict.pop("file_analysis")
    
    # Durable Functions 프레임워크가 자동으로 메타데이터를 추가
    return analysis_result_dict

main = df.Orchestrator.create(orchestrator_function)