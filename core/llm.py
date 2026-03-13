from langchain_community.llms import Ollama
from langchain_core.prompts import ChatPromptTemplate
from sql.cache_database import get_chat_history
import time
from config import get_parameter
import requests
from requests.auth import HTTPBasicAuth


#修改后的代码
BASE_URL = get_parameter("ollama", "base_url") or "http://localhost:11434" #远程的已经下线了
#BASE_URL = "http://localhost:11434"
MODEL_ID = get_parameter("ollama", "model_id") or "llama3"
#测试输出
print("测试是否取到模型名称和ID")
print("MODEL_ID =", MODEL_ID)
print("BASE_URL =", BASE_URL)
AUTH_USERNAME = get_parameter("ollama", "auth_username") or ""
AUTH_PASSWORD = get_parameter("ollama", "auth_password") or ""

#以前的代码
# BASE_URL = get_parameter("ollama", "base_url")
# MODEL_ID = get_parameter("ollama", "model_id")
# AUTH_USERNAME = get_parameter("ollama", "auth_username")
# AUTH_PASSWORD = get_parameter("ollama", "auth_password")

def serve_model(model_id):
    # session = requests.Session()
    # session.auth = HTTPBasicAuth("dialog", "dialog#Y27u")
    if model_id and model_id.startswith("gpt"):
        raise NotImplementedError("GPT is not allowed for Chinese Region")
    else:
        # 如果没有提供有效的模型ID，使用默认模型
        if not model_id:
            model_id = "llama3"
        
        # 如果没有提供有效的认证信息，不使用认证
        auth = None
        if AUTH_USERNAME and AUTH_PASSWORD:
            auth = HTTPBasicAuth(AUTH_USERNAME, AUTH_PASSWORD)
        
        llm = Ollama(
            model=model_id,
            base_url=BASE_URL,
            auth=auth
            )
    return llm


__ = '''
(
        "Your name is DiaLOG, and you are a helpful assistant specified in diabetes care. If the user messages include "
        "personal information, you must respond the message based on the information, the risk level in these information"
        "was determined by physician and should be taken into consideration to your response. For example, if the person's risk level "
        "is high and the user is seeking for health advice, you might explicitly ask the user to go make a medical appointment,"
        "ask for medical intervention and appropriate drug prescription; if the risk is medium, you can provide moderate advices like "
        "controlling the weight and quitting smoking based on the personal information provided; if the risk level is low, you can loosen the"
        "constraint and provide more general health advices like regular monitoring of blood sugar level, and regular exercise."
        )
'''
# set up the initial template
initial_history = [
    ("system", (
        "Your name is DiaLOG, and you are a helpful assistant specified in diabetes care. Do not reject the patient queries, and give them the advice accordingly."
        "You need to answer the patients medical queries in less than 100 words."
        )
    
    ),
    
    
]
__llm = serve_model(MODEL_ID)

def response(human_input, session_id):
    history = get_chat_history(session_id)
    history.append(("human", human_input))
    template = ChatPromptTemplate(history)
    chain = template | __llm
    response = chain.invoke({})

    return response

