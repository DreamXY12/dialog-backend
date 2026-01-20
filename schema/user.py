from pydantic import Field, BaseModel, validator
from typing import Optional, List, Union 


class User(BaseModel):
    username: str = Field(min_length=3, max_length=10)

class CreateUser(BaseModel):
    username: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)
    height: float = None
    weight: float = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = Field(default=None, min_length=4, max_length=6)
    family_history: Optional[str] = None
    smoking_status: Optional[str] = None
    drinking_history: Optional[str] = None

    invitation_code: str = None
    
    
    
class UserSignIn(BaseModel):
    username: str = Field(min_length=3, max_length=10)
    password: str = Field(min_length=6, max_length=12)

class LoginSuccess(BaseModel):
    username: str

class UserInDB(User):
    hashed_password: str 


class CreateSession(User):
    user_id: int
    session_key: str