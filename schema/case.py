from pydantic import Field, BaseModel, validator
from typing import Optional, List, Union
from datetime import datetime, date
from sql.models import User


class UploadBody(BaseModel):
    hba1c: Union[float, None] = None
    fasting_glucose: Union[float, None] = None
    hdl_cholesterol: Union[float, None] = None
    total_cholesterol: Union[float, None] = None
    ldl_cholesterol: Union[float, None] = None
    creatinine: Union[float, None] = None
    triglyceride: Union[float, None] = None
    potassium: Union[float, None] = None
    test_date: str
    time_spec: int = 2

class DashboardItem(BaseModel):
    case_id: int
    labtest_date: date
    create_time: Optional[datetime] = None
    time_spec: Optional[int] = None
    analysis_result: Optional[int] = None
    score: Optional[float] = None
    hba1c: Optional[float] = None
    fasting_glucose: Optional[float] = None
    hdl_cholesterol: Optional[float] = None
    total_cholesterol: Optional[float] = None
    ldl_cholesterol: Optional[float] = None
    creatinine: Optional[float] = None
    triglyceride: Optional[float] = None
    potassium: Optional[float] = None

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

