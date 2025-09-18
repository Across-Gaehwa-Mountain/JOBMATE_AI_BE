# JobMate AI - 백엔드 서버리스 프로젝트 (Python 버전)

이 프로젝트는 JobMate AI 서비스의 백엔드를 **Python** 기반의 Azure Functions와 Durable Functions를 사용하여 멀티 에이전트 아키텍처로 구현한 샘플입니다.

## 🚀 프로젝트 구조

-   각 폴더는 하나의 Azure Function을 나타냅니다.
-   **`HttpStart/`**: 프론트엔드로부터 HTTP POST 요청을 받아 오케스트레이션을 시작하는 진입점입니다.
-   **`JobMateOrchestrator/`**: 전체 분석 프로세스를 조율하는 오케스트레이터입니다.
-   **`ComprehensionEvaluationAgent/`**: 이해도 점수와 피드백을 생성하는 에이전트입니다.
-   **`QuestionGenerationAgent/`**: 심층적인 질문을 생성하는 에이전트입니다.
-   **`ActionItemSuggestionAgent/`**: 다음 할 일을 제안하는 에이전트입니다.
-   **`shared_code/`**: 여러 함수에서 공통으로 사용하는 데이터 모델(`models.py`)이 포함되어 있습니다.
-   **`requirements.txt`**: 프로젝트 실행에 필요한 Python 패키지 목록입니다.

## ⚙️ 작동 방식

1.  **요청 시작**: 클라이언트가 분석할 데이터를 `HttpStart` 함수로 POST 요청을 보냅니다.
2.  **오케스트레이션 실행**: `HttpStart`는 `JobMateOrchestrator`를 비동기적으로 실행 시작합니다.
3.  **에이전트 병렬 호출**: `JobMateOrchestrator`는 3개의 핵심 분석 에이전트를 병렬로 호출하여 동시에 작업을 수행시킵니다.
4.  **결과 취합**: 모든 에이전트의 작업이 완료되면, 오케스트레이터는 각각의 반환 값을 하나의 `AnalysisResult` 객체로 취합하여 반환합니다.

## 🔧 설정 및 배포

1.  `pip install -r requirements.txt` 명령어로 필요한 패키지를 설치합니다.
2.  Azure Functions Core Tools를 설치하고 `func start` 명령어로 로컬에서 프로젝트를 실행하고 테스트할 수 있습니다.
3.  배포는 Visual Studio Code의 Azure Functions 익스텐션 또는 Azure CLI를 통해 간편하게 진행할 수 있습니다.
