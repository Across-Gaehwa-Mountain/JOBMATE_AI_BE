# ContentAwareAgent

Azure AI Document Intelligence를 사용하여 파일을 분석하는 Azure Function입니다.

## 기능

- PDF, 이미지, Office 문서 등 다양한 파일 형식 지원
- Azure AI Document Intelligence의 prebuilt-layout 모델을 사용한 문서 분석
- 텍스트 추출, 테이블 인식, 문서 구조 분석
- 신뢰도 점수 제공

## 설정

### 1. Azure Document Intelligence 리소스 생성

1. Azure Portal에서 "Document Intelligence" 리소스를 생성합니다.
2. 엔드포인트 URL과 API 키를 확인합니다.

### 2. 환경 변수 설정

`local.settings.json` 파일에 다음 환경 변수를 설정합니다:

```json
{
	"Values": {
		"AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://your-resource.cognitiveservices.azure.com/",
		"AZURE_DOCUMENT_INTELLIGENCE_KEY": "your-api-key-here"
	}
}
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

## 사용법

### 입력 형식

```json
{
	"file_names": ["document1.pdf", "document2.docx", "image1.jpg"],
	"files": [
		"base64-encoded-file1-content",
		"base64-encoded-file2-content",
		"base64-encoded-file3-content"
	]
}
```

### 출력 형식

```json
{
	"file_analysis": [
		{
			"file_name": "document1.pdf",
			"file_type": "application/pdf",
			"extracted_text": "첫 번째 문서의 추출된 텍스트 내용...",
			"document_structure": {
				"paragraphs": [
					{
						"content": "문단 내용",
						"confidence": 0.95
					}
				],
				"tables": [
					{
						"row_count": 3,
						"column_count": 2,
						"cells": [
							{
								"content": "셀 내용",
								"confidence": 0.9
							}
						]
					}
				]
			},
			"confidence_score": 0.92,
			"processing_status": "completed"
		},
		{
			"file_name": "document2.docx",
			"file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"extracted_text": "두 번째 문서의 추출된 텍스트 내용...",
			"document_structure": {...},
			"confidence_score": 0.88,
			"processing_status": "completed"
		}
	],
	"extracted_content": "첫 번째 문서의 추출된 텍스트 내용...\n\n두 번째 문서의 추출된 텍스트 내용...",
	"total_files_processed": 2,
	"error": null
}
```

## 지원 파일 형식

- PDF (.pdf)
- 이미지 파일 (.jpg, .jpeg, .png, .bmp, .tiff)
- Microsoft Office 문서 (.docx, .xlsx, .pptx)
- 기타 Azure Document Intelligence에서 지원하는 형식

## 에러 처리

파일 분석 중 오류가 발생하면 `processing_status`에 에러 메시지가 포함되고, `error` 필드에 상세한 오류 정보가 제공됩니다.

## 주의사항

- 파일 크기 제한: Azure Document Intelligence의 제한에 따릅니다 (일반적으로 500MB)
- API 호출 제한: Azure 구독의 할당량에 따라 제한됩니다
- 파일 형식: 지원되지 않는 형식의 경우 분석이 실패할 수 있습니다
