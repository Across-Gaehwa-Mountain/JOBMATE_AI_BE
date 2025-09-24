import os
import base64
import requests
from typing import List

def is_audio_or_video(filename: str) -> bool:
    audio_exts = ['.wav', '.mp3', '.m4a', '.aac', '.ogg', '.flac']
    video_exts = ['.mp4', '.avi', '.mov', '.wmv', '.mkv']
    ext = os.path.splitext(filename)[1].lower()
    return ext in audio_exts + video_exts

def stt_from_file(file_bytes: bytes, filetype: str, azure_speech_key: str, azure_speech_region: str) -> str:
    speech_endpoint = f"https://{azure_speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    headers = {
        'Ocp-Apim-Subscription-Key': azure_speech_key,
        'Content-Type': f'audio/{filetype}' if filetype in ['wav', 'mp3', 'ogg', 'flac', 'aac', 'm4a'] else 'application/octet-stream',
    }
    params = {
        'language': 'ko-KR',
    }
    try:
        response = requests.post(speech_endpoint, params=params, headers=headers, data=file_bytes, timeout=60)
        if response.status_code == 200:
            result = response.json()
            return result.get('DisplayText', '')
        else:
            return f"[STT 실패: {response.status_code}]"
    except Exception as e:
        return f"[STT 예외: {str(e)}]"

def stt_for_files(file_names: List[str], files: List[str], azure_speech_key: str, azure_speech_region: str) -> List[str]:
    """
    file_names: 파일명 리스트
    files: base64 인코딩된 파일 바이너리 리스트
    """
    stt_texts: List[str] = []
    for idx, fname in enumerate(file_names):
        if is_audio_or_video(fname):
            try:
                file_bytes = base64.b64decode(files[idx])
                # 10MB 이상은 별도 처리 (Azure STT REST API는 10MB 제한)
                if len(file_bytes) > 10 * 1024 * 1024:
                    stt_texts.append(f"[파일 '{fname}'은(는) 10MB 초과로 STT를 건너뜀]")
                else:
                    ext = os.path.splitext(fname)[1].lower().replace('.', '')
                    stt_result = stt_from_file(file_bytes, ext, azure_speech_key, azure_speech_region)
                    stt_texts.append(f"[{fname} STT 결과]: {stt_result}")
            except Exception as e:
                stt_texts.append(f"[{fname} STT 처리 중 오류: {str(e)}]")
    return stt_texts
import os
import base64
import requests
from typing import List

def is_audio_or_video(filename: str) -> bool:
    audio_exts = ['.wav', '.mp3', '.m4a', '.aac', '.ogg', '.flac']
    video_exts = ['.mp4', '.avi', '.mov', '.wmv', '.mkv']
    ext = os.path.splitext(filename)[1].lower()
    return ext in audio_exts + video_exts


def stt_from_file(file_bytes: bytes, filetype: str, azure_speech_key: str, azure_speech_region: str) -> str:
    speech_endpoint = f"https://{azure_speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    headers = {
        'Ocp-Apim-Subscription-Key': azure_speech_key,
        'Content-Type': f'audio/{filetype}' if filetype in ['wav', 'mp3', 'ogg', 'flac', 'aac', 'm4a'] else 'application/octet-stream',
    }
    params = {
        'language': 'ko-KR',
    }
    try:
        response = requests.post(speech_endpoint, params=params, headers=headers, data=file_bytes, timeout=60)
        if response.status_code == 200:
            result = response.json()
            return result.get('DisplayText', '')
        else:
            return f"[STT 실패: {response.status_code}]"
    except Exception as e:
        return f"[STT 예외: {str(e)}]"


def stt_for_files(file_names: List[str], files: List[str], azure_speech_key: str, azure_speech_region: str) -> List[str]:
    """
    file_names: 파일명 리스트
    files: base64 인코딩된 파일 바이너리 리스트
    """
    stt_texts: List[str] = []
    for idx, fname in enumerate(file_names):
        if is_audio_or_video(fname):
            try:
                file_bytes = base64.b64decode(files[idx])
                # 10MB 이상은 별도 처리 (Azure STT REST API는 10MB 제한)
                if len(file_bytes) > 10 * 1024 * 1024:
                    stt_texts.append(f"[파일 '{fname}'은(는) 10MB 초과로 STT를 건너뜀]")
                else:
                    ext = os.path.splitext(fname)[1].lower().replace('.', '')
                    stt_result = stt_from_file(file_bytes, ext, azure_speech_key, azure_speech_region)
                    stt_texts.append(f"[{fname} STT 결과]: {stt_result}")
            except Exception as e:
                stt_texts.append(f"[{fname} STT 처리 중 오류: {str(e)}]")
    return stt_texts
