from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any

@dataclass
class NextAction:
    action: str
    priority: str
    key: Optional[int] = None

    def to_dict(self):
        return asdict(self)

@dataclass
class Feedback:
    score: int
    good_points: List[str] = field(default_factory=list)
    improvement_points: List[str] = field(default_factory=list)
    missed_points: List[str] = field(default_factory=list)
    mentor_comment:List[str] = field(default_factory=list)
    reasoning_summary:List[str] = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)

@dataclass
class FileAnalysisResult:
    """파일 분석 결과를 담는 데이터 클래스"""
    file_name: str
    file_type: str
    extracted_text: str
    document_structure: Dict[str, Any]
    confidence_score: float
    processing_status: str

    def to_dict(self):
        return asdict(self)

@dataclass
class AnalysisRequest:
    """분석 요청을 담는 데이터 클래스"""
    file_names: List[str]
    files: List[Any]  # File 객체들 (Base64 인코딩된 데이터)
    user_summary: str

    def to_dict(self):
        return asdict(self)

@dataclass
class AnalysisResult:
    score: int
    feedback: Feedback
    suggested_questions: List[str] = field(default_factory=list)
    next_actions: List[NextAction] = field(default_factory=list)
    file_analysis: Optional[List[Dict[str, Any]]] = None  # 여러 파일 분석 결과

    def to_dict(self):
        # asdict는 중첩된 dataclass도 재귀적으로 dict로 변환해줍니다.
        return asdict(self)
