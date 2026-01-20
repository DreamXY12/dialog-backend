import hashlib,base64

from sqlalchemy.orm import Session as Connection

from datetime import datetime, timedelta
from typing import Annotated, Union

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from schema.token import Token, TokenData

from sql.start import get_db
from sql.models import User, Case, Query, Session
from sql.crud import get_user_by_username, get_session_by_key
from config import get_parameter
##CONSTANT VARIABLE

#测试环境专用
SECRET_KEY = get_parameter("web", "secrete_key") or "dev_secret_key"
ALGORITHM = get_parameter("web", "algorithm") or "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = get_parameter("web", "expire_minute") or 60
TOKEN_URL = get_parameter("web", "token_url") or "/token"

#之前的代码
# SECRET_KEY = get_parameter("web", "secrete_key")
# ALGORITHM = get_parameter("web", "algorithm")

# ACCESS_TOKEN_EXPIRE_MINUTES = get_parameter("web", "expire_minute")
# TOKEN_URL = get_parameter("web", "token_url")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=TOKEN_URL)

'''authentication'''
def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password, hashed_password):
    digest_bytes = hashlib.sha256(plain_password.encode("utf-8")).digest()
    normalized_str = base64.b64encode(digest_bytes).decode("ascii")
    return pwd_context.verify(normalized_str, hashed_password)


def get_password_hash(password):
    normalized = hashlib.sha256(password.encode("utf-8")).digest()
    print("密码长度:")
    print(len(normalized))
    normalized_str = base64.b64encode(normalized).decode("ascii")
    return normalized_str
    # print(len(pwd_context.hash(normalized)))
    # return pwd_context.hash(normalized)


def authenticate_user(
        db: Connection,
        username: str,
        password: str
):
    user: User = get_user_by_username(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user
    

def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: Annotated[Connection, Depends(get_db)]
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

def get_current_session(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Connection, Depends(get_db)]
) -> Session:  
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        session_key = payload.get("session_key")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return get_session_by_key(db, session_key)
