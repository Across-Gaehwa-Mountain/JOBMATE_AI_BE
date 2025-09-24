import logging
import json
import os
import base64
import io
from typing import Dict, Any, Optional
import azure.functions as func
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from shared_code.models import FileAnalysisResult
from SpeechToTextAgent import is_audio_or_video, stt_for_files

def _get_file_type_from_name(file_name: str) -> str:
    """파일명에서 MIME 타입을 추정합니다."""
    file_extension = file_name.lower().split('.')[-1] if '.' in file_name else ''
    
    mime_types = {
        'pdf': 'application/pdf',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls': 'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'ppt': 'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'bmp': 'image/bmp',
        'tiff': 'image/tiff',
        'tif': 'image/tiff'
    }
    
    return mime_types.get(file_extension, 'application/octet-stream')

def main(req) -> Dict[str, Any]:
    """Azure AI Document Intelligence를 사용하여 여러 파일을 분석하는 ContentAwareAgent입니다.
    Args:
        req: 분석 요청 데이터 (file_names: string[], files: File[])
    Returns:
        Dict[str, Any]: 분석된 파일 정보들
    """
    logging.info("[ContentAwareAgent] Start processing request: %s", str(req)[:500])
    
    try:
        # Azure Document Intelligence 설정
        endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        model_id = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-layout")
        
        if not endpoint or not key:
            raise ValueError("Azure Document Intelligence endpoint and key must be configured")
        
        logging.info(f"[ContentAwareAgent] Using Document Intelligence model: {model_id}")
        
        # Document Intelligence 클라이언트 초기화
        client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )
        
        # 요청 데이터에서 파일 정보 추출
        file_names = req.get("file_names", [])
        files = req.get("files", [])
        logging.info(f"[ContentAwareAgent] file_names: {file_names}")
        logging.info(f"[ContentAwareAgent] files count: {len(files)}")
        if not files or len(files) == 0:
            logging.warning("[ContentAwareAgent] No files provided for analysis")
            return {
                "file_analysis": [],
                "extracted_content": "",
                "total_files_processed": 0
            }

        # 파일 타입 분기: 오디오/비디오(stt), 문서(document intelligence)
        file_analyses = []
        all_extracted_text = []
        stt_indices = []
        doc_indices = []
        # 파일명 확장자 기반으로 오디오/비디오와 문서 파일 인덱스 분리
        for i, file_name in enumerate(file_names):
            if is_audio_or_video(file_name):
                stt_indices.append(i)
            else:
                doc_indices.append(i)
        logging.info(f"[ContentAwareAgent] stt_indices: {stt_indices}, doc_indices: {doc_indices}")

        # 1. 오디오/비디오 파일 STT 처리
        # (mp3, mp4 등은 Azure Speech로 STT 변환)
        if stt_indices:
            stt_file_names = [file_names[i] for i in stt_indices]
            stt_files = [files[i] for i in stt_indices]
            logging.info(f"[ContentAwareAgent] STT 대상 파일: {stt_file_names}")
            stt_texts = stt_for_files(stt_file_names, stt_files, os.environ.get('AZURE_SPEECH_KEY', ''), os.environ.get('AZURE_SPEECH_REGION', ''))
            # STT 결과를 file_analysis에 추가 (문서 구조 없음)
            for idx, fname in enumerate(stt_file_names):
                logging.info(f"[ContentAwareAgent] STT 처리 결과: {fname} => {stt_texts[idx][:100]}")
                file_analysis = FileAnalysisResult(
                    file_name=fname,
                    file_type="audio_or_video",
                    extracted_text=stt_texts[idx],
                    document_structure={},
                    confidence_score=0.0,
                    processing_status="stt_completed"
                )
                file_analyses.append(file_analysis.to_dict())
                all_extracted_text.append(stt_texts[idx])

        # 2. 문서 파일(Document Intelligence) 처리
        # (pdf, docx, txt 등은 Azure Document Intelligence로 분석)
        for i in doc_indices:
            try:
                file_name = file_names[i] if i < len(file_names) else f"file_{i+1}"
                logging.info(f"[ContentAwareAgent] 문서 파일 분석 시작: {file_name}")
                # 파일 타입 추정 (파일명 확장자 기반)
                file_type = _get_file_type_from_name(file_name)
                file_data = files[i]
                # Base64 인코딩된 파일 데이터 디코딩
                if isinstance(file_data, str):
                    file_bytes = base64.b64decode(file_data)
                else:
                    file_bytes = file_data
                # 파일 스트림 생성
                file_stream = io.BytesIO(file_bytes)
                # Document Intelligence로 문서 분석
                # 분석 요청 생성
                analyze_request = AnalyzeDocumentRequest(
                    bytes_source=file_stream.getvalue()
                )
                # 문서 분석 실행
                poller = client.begin_analyze_document(
                    model_id=model_id,
                    body=analyze_request,
                    output_content_format=DocumentContentFormat.MARKDOWN
                )
                result = poller.result()
                # 분석 결과 추출
                extracted_text = ""
                document_structure = {}
                confidence_score = 0.0
                if result.content:
                    extracted_text = result.content
                    all_extracted_text.append(extracted_text)
                # 문서 구조 정보 추출
                if result.paragraphs:
                    document_structure["paragraphs"] = [
                        {
                            "content": p.content,
                            "confidence": p.confidence if hasattr(p, 'confidence') else 0.0
                        }
                        for p in result.paragraphs
                    ]
                if result.tables:
                    document_structure["tables"] = [
                        {
                            "row_count": t.row_count,
                            "column_count": t.column_count,
                            "cells": [
                                {
                                    "content": c.content,
                                    "confidence": c.confidence if hasattr(c, 'confidence') else 0.0
                                }
                                for c in t.cells
                            ] if t.cells else []
                        }
                        for t in result.tables
                    ]
                # 전체 신뢰도 점수 계산 (평균)
                all_confidences = []
                if result.paragraphs:
                    all_confidences.extend([p.confidence for p in result.paragraphs if hasattr(p, 'confidence')])
                if result.tables and result.tables[0].cells:
                    all_confidences.extend([c.confidence for c in result.tables[0].cells if hasattr(c, 'confidence')])
                if all_confidences:
                    confidence_score = sum(all_confidences) / len(all_confidences)
                # 파일 분석 결과 생성
                file_analysis = FileAnalysisResult(
                    file_name=file_name,
                    file_type=file_type,
                    extracted_text=extracted_text,
                    document_structure=document_structure,
                    confidence_score=confidence_score,
                    processing_status="completed"
                )
                file_analyses.append(file_analysis.to_dict())
                logging.info(f"[ContentAwareAgent] 문서 파일 분석 완료: {file_name}, 추출 텍스트 길이: {len(extracted_text)}")
            except Exception as file_error:
                logging.error(f"[ContentAwareAgent] 문서 파일 처리 중 오류: {file_name}, 에러: {str(file_error)}")
                # 에러 발생한 파일도 결과에 포함
                error_analysis = FileAnalysisResult(
                    file_name=file_names[i] if i < len(file_names) else f"file_{i+1}",
                    file_type="unknown",
                    extracted_text="",
                    document_structure={},
                    confidence_score=0.0,
                    processing_status=f"error: {str(file_error)}"
                )
                file_analyses.append(error_analysis.to_dict())

        # 모든 추출된 텍스트 결합
        combined_extracted_text = "\n\n".join(all_extracted_text)
        logging.info(f"[ContentAwareAgent] Completed analysis of {len(files)} files")
        logging.info(f"[ContentAwareAgent] Total extracted text length: {len(combined_extracted_text)} characters")
        # 결과 반환
        return {
            "file_analysis": file_analyses,
            "extracted_content": combined_extracted_text,
            "total_files_processed": len(files)
        }
        
    except Exception as e:
        logging.error(f"[ContentAwareAgent] 전체 처리 중 예외 발생: {str(e)}")
        # 에러 발생 시에도 기본 구조 반환
        return {
            "file_analysis": [],
            "extracted_content": "",
            "total_files_processed": 0,
            "error": str(e)
        }
