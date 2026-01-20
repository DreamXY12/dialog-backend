from fastapi import Request, Query, APIRouter, HTTPException, Body
from typing import Optional, List, Union
from typing_extensions import Annotated

import openai 

from fastapi import Depends

from sqlalchemy.orm import Session as Connection

from core.auth import get_current_session
from core import llm
from core.translate import to_other_language
from core.services import registration_list, service_functions
from sql.models import User, Session, Query, Case
from sql.cache_database import store_message, get_chat_history
from sql.start import get_db
from sql.crud import create_query, update_response, get_session_by_key, get_queries_by_session, get_total_queries
import json
from config import get_parameter

# 修改后的代码使用了or给了默认值
MAXIMUM_QUERIES = int(get_parameter("chat", "max_queries") or 10)
MAX_TOKEN = int(get_parameter("chat", "max_token") or 1024)
TEMPERATURE = float(get_parameter("chat", "temperature") or 0.7)

openai.api_key = get_parameter("openai", "api_key")
FUNCTIONAL_CALL_MODEL = get_parameter("openai", "functional_call_model")

router = APIRouter(prefix='/session', tags=["session"])

def clean_text(text):
    # Remove leading/trailing whitespace
    text = text.strip()
    # Replace multiple newlines or carriage returns with a space
    text = text.replace('\n', ' ').replace('\r', ' ')
    # Replace multiple spaces with a single space
    text = ' '.join(text.split())
    return text

def distribute(q: Query):
    "Determine the functional call"
    response = openai.ChatCompletion.create(
        model=FUNCTIONAL_CALL_MODEL,
        messages=[{'role': 'user', 'content': q.enquiry}],
        functions=service_functions,
        function_call='auto'
    )
    # distribute the functions
    response = response['choices'][0]['message']
    try:
        function_name = response["function_call"]['name']
        function_args = json.loads(response['function_call']['arguments'])
        return function_name, function_args
    # no matching services
    except KeyError as e:
        return "advise", {}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=409, detail="Cannot communicate with the AI module")

def response_from_llm(q: Query, current_session: Session, db, phone_number=None):
    chat_id = phone_number if phone_number != None else current_session.session_key
    q.enquiry = to_other_language(q.enquiry, "en")
    history = get_chat_history(chat_id)

    if len(history) == 0:
        # store the system message
        store_message(chat_id, llm.initial_history[0])
        print(f"history initiated: {get_chat_history(chat_id)}")
        
    function_name, function_args = distribute(q)

    print(f"{function_name=}")
    # customized functions
    if function_name in registration_list["direct_functions"]:
        generated_text: str = registration_list["direct_functions"][function_name](q=q, current_session=current_session, **dict(function_args))
        store_message(chat_id, ('human', q.enquiry))
    else:
        prompt: str = registration_list["prompt_functions"][function_name](q=q, current_session=current_session, **dict(function_args))
        print("prompt: ", prompt)
        store_message(chat_id, ('human', prompt))
        generated_text = llm.response(
            human_input = q.enquiry,
            session_id=chat_id
        )
    generated_text = clean_text(generated_text)
    
    update_response(db, q, response=generated_text)
    return {"question": q.enquiry, "response": generated_text}

@router.post("/query", response_model=None)
def ask(
    current_session: Annotated[Session, Depends(get_current_session)],
    db: Annotated[Connection, Depends(get_db)],
    enquiry: Annotated[str, Query]
):  
    
    # check if the query has exceeded the maximum limit
    n_queries = get_total_queries(db, user=current_session.user)
    if n_queries > MAXIMUM_QUERIES:
        raise HTTPException(401, detail="your queries has exceeded the maximum of {}".format(MAXIMUM_QUERIES))
    # create query
    if current_session == None:
        raise HTTPException(status_code=401, detail="unauthorized session")
    q = Query(session_key=current_session.session_key, enquiry=enquiry)
    q = create_query(db, q)
    
    return response_from_llm(q, current_session, db)






