from pydantic import Field, BaseModel, validator
from typing import Optional, List, Union
from datetime import datetime, date
from sql.models import User


class UploadBody(BaseModel):
    cholesHDL: Union[float, None] = None
    choles: Union[float, None] = None
    creatinine: Union[float, None] = None
    fastingGlucose: Union[float, None] = None
    triglyceride: Union[float, None] = None
    cholesLDL_1: Union[float, None] = None
    potassiumSerumOrPlasma: Union[float, None] = None
    HBA1C: Union[float, None] = None
    labtest_date: str
    time_spec: int = 2

class DashboardItem(BaseModel):
    case_id: int
    labtest_date: date
    time_spec: int = None
    analysis_result: int = None

class Step(BaseModel):
    cholesHDL: float
    choles: float
    creatinine: float
    fastingGlucose: float
    triglyceride: float
    cholesLDL_1: float
    potassiumSerumOrPlasma: float
    HBA1C: float

class MarginRequest(BaseModel):
    case_id: int
    step: Step

class MarginResponse(BaseModel):
    cholesHDL: Union[float, None] = None
    choles: Union[float, None] = None
    creatinine: Union[float, None] = None
    fastingGlucose: Union[float, None] = None
    triglyceride: Union[float, None] = None
    cholesLDL_1: Union[float, None] = None
    potassiumSerumOrPlasma: Union[float, None] = None
    HBA1C: Union[float, None] = None

class HistoryResponse(BaseModel):
    labtest_date: date
    score: float = None

class DenseResponse(BaseModel):
    dense: List[float]
    score: float = None
    exceeded_portion: float = None
    threshold: List[float] = None

