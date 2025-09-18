from dataclasses import dataclass, asdict, field
from typing import List, Optional

@dataclass
class NextAction:
    action: str
    priority: str

    def to_dict(self):
        return asdict(self)

@dataclass
class Feedback:
    score: int
    good_points: List[str]
    improvement_points: List[str]
    missed_points: List[str]
    mentor_comment:List[str]
    reasoning_summary:List[str]
    
    def to_dict(self):
        return asdict(self)

@dataclass
class AnalysisResult:
    score: int
    feedback: Feedback
    suggested_questions: List[str] = field(default_factory=list)
    next_actions: List[NextAction] = field(default_factory=list)

    def to_dict(self):
        # asdict는 중첩된 dataclass도 재귀적으로 dict로 변환해줍니다.
        return asdict(self)
