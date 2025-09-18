import logging
import azure.functions as func
import azure.durable_functions as df
import json

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    프론트엔드로부터 최초의 분석 요청을 받는 API 진입점입니다.
    """
    client = df.DurableOrchestrationClient(starter)
    
    try:
        request_data = req.get_json()
    except ValueError:
        return func.HttpResponse("Please provide analysis request data in the request body.", status_code=400)

    logging.info("Starting orchestration via HTTP request.")
    
    # 오케스트레이션 시작
    instance_id = await client.start_new("JobMateOrchestrator", client_input=request_data)

    logging.info(f"Started orchestration with ID = '{instance_id}'.")

    # 오케스트레이션 상태를 확인할 수 있는 URL과 함께 응답을 반환합니다.
    return client.create_check_status_response(req, instance_id)
