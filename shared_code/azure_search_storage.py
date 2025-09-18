import logging
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchFieldDataType,
    SearchableField,
    ComplexField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticSearch,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField
)
from azure.core.credentials import AzureKeyCredential


def format_datetime_for_search(dt: datetime) -> str:
    """
    Azure AI Search의 DateTimeOffset 형식에 맞게 datetime을 포맷합니다.
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AnalysisResultStorage:
    """
    Azure AI Search를 사용하여 분석 결과를 저장하고 조회하는 클래스
    NoSQL Database처럼 사용
    """
    
    def __init__(self):
        self.endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
        self.key = os.environ.get("AZURE_SEARCH_KEY")
        self.index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "jobmate-analysis-results")
        
        if not self.endpoint or not self.key:
            raise ValueError("Azure AI Search endpoint and key must be provided in environment variables")
        
        try:
            safe_endpoint = self.endpoint.split('//')[-1].split('/')[0]
        except Exception:
            safe_endpoint = self.endpoint
        logging.info(f"[Search] Initializing clients | endpoint={safe_endpoint} | index={self.index_name}")

        self.credential = AzureKeyCredential(self.key)
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential
        )
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=self.credential
        )
        
        self._initialize_index()
    
    def _initialize_index(self):
        """검색 인덱스를 초기화합니다."""
        try:
            # 인덱스가 존재하는지 확인
            try:
                self.index_client.get_index(self.index_name)
                logging.info(f"Search index already exists: {self.index_name}")
            except Exception:
                # 인덱스가 없으면 생성
                self._create_index()
                
        except Exception as e:
            logging.error(f"Failed to initialize search index: {str(e)}")
            raise
    
    def _create_index(self):
        """검색 인덱스를 생성합니다."""
        try:
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="userId", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="reportId", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="creation_datetime", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                
                # 분석 결과 필드들
                SimpleField(name="score", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
                SearchableField(name="good_points", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                SearchableField(name="improvement_points", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                SearchableField(name="missed_points", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                SearchableField(name="mentor_comment", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                SearchableField(name="reasoning_summary", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                SearchableField(name="suggested_questions", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
                
                # Next Actions를 JSON 문자열로 저장
                SearchableField(name="next_actions", type=SearchFieldDataType.String),
                
                # 전체 분석 결과를 JSON으로 저장 (검색용)
                SearchableField(name="analysis_result_json", type=SearchFieldDataType.String)
            ]
            
            # 시맨틱 검색 설정
            semantic_config = SemanticConfiguration(
                name="default-semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="analysis_result_json"),
                    content_fields=[
                        SemanticField(field_name="good_points"),
                        SemanticField(field_name="improvement_points"),
                        SemanticField(field_name="suggested_questions")
                    ],
                    keywords_fields=[
                        SemanticField(field_name="userId"),
                        SemanticField(field_name="reportId")
                    ]
                )
            )
            
            index = SearchIndex(
                name=self.index_name,
                fields=fields,
                semantic_search=SemanticSearch(configurations=[semantic_config])
            )
            
            self.index_client.create_index(index)
            logging.info(f"Search index created successfully: {self.index_name}")
            
        except Exception as e:
            logging.error(f"Failed to create search index: {str(e)}")
            raise
    
    def save_analysis_result(self, user_id: str, report_id: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        분석 결과를 Azure AI Search에 저장합니다.
        
        Args:
            user_id: 사용자 ID
            report_id: 리포트 ID
            analysis_result: 분석 결과 딕셔너리
            
        Returns:
            저장된 문서 정보
        """
        try:
            # 고유한 문서 ID 생성 (userId_reportId_timestamp)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            document_id = f"{user_id}_{report_id}_{timestamp}"
            
            # 저장할 문서 구조 - 빈 배열을 None으로 변환하여 Azure AI Search 호환성 확보
            def safe_list(value):
                """빈 리스트를 None으로 변환하여 Azure AI Search 호환성 확보"""
                if not value or len(value) == 0:
                    return None
                return value
            
            # suggested_questions는 인덱스 스키마에서 Collection(String)으로 정의됨
            # 에이전트에서 dict 리스트로 올 수 있으므로 질문 텍스트만 추출해 문자열 리스트로 정규화
            raw_sq = analysis_result.get("suggested_questions", [])
            normalized_suggested_questions: List[str] = []
            if isinstance(raw_sq, list):
                for item in raw_sq:
                    if isinstance(item, dict):
                        q = item.get("question")
                        if isinstance(q, str) and q:
                            normalized_suggested_questions.append(q)
                    elif isinstance(item, str):
                        normalized_suggested_questions.append(item)

            # 로깅: 입력 요약
            try:
                feedback = analysis_result.get("feedback", {}) or {}
                gp_len = len(feedback.get("good_points", []) or [])
                ip_len = len(feedback.get("improvement_points", []) or [])
                mp_len = len(feedback.get("missed_points", []) or [])
                na_len = len(analysis_result.get("next_actions", []) or [])
                sq_len = len(normalized_suggested_questions)
                logging.info(
                    f"[Search] Preparing document | id={document_id} | score={analysis_result.get('score')} | "
                    f"good={gp_len} improve={ip_len} missed={mp_len} next_actions={na_len} suggested_q={sq_len}"
                )
            except Exception:
                pass

            document = {
                "id": document_id,
                "userId": user_id,
                "reportId": report_id,
                "creation_datetime": format_datetime_for_search(datetime.now()),
                "score": analysis_result.get("score", 0),
                "good_points": safe_list(analysis_result.get("feedback", {}).get("good_points", [])),
                "improvement_points": safe_list(analysis_result.get("feedback", {}).get("improvement_points", [])),
                "missed_points": safe_list(analysis_result.get("feedback", {}).get("missed_points", [])),
                "mentor_comment": safe_list(analysis_result.get("feedback", {}).get("mentor_comment", [])),
                "reasoning_summary": safe_list(analysis_result.get("feedback", {}).get("reasoning_summary", [])),
                "suggested_questions": safe_list(normalized_suggested_questions),
                "next_actions": json.dumps(analysis_result.get("next_actions", [])),
                "analysis_result_json": json.dumps(analysis_result)
            }
            
            # Azure AI Search에 문서 저장
            logging.info(f"[Search] Uploading document to index '{self.index_name}'")
            result = self.search_client.upload_documents([document])
            try:
                logging.info(f"[Search] Upload result raw: {result}")
            except Exception:
                pass
            
            if result[0].succeeded:
                logging.info(f"Analysis result saved successfully: Document ID={document_id}, User ID={user_id}, Report ID={report_id}")
                
                return {
                    "success": True,
                    "document_id": document_id,
                    "timestamp": document["creation_datetime"]
                }
            else:
                error_msg = f"Failed to save document: {result[0].error_message}"
                logging.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "document_id": document_id
                }
                
        except Exception as e:
            logging.error(f"Failed to save analysis result: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id if 'document_id' in locals() else None
            }
    
    def get_analysis_results_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """
        특정 사용자의 모든 분석 결과를 조회합니다.
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            분석 결과 리스트
        """
        try:
            # 사용자별 필터링 쿼리
            search_results = self.search_client.search(
                search_text="*",
                filter=f"userId eq '{user_id}'",
                order_by=["creation_datetime desc"],
                select=["*"]
            )
            
            results = []
            for result in search_results:
                # next_actions JSON 파싱
                next_actions = []
                if result.get("next_actions"):
                    try:
                        next_actions = json.loads(result["next_actions"])
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse next_actions for document {result['id']}")
                
                # 전체 분석 결과 JSON 파싱
                analysis_result = {}
                if result.get("analysis_result_json"):
                    try:
                        analysis_result = json.loads(result["analysis_result_json"])
                        analysis_result["next_actions"] = next_actions
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse analysis_result_json for document {result['id']}")
                
                formatted_result = {
                    "id": result["id"],
                    "userId": result["userId"],
                    "reportId": result["reportId"],
                    "value": analysis_result,
                    "creation_datetime": result["creation_datetime"]
                }
                results.append(formatted_result)
            
            logging.info(f"Retrieved {len(results)} analysis results for user: {user_id}")
            return results
            
        except Exception as e:
            logging.error(f"Failed to retrieve analysis results for user {user_id}: {str(e)}")
            return []
    
    def get_analysis_result_by_report(self, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        """
        특정 리포트의 분석 결과를 조회합니다.
        
        Args:
            user_id: 사용자 ID
            report_id: 리포트 ID
            
        Returns:
            분석 결과 또는 None
        """
        try:
            # 특정 리포트 필터링 쿼리
            search_results = self.search_client.search(
                search_text="*",
                filter=f"userId eq '{user_id}' and reportId eq '{report_id}'",
                order_by=["creation_datetime desc"],
                select=["*"],
                top=1
            )
            
            results = list(search_results)
            if results:
                result = results[0]
                
                # next_actions JSON 파싱
                next_actions = []
                if result.get("next_actions"):
                    try:
                        next_actions = json.loads(result["next_actions"])
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse next_actions for document {result['id']}")
                
                # 전체 분석 결과 JSON 파싱
                analysis_result = {}
                if result.get("analysis_result_json"):
                    try:
                        analysis_result = json.loads(result["analysis_result_json"])
                        analysis_result["next_actions"] = next_actions
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse analysis_result_json for document {result['id']}")
                
                formatted_result = {
                    "id": result["id"],
                    "userId": result["userId"],
                    "reportId": result["reportId"],
                    "value": analysis_result,
                    "creation_datetime": result["creation_datetime"]
                }
                
                logging.info(f"Retrieved analysis result for user: {user_id}, report: {report_id}")
                return formatted_result
            else:
                logging.info(f"No analysis result found for user: {user_id}, report: {report_id}")
                return None
                
        except Exception as e:
            logging.error(f"Failed to retrieve analysis result for user {user_id}, report {report_id}: {str(e)}")
            return None
    
    def update_next_action_checked_status(self, user_id: str, report_id: str, next_action_idx: int, is_checked: bool) -> Dict[str, Any]:
        """
        특정 리포트의 next_action의 체크 상태를 업데이트합니다.
        
        Args:
            user_id: 사용자 ID
            report_id: 리포트 ID
            next_action_idx: 업데이트할 next_action의 인덱스
            is_checked: 체크 상태 (True/False)
            
        Returns:
            업데이트 결과
        """
        try:
            # 해당 리포트의 분석 결과 조회
            analysis_result = self.get_analysis_result_by_report(user_id, report_id)
            
            if not analysis_result:
                return {
                    "success": False,
                    "error": "Analysis result not found",
                    "message": f"No analysis result found for user: {user_id}, report: {report_id}"
                }
            
            # next_actions 확인
            value = analysis_result.get("value", {})
            next_actions = value.get("next_actions", [])
            
            if not next_actions:
                return {
                    "success": False,
                    "error": "No next_actions found",
                    "message": "No next_actions found in the analysis result"
                }
            
            # 인덱스 유효성 검사
            if next_action_idx < 0 or next_action_idx >= len(next_actions):
                return {
                    "success": False,
                    "error": "Invalid index",
                    "message": f"next_action_idx {next_action_idx} is out of range. Available range: 0-{len(next_actions)-1}"
                }
            
            # 체크 상태 업데이트
            next_actions[next_action_idx]["isChecked"] = is_checked
            
            # 문서 업데이트
            analysis_result["value"]["next_actions"] = next_actions
            
            # 업데이트할 문서 준비 - 빈 배열을 None으로 변환하여 Azure AI Search 호환성 확보
            def safe_list(value):
                """빈 리스트를 None으로 변환하여 Azure AI Search 호환성 확보"""
                if not value or len(value) == 0:
                    return None
                return value
            
            document_id = analysis_result["id"]
            updated_document = {
                "id": document_id,
                "userId": user_id,
                "reportId": report_id,
                "creation_datetime": analysis_result["creation_datetime"],
                "score": analysis_result["value"].get("score", 0),
                "good_points": safe_list(analysis_result["value"].get("feedback", {}).get("good_points", [])),
                "improvement_points": safe_list(analysis_result["value"].get("feedback", {}).get("improvement_points", [])),
                "missed_points": safe_list(analysis_result["value"].get("feedback", {}).get("missed_points", [])),
                "mentor_comment": safe_list(analysis_result["value"].get("feedback", {}).get("mentor_comment", [])),
                "reasoning_summary": safe_list(analysis_result["value"].get("feedback", {}).get("reasoning_summary", [])),
                "suggested_questions": safe_list(analysis_result["value"].get("suggested_questions", [])),
                "next_actions": json.dumps(next_actions),
                "analysis_result_json": json.dumps(analysis_result["value"])
            }
            
            # Azure AI Search에 업데이트된 문서 저장
            result = self.search_client.upload_documents([updated_document])
            
            if result[0].succeeded:
                logging.info(f"Next action checked status updated successfully: User={user_id}, Report={report_id}, Index={next_action_idx}, Checked={is_checked}")
                
                return {
                    "success": True,
                    "message": "Next action checked status updated successfully",
                    "updated_action": next_actions[next_action_idx]
                }
            else:
                error_msg = f"Failed to update document: {result[0].error_message}"
                logging.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "message": "Failed to update next action checked status"
                }
            
        except Exception as e:
            logging.error(f"Failed to update next action checked status: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update next action checked status"
            }
