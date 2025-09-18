import logging
import os
import base64
from typing import List, Dict, Any
import httpx

from azure.storage.blob import BlobServiceClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential


def _get_env(name: str, required: bool = True) -> str:
    value = os.environ.get(name)
    if required and not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value


def _upload_to_blob(container: str, file_name: str, data: bytes) -> str:
    connection_string = _get_env("AZURE_STORAGE_CONNECTION_STRING")
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container)
    try:
        container_client.create_container()
    except Exception:
        pass
    blob_client = container_client.get_blob_client(file_name)
    blob_client.upload_blob(data, overwrite=True)
    return blob_client.url


def _extract_text_with_di(content: bytes, content_type: str) -> Dict[str, Any]:
    endpoint = _get_env("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    key = _get_env("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    model_id = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-read")

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    # SDK 버전에 따라 시그니처가 다릅니다. (body | analyze_request | content)
    # 가장 최신(body) → 구버전(analyze_request) → 이전(content) 순으로 시도합니다.
    analyze_req = AnalyzeDocumentRequest(bytes_source=content)
    poller = None
    # 1) 최신 스타일: body=bytes 직접
    try:
        poller = client.begin_analyze_document(model_id=model_id, body=content, content_type=content_type)
    except TypeError:
        pass
    # 2) 최신 스타일: body=AnalyzeDocumentRequest
    if poller is None:
        try:
            poller = client.begin_analyze_document(model_id=model_id, body=analyze_req, content_type=content_type)
        except TypeError:
            pass
    # 3) 구버전 키워드: analyze_request
    if poller is None:
        try:
            poller = client.begin_analyze_document(model_id=model_id, analyze_request=analyze_req, content_type=content_type)
        except TypeError:
            pass
    # 4) 더 구버전: 위치 인자(content)
    if poller is None:
        try:
            poller = client.begin_analyze_document(model_id, content, content_type=content_type)
        except TypeError as e:
            # 마지막 실패는 그대로 raise
            raise e

    if poller is None:
        raise RuntimeError("Failed to start analyze_document with any supported signature")

    result = poller.result()

    text_chunks: List[str] = []
    try:
        for page in result.pages or []:
            if getattr(page, "lines", None):
                for line in page.lines:
                    text_chunks.append(line.content)
    except Exception:
        pass

    full_text = "\n".join(text_chunks) if text_chunks else getattr(result, "content", "") or ""

    return {
        "extracted_text": full_text,
        "raw_result": result.as_dict() if hasattr(result, "as_dict") else None
    }


def main(req: dict) -> dict:
    """
    입력: {
      "file_names": ["a.pdf", ...],
      "files": ["<base64>", ...],
      "blob_urls": ["https://...sas"]
    }
    출력: {
      "file_analysis": [ { file_name, file_type, blob_url, extracted_text, processing_status }, ...],
      "extracted_content": "모든 파일의 텍스트 합본"
    }
    """
    logging.info("Executing ContentAwareAgent")

    file_names: List[str] = req.get("file_names", [])
    files_b64: List[str] = req.get("files", [])
    blob_urls: List[str] = req.get("blob_urls", [])

    if not files_b64 and not blob_urls:
        raise ValueError("files(Base64) 또는 blob_urls(SAS) 중 하나는 제공되어야 합니다.")

    container = os.environ.get("BLOB_CONTAINER", "uploads")

    file_analysis: List[Dict[str, Any]] = []
    merged_texts: List[str] = []

    # 입력 소스에 따라 순회 대상 구성
    sources: List[Dict[str, Any]] = []
    if files_b64:
        for i, b64 in enumerate(files_b64):
            sources.append({"name": file_names[i] if i < len(file_names) else f"file_{i+1}", "loader": "base64", "value": b64})
    if blob_urls:
        for i, url in enumerate(blob_urls):
            sources.append({"name": file_names[i] if i < len(file_names) else f"blob_{i+1}", "loader": "blob", "value": url})

    for src in sources:
        file_name = src["name"]
        try:
            if src["loader"] == "base64":
                content = base64.b64decode(src["value"])
            else:
                url = src["value"]
                content = None
                # 1차: SAS/공개 URL 직접 다운로드
                try:
                    with httpx.Client(follow_redirects=True, timeout=60.0) as client_http:
                        resp = client_http.get(url)
                        resp.raise_for_status()
                        content = resp.content
                except Exception as http_err:
                    logging.warning(f"HTTP download failed for {file_name}: {http_err}")
                # 2차: 같은 스토리지 계정이면 연결 문자열로 비공개 Blob 다운로드
                if content is None:
                    try:
                        # URL 형식: https://{account}.blob.core.windows.net/{container}/{blobPath}
                        path_part = url.split('.blob.core.windows.net/')[-1]
                        container_name = path_part.split('/')[0]
                        blob_path = '/'.join(path_part.split('/')[1:]).split('?')[0]
                        if not container_name or not blob_path:
                            raise ValueError("Failed to parse container/blob from URL")
                        conn_str = _get_env("AZURE_STORAGE_CONNECTION_STRING")
                        bsc = BlobServiceClient.from_connection_string(conn_str)
                        blob_client = bsc.get_blob_client(container=container_name, blob=blob_path)
                        content = blob_client.download_blob().readall()
                    except Exception as sdk_err:
                        raise RuntimeError(f"Blob download fallback failed: {sdk_err}")
        except Exception as e:
            logging.error(f"Load failed for {file_name}: {e}")
            file_analysis.append({
                "file_name": file_name,
                "file_type": "unknown",
                "blob_url": None,
                "extracted_text": "",
                "processing_status": "load_failed"
            })
            continue

        # 간단 검증: 길이와 PDF 시그니처 확인
        content_len = len(content) if content is not None else 0
        if content_len == 0:
            logging.error(f"Loaded empty content for {file_name}")
            file_analysis.append({
                "file_name": file_name,
                "file_type": "unknown",
                "blob_url": None,
                "extracted_text": "",
                "processing_status": "load_failed: empty_content"
            })
            continue

        is_pdf_sig = content.startswith(b"%PDF")

        # Blob 업로드
        blob_url = _upload_to_blob(container, file_name, content)

        # 파일 타입 추정
        file_type = "application/pdf" if file_name.lower().endswith(".pdf") else "application/octet-stream"
        if file_type == "application/pdf" and not is_pdf_sig:
            logging.warning(f"File {file_name} declared as PDF but signature missing. Possible HTML/403 or wrong file.")

        # Document Intelligence 추출
        try:
            di = _extract_text_with_di(content, file_type)
            extracted_text = di.get("extracted_text", "")
            merged_texts.append(extracted_text)
            status = "succeeded"
        except Exception as e:
            logging.error(f"Document Intelligence failed for {file_name} (len={content_len}, pdf_sig={is_pdf_sig}): {e}")
            extracted_text = ""
            status = f"di_failed: {e}"

        file_analysis.append({
            "file_name": file_name,
            "file_type": file_type,
            "blob_url": blob_url,
            "extracted_text": extracted_text,
            "processing_status": status
        })

    return {
        "file_analysis": file_analysis,
        "extracted_content": "\n\n".join(merged_texts)
    }

