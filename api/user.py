from fastapi import APIRouter, HTTPException, Depends
from typing_extensions import Annotated
from datetime import timedelta
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session as Connection

from core.auth import authenticate_user, get_password_hash, create_access_token
from sql.models import User, Case, Query, Session
from sql.start import get_db
from sql.crud import create_user, get_user_by_username, create_session, get_invitation_by_code, set_invitation_status, get_n_users
from schema.user import CreateUser, LoginSuccess
from schema.token import Token
from config import get_parameter

router = APIRouter(prefix='/user', tags=["user"])

#修改后的代码
ACCESS_TOKEN_EXPIRE_MINUTES = int(get_parameter("auth", "access_token_expire_minutes") or 60)
MAX_ACCOUNTS = int(get_parameter("auth", "max_accounts") or 10)

#以前的代码
#ACCESS_TOKEN_EXPIRE_MINUTES = int(get_parameter("auth", "access_token_expire_minutes"))
#MAX_ACCOUNTS = int(get_parameter("auth", "max_accounts"))


@router.post("/signup")
def sign_up(
    createUser: CreateUser,
    db: Annotated[Connection, Depends(get_db)]
):
    username = createUser.username
    password = createUser.password

    # if len(username) <= 3 or len(username) > 10:
    #     raise HTTPException(status_code=400, detail="the length of username must be smaller than 10 and greater than 3")
    
    # if len(password) <= 6 or len(password) > 12:
    #     raise HTTPException(status_code=400, detail="the length of password must be smaller than 12 and greater than 6")
    
    db_user = get_user_by_username(db, username)
    if db_user != None:
        raise HTTPException(status_code=409, detail="the username is not available")
    
    # check the invitation code
    code = createUser.invitation_code
    inv = get_invitation_by_code(db, code)
    if inv == None or not inv.status:
        raise HTTPException(status_code=401, detail="your invitation code is invalid")
    #check if the total account excesses 20
    n_acc = get_n_users(db, code=code)
    print(n_acc)
    if n_acc == MAX_ACCOUNTS:
        set_invitation_status(db, inv, False)
        raise HTTPException(status_code=401, detail=f"your accounts number has reached the maximum of %d".format(MAX_ACCOUNTS))
    # write to database
    newHashPassword = get_password_hash(password)
    db_user = User(
        username = createUser.username,
        hashed_password = newHashPassword,
        date_of_birth = createUser.date_of_birth,
        sex = createUser.sex,
        family_history = createUser.family_history,
        smoking_status = createUser.smoking_status,
        drinking_history = createUser.drinking_history,
        height = createUser.height,
        weight = createUser.weight,
        identity = inv.tag,
        code=code
    )
    db_user = create_user(db, db_user)
    return LoginSuccess(username = db_user.username)


@router.post("/login", response_model=Token, summary="Authenticate login and create new token for new authenticated user")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Connection, Depends(get_db)]
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    session_key = str(uuid.uuid4()) 
    access_token = create_access_token(
        data={
            "sub": user.username,
            "session_key": session_key
        }, 
        expires_delta=access_token_expires
    )

    # create session
    db_session = Session(session_key=session_key, user_id=user.user_id, status=True)
    create_session(db, db_session)
    return {"access_token": access_token, "token_type": "bearer"}


        




