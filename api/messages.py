import logging
from twilio.rest import Client
from fastapi import Request, APIRouter, HTTPException
from core.translate import to_other_language
from sql.cache_database import r, store_message, get_chat_history
from sql.start import get_db
import sql.crud as crud
from api.user import sign_up, CreateUser
from api.session import response_from_llm
from sql.models import Session, Query
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session as Connection
import re
from core.auth import get_current_session
from datetime import datetime, timedelta
import uuid
from config import get_parameter

# 修改后的代码，现在先用明文，主要是先联通起来
TWILIO_ACCOUNT_SID=get_parameter("twilio", "account_sid")
TWILIO_AUTH_TOKEN=get_parameter("twilio", "auth_token")
TWILIO_NUMBER=get_parameter("twilio", "phone_number")

# 当前远程服务器上存储的debug的值为0
# 这里的DEBUG值为False
DEBUG = get_parameter("dev", "debug") == "1"

router = APIRouter(prefix='/whatsapp', tags=["whatsapp"])

account_sid = TWILIO_ACCOUNT_SID
auth_token = TWILIO_AUTH_TOKEN
client = Client(account_sid, auth_token)

logging.basicConfig(
    level=logging.INFO,
    filename='dev.log',             # Write logs to dev.log
    filemode='a',                   # Append mode (use 'w' to overwrite)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

twilio_number = "+14155238886"

sign_up_form = [ #tuple(query string, retain string)
    "Greeting! My name is DiaLOG, a diabetes AI chatbot, to use our service, please enter your invitation code.",
    "What is your weight (kg)?",
    "What is your height in cm?",
    "What is your age",
    "What is your sex? (Female/Male/Prefer not to tell)",
    "Do you have family history of diabetes? (Yes/No/Unknown)",
    "Do you smoke? (Yes/No/Prefer not to tell)",
    '''How often do you consume alcoholic beverages? You can choose from the following options:
Never
Rarely (a few times a year)
Occasionally (once a month)
Frequently (several times a week)
Daily
'''
]
unexceptional_response = [
    "Sorry the invitation code is not valid, please ask admin for the latest key phrase.",
    '''Sorry, I cannot understand you. What is your weight? You can say:" My weight is 78kg."''',
    '''Sorry, I cannot understand you. What is your height? You can say:" My height is 173cm."''',
    '''Sorry, I cannot understand you. What is your age, you could say" 69"''',
    '''Sorry, I cannot understand you. What is your sex? You can say:" Female."''',
    '''Sorry, I cannot understand you. Do you have family history of diabetes? You can say:" Yes.''',
    '''Sorry, I cannot understand you. Do you smoke? You can say:" Yes.''',
    '''Sorry, I cannot understand you. How often do you consume alcoholic beverages? You can choose from the following: Never
Rarely (a few times a year)
Occasionally (once a month)
Frequently (several times a week)
Daily.
'''
]   

@router.get("/")
def read_root():
    return {"message": "Fish on!"}

def send_message(to_number, body_text, role):
    try:
        print(f"{body_text=}")
        yue_body_text = to_other_language(body_text, "yue")
        print(f"{yue_body_text=}")
        
        message = client.messages.create(
                from_=f"whatsapp:{twilio_number}",
                body=yue_body_text,
                to=f"whatsapp:{to_number}",
                status_callback="https://regulable-sublittoral-lianne.ngrok-free.dev/api/v1/whatsapp/status"
            )
        store_message(to_number, (role, body_text))
        print("from:",f"whatsapp:{twilio_number}")
        print("to:",f"whatsapp:{to_number}")
        
        logger.info(f"Message sent to {to_number}: {message.body}")
    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {e}")

async def extract(request: Request):
    form_data = await request.form()

    # Extract parameters from the form data
    message_sid = form_data.get("MessageSid")
    sms_sid = form_data.get("SmsSid")
    sms_message_sid = form_data.get("SmsMessageSid")
    account_sid = form_data.get("AccountSid")
    messaging_service_sid = form_data.get("MessagingServiceSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    body = form_data.get("Body")
    num_media = form_data.get("NumMedia")
    num_segments = form_data.get("NumSegments")
    
    return {
        "MessageSid": message_sid,
        "SmsSid": sms_sid,
        "SmsMessageSid": sms_message_sid,
        "AccountSid": account_sid,
        "MessagingServiceSid": messaging_service_sid,
        "From": from_number,
        "To": to_number,
        "Body": body,
        "NumMedia": num_media,
        "NumSegments": num_segments
    }
    
@router.post("/")
async def reply(request:Request, db: Annotated[Connection, Depends(get_db)]):
    
    data = await extract(request)
    question = data["Body"]
    phone_number = data["From"].split(":")[-1]
    
    # decide whether to sign up
    user = crud.get_user_by_username(db, phone_number)

    if user == None:
        logger.info(get_chat_history(phone_number))
        # retrieve the last message
        history = get_chat_history(phone_number)
        if len(history) == 0:
            send_message(phone_number, sign_up_form[0], "system")
            return
        print("History:", history)
        for i, text in enumerate(sign_up_form):
            sys_text = ""
            for his in reversed(history):
                if his[0] == "system":
                    sys_text = his[1]
                    break
            if sys_text not in unexceptional_response and sys_text not in sign_up_form:
                    send_message(phone_number, "There are some unexceptional errors, please try to sign up again.", 'system')
                    for key in r.scan_iter(f"chat:{phone_number}*"):
                        r.delete(key)
                    break
                
            if (text == sys_text or unexceptional_response[i] == sys_text):
                print(i)
                ok = sign_up_roll(i, db, phone_number, question)
                if ok:
                    if i == len(sign_up_form) - 1:
                        send_message(phone_number, "You have finished sign up procedure, you can now talk to our chatbot.", "system")
                        sign_up_whatsapp(phone_number, db)
                    else:
                        send_message(phone_number, sign_up_form[i+1], "system")
                else:
                    send_message(phone_number, unexceptional_response[i], "system")
                return
        
        return
    session = crud.get_latest_session(db, user_id = user.user_id)
    
    if session == None or session.create_time < datetime.utcnow() - timedelta(minutes=30):
        session_key = str(uuid.uuid4()) 
        db_session = Session(session_key=session_key, user_id=user.user_id, status=True)
        session = crud.create_session(db, db_session)
    
    q = Query(session_key=session.session_key, enquiry=question)
    q = crud.create_query(db, q)

    chat_response = response_from_llm(q, session, db, phone_number)
    
    send_message(phone_number, chat_response["response"], "ai")
    # except Exception as e:
    #     print(e)
    #     logger.error(e)        
    #     send_message(phone_number, "Sorry, there are some internal errors.", "system")

@router.post("/status")
@router.post("/status/")  
async def replyStatus(request:Request):
    print("testReplyStatus")


def sign_up_roll(i, db, phone_number, user_response) -> bool:
    if i == 0:
        if crud.get_invitation_by_code(db, user_response) != None:
            r.set(f"info-{phone_number}:invitation_code", user_response)
            return True
        return False
    
    if i == 1:
        match = re.search(r"\b(\d+)\s*k?g?\b", user_response.lower())

        if match:
            weight = float(match.group(1))
            r.set(f"info-{phone_number}:weight", weight)
            return True
        else:
            return False

    if i == 2:
        match = re.search(r"\b(\d+)\s*c?m?\b", user_response.lower())
        if match:
            height = float(match.group(1))
            if height < 100:
                return False
            r.set(f"info-{phone_number}:height", height)
            return True
        else:
            return False
            
    if i==3:
        match = re.search(r'(\b(\d+))', user_response)
        if match:
            r.set(f"info-{phone_number}:age", int(match.group(1)))
            return True
        else:
            return False

    if i == 4:
        match = re.search(r'\b(Female|Male|Prefer not to tell)\b', user_response, re.IGNORECASE)
        if match:
            sex = match.group(1).title()
            r.set(f"info-{phone_number}:sex", sex)
            return True
        else:
            return False

    if i == 5:
        match = re.search(r'\b(Yes|No|Unknown)\b', user_response, re.IGNORECASE)
        if match:
            his = match.group(1).title()
            r.set(f"info-{phone_number}:family_history", his)
            return True
        else:
            return False
            
    if i == 6:
        pattern = r'\b(Yes|No|Prefer not to tell)\b'
        # Search for the pattern in the response
        match = re.search(pattern, user_response)
        if match:
            smoking_status = match.group(0).title()
            
            r.set(f"info-{phone_number}:smoking_status", smoking_status)
            return True
        else:
            return False
    
    if i == 7:
        pattern = r"(Never|Rarely|Occasionally|Regularly|Frequently|Daily)"
        match = re.search(pattern, user_response, re.IGNORECASE)
        if match:
            drinking_history = match.group(1).title()
            r.set(f"info-{phone_number}:drinking_history", drinking_history)
            return True
        else:
            return False
    
    raise NotImplementedError(f"Conversation {i} is not in the sing up form")
        
            
            
        
def sign_up_whatsapp(phone_number, db):
    
    def pre_process(s):
        # Convert bytes to string if needed
        if isinstance(s, bytes):
            s = s.decode('utf-8', errors='ignore')  # decode safely

        s = str(s).strip()  # Ensure it's a clean string

        if s.lower() == "unknown" or s.lower() == "prefer not to tell":
            return None
        elif s.lower() == "yes":
            return True
        elif s.lower() == "no":
            return False
        return s
    
    salt = get_parameter("auth", "salt")
    age = int(r.get(f"info-{phone_number}:age"))
    current_year = datetime.now().year
    birth_year = current_year - age
    birth_date = datetime(birth_year, 1, 1).strftime("%Y-%m-%d")
    new_user = CreateUser(
            username = phone_number,
            password = f"{salt}{phone_number}",
            invitation_code=r.get(f"info-{phone_number}:invitation_code"),
            date_of_birth = birth_date,
            height = float(r.get(f"info-{phone_number}:height")),
            weight = float(r.get(f"info-{phone_number}:weight")),
            sex = pre_process(r.get(f"info-{phone_number}:sex")),
            family_history = r.get(f"info-{phone_number}:family_history"),
            smoking_status = r.get(f"info-{phone_number}:smoking_status"),
            drinking_history = r.get(f"info-{phone_number}:drinking_history")
    )
    try:
        user = sign_up(
            new_user,
            db
        )
    except HTTPException as e:
        logger.error(e)
        send_message(phone_number, "Sorry, the sign up process fails, please try again", "system")

    for key in r.scan_iter(f"info-{phone_number}*"):
        r.delete(key)
    
    for key in r.scan_iter(f"chat:{phone_number}*"):
        r.delete(key)
