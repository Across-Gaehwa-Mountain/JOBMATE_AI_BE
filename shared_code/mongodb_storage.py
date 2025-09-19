import logging
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pymongo import MongoClient
from bson import ObjectId


def format_datetime_for_mongodb(dt: datetime) -> datetime:
    """
    MongoDB의 datetime 형식에 맞게 datetime을 반환합니다.
    """
    return dt


class AnalysisResultStorage:
    """
    MongoDB를 사용하여 분석 결과를 저장하고 조회하는 클래스
    """
    
    def __init__(self):
        self.connection_string = os.environ.get("MONGODB_CONNECTION_STRING", "mongodb://localhost:27017")
        self.database_name = os.environ.get("MONGODB_DATABASE_NAME", "jobmate")
        self.collection_name = os.environ.get("MONGODB_COLLECTION_NAME", "analysis_results")
        
        if not self.connection_string:
            raise ValueError("MongoDB connection string must be provided in environment variables")
        
        self.client = MongoClient(self.connection_string)
        self.db = self.client[self.database_name]
        self.collection = self.db[self.collection_name]
        
        self._initialize_collection()
    
    def _initialize_collection(self):
        """MongoDB 컬렉션을 초기화합니다."""
        try:
            # 컬렉션이 존재하지 않으면 생성
            if self.collection_name not in self.db.list_collection_names():
                self.db.create_collection(self.collection_name)
                logging.info(f"MongoDB collection created: {self.collection_name}")
            else:
                logging.info(f"MongoDB collection already exists: {self.collection_name}")
            
            # 인덱스 생성 (성능 최적화)
            self.collection.create_index([("userId", 1), ("reportId", 1)], unique=True)
            self.collection.create_index([("userId", 1), ("creation_datetime", -1)])
            logging.info("MongoDB indexes created successfully")
                
        except Exception as e:
            logging.error(f"Failed to initialize MongoDB collection: {str(e)}")
            raise
    
    def save_analysis_result(self, user_id: str, report_id: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        분석 결과를 MongoDB에 저장합니다.
        
        Args:
            user_id: 사용자 ID
            report_id: 리포트 ID
            analysis_result: 분석 결과 딕셔너리
            
        Returns:
            저장된 문서 정보
        """
        try:
            # MongoDB 문서 구조
            document = {
                "userId": user_id,
                "reportId": report_id,
                "creation_datetime": format_datetime_for_mongodb(datetime.now()),
                "analysis_result": analysis_result
            }
            
            # MongoDB에 문서 저장 (upsert 사용)
            result = self.collection.replace_one(
                {"userId": user_id, "reportId": report_id},
                document,
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                document_id = str(result.upserted_id) if result.upserted_id else f"{user_id}_{report_id}"
                logging.info(f"Analysis result saved successfully: Document ID={document_id}, User ID={user_id}, Report ID={report_id}")
                
                return {
                    "success": True,
                    "document_id": document_id,
                    "timestamp": document["creation_datetime"].isoformat()
                }
            else:
                error_msg = "Failed to save document to MongoDB"
                logging.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "document_id": None
                }
                
        except Exception as e:
            logging.error(f"Failed to save analysis result: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "document_id": None
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
            # MongoDB에서 사용자별 조회
            cursor = self.collection.find(
                {"userId": user_id}
            ).sort("creation_datetime", -1)
            
            results = []
            for document in cursor:
                # ObjectId를 문자열로 변환
                document_id = str(document["_id"])
                
                formatted_result = {
                    "id": document_id,
                    "userId": document["userId"],
                    "reportId": document["reportId"],
                    "value": document["analysis_result"],
                    "creation_datetime": document["creation_datetime"].isoformat()
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
            # MongoDB에서 특정 리포트 조회
            document = self.collection.find_one({
                "userId": user_id,
                "reportId": report_id
            })
            
            if document:
                # ObjectId를 문자열로 변환
                document_id = str(document["_id"])
                
                formatted_result = {
                    "id": document_id,
                    "userId": document["userId"],
                    "reportId": document["reportId"],
                    "value": document["analysis_result"],
                    "creation_datetime": document["creation_datetime"].isoformat()
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
            result = self.collection.update_one(
            {"userId": user_id, "reportId": report_id},
            {"$set": {f"analysis_result.next_actions.{next_action_idx}.isChecked": is_checked}})
            
            if result.modified_count > 0:
                logging.info(f"Next action checked status updated successfully: User={user_id}, Report={report_id}, Index={next_action_idx}, Checked={is_checked}")
                
                return {
                    "success": True,
                    "message": "Next action checked status updated successfully",
                    "updated_action": next_actions[next_action_idx]
                }
            else:
                error_msg = "Failed to update document in MongoDB"
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
