from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime

# 单选枚举字面量，和前端保持一致
ExerciseOpt = Literal["No exercise", "Less than 1 hour", "1-2 hours", "2-3 hours", "3 hours or more"]
AlcoholOpt = Literal["Non-drinker", "Ex-drinker", "Social drinker", "Chronic drinker"]
SmokingOpt = Literal["Never", "Ex-smoker", "Smoker"]
YesNo = Literal["Yes", "No"]
YesNoNA = Literal["Yes", "No", "Not applicable"]
AnswerABCDE = Literal["a", "b", "c", "d", "e"]

# 单道题目
class QuizItem(BaseModel):
    questionId: str
    selectedAnswer: Optional[AnswerABCDE] = None

# 基础健康模块
class BaseHealthSubmit(BaseModel):
    assessmentDate: str
    bodyWeight: Optional[float] = None
    cardioExercisePerWeek: Optional[ExerciseOpt] = None
    muscleStrengthenPerWeek: Optional[ExerciseOpt] = None
    alcoholUse: Optional[AlcoholOpt] = None
    smoking: Optional[SmokingOpt] = None
    healthyDietHabit: Optional[YesNo] = None
    selfMonitorBP: Optional[YesNo] = None
    selfMonitorBG: Optional[YesNoNA] = None
    attemptQuitSmoking: Optional[YesNoNA] = None
    attemptManageWeight: Optional[YesNo] = None

# 完整问卷提交体
class Week9QuestionnaireSubmit(BaseModel):
    baseHealth: BaseHealthSubmit
    dmQuiz: List[QuizItem]
    htQuiz: List[QuizItem]

# 问卷查询返回结构
class SingleQuestionnaireResp(BaseModel):
    id: int
    patientId: int
    baseHealth: BaseHealthSubmit
    dmQuiz: List[QuizItem]
    htQuiz: List[QuizItem]
    createdAt: str
    updatedAt: str

# 弹窗状态返回
class QuestionnaireStatusResp(BaseModel):
    is_week9_questionnaire_completed: int
    patient_create_time: datetime
