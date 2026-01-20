import datetime

from core.risk_engine import RiskEngine

from typing import List, Dict, Callable, Union
from sql.crud import create_case, get_case_by_id, get_case_by_closest_date
from schema.case import UploadBody, Step
from sql.start import SessionLocal
from fastapi import Request, Query, APIRouter, HTTPException, Body
from typing import Optional, List, Union
from sql.models import User, Session, Query, Case
from sql.crud import get_latest_case, create_query, get_queries_by_session
from core.utils import assemble
from core.margin import Margin
from datetime import datetime

risk_map = {
    "low risk":0,
    "medium risk":1,
    "high risk":2,
    "unknown risk" : None
}

# dense meta data
DENSE = {
    2: [
        0.007031738222528992,
        0.010383824116446183,
        0.01491947540773409,
        0.02086591992892659,
        0.02842009217120187,
        0.03771986854038877,
        0.04881675109136721,
        0.06165565019669958,
        0.07606744711592234,
        0.09177869924314282,
        0.10844023709689181,
        0.1256729283544811,
        0.14312528527362096,
        0.16053470073791629,
        0.17778259282570603,
        0.1949339333893618,
        0.21225341049464142,
        0.2301933602676922,
        0.24935200459869034,
        0.27040396065713959,
        0.29400821218884379,
        0.32070174450365626,
        0.35078988442374206,
        0.3842468970797699,
        0.42064205841751775,
        0.45910640397749055,
        0.4983527442862318,
        0.536755781950971,
        0.5724904809098763,
        0.6037164320625472,
        0.628785923164454,
        0.6464462613632658,
        0.6560048198796744,
        0.6574294506944127,
        0.6513669480293444,
        0.639076199869178,
        0.6222874365934592,
        0.6030112086405821,
        0.5833277156231015,
        0.5651876193763561,
        0.5502499732919349,
        0.5397733127542275,
        0.5345649594685531,
        0.5349837909390794,
        0.5409849234648693,
        0.5521916393539001,
        0.5679801011829239,
        0.5875649213559903,
        0.6100772943965505,
        0.6346311493567033,
        0.6603760074541768,
        0.6865376455084675,
        0.7124491832845173,
        0.7375758133034347,
        0.7615360640689555,
        0.784121267803452,
        0.8053129701516621,
        0.8252957759575297,
        0.8444612039440458,
        0.86339726655893,
        0.8828593260447778,
        0.9037205397180315,
        0.9269045223816066,
        0.9533076903644085,
        0.9837226246889178,
        1.018775207809335,
        1.0588863170177146,
        1.1042636008738816,
        1.1549216144062638,
        1.2107215217592027,
        1.2714170420110614,
        1.3366929580158116,
        1.4061865696741923,
        1.4794895931389887,
        1.5561356493685284,
        1.6355838314610945,
        1.7172098157328937,
        1.8003120095293608,
        1.8841324468256418,
        1.9678830475359486,
        2.0507605561907966,
        2.1319308250118147,
        2.2104669584581324,
        2.2852365255449018,
        2.3547491251316807,
        2.4169938331089577,
        2.4693118150309907,
        2.5083573757679207,
        2.530196335777736,
        2.530571544795505,
        2.505332958001338,
        2.4509897519785954,
        2.3653038385003146,
        2.247818684778563,
        2.1002136491092284,
        1.926396192057673,
        1.7322894455109955,
        1.5253309900746098,
        1.3137561991678522,
        1.1057817537620536,
        0
    ],
    5:[
        0.02808235396750209,
        0.03130406716966472,
        0.03458669306202234,
        0.03811121648929286,
        0.04213683438406029,
        0.04697368264167391,
        0.05294224330996478,
        0.06032649310981076,
        0.06933011868508003,
        0.08004528410518715,
        0.09244118258611757,
        0.10637531772111303,
        0.1216252047213251,
        0.13793343861951905,
        0.15505625201532759,
        0.17280558512896838,
        0.19107717665533378,
        0.209861205929762,
        0.22923605453803673,
        0.24934848721901607,
        0.27038444597153135,
        0.29253417225655117,
        0.31595466946417147,
        0.3407327222927111,
        0.3668531677697213,
        0.39417908973799128,
        0.4224514253914782,
        0.4513134281194212,
        0.4803598416025655,
        0.5092025662095108,
        0.5375367876286646,
        0.565187471507988,
        0.5921185134030484,
        0.6183961976850577,
        0.6441127009082317,
        0.6692896838640076,
        0.6937914105099258,
        0.7172774906780125,
        0.7392163119737532,
        0.7589638868588986,
        0.7758941264023204,
        0.7895512331723325,
        0.7997876298590259,
        0.8068536463301156,
        0.8114169806662089,
        0.8145070325264926,
        0.8173965975751465,
        0.8214464368834282,
        0.827943872094099,
        0.8379641311057253,
        0.8522742805771644,
        0.8712873901835165,
        0.8950627442040366,
        0.9233395730433306,
        0.9555887316780519,
        0.9910691343771179,
        1.0288820746200054,
        1.068024150894882,
        1.1074453096030297,
        1.1461199833899956,
        1.183135401379094,
        1.2177928746426646,
        1.2497081459359483,
        1.2788896845312779,
        1.30577256854939,
        1.3311917916777308,
        1.3562910985886277,
        1.3823779762155864,
        1.4107474474909037,
        1.4425031538031308,
        1.4784028281443747,
        1.518748501615351,
        1.563333193471848,
        1.6114486102772079,
        1.6619536468631556,
        1.7133998625952063,
        1.7642049034423287,
        1.8128561838532254,
        1.8581158414928243,
        1.8991879054559487,
        1.9358052463238976,
        1.9682016251552146,
        1.996953937890436,
        2.022708002652572,
        2.0458309850209956,
        2.066056902742699,
        2.082202429116139,
        2.092025584803707,
        2.0922804485863888,
        2.0789897723397705,
        2.04791883616372,
        1.995193539090077,
        1.917970264813587,
        1.8150422083628118,
        1.6872641237993132,
        1.5376996764391316,
        1.3714419841822084,
        1.1951204818337405,
        1.016171610474465,
        0.8420002391293276,
        0
    ],
    10:[
        0.003865171975525856,
        0.0060279978389134948,
        0.00913123329547628,
        0.01344158926403559,
        0.019238890591951928,
        0.026791366142114898,
        0.03632528427364341,
        0.04799272495220425,
        0.06184254817207012,
        0.07779990065593108,
        0.09565865376049429,
        0.11508911713141973,
        0.135660744570603,
        0.1568770932439888,
        0.17821872128595374,
        0.19918938057246425,
        0.2193616404613921,
        0.23841935861480574,
        0.25619538406110556,
        0.2727028909831928,
        0.2881576537795065,
        0.3029868762974114,
        0.31781888186581566,
        0.3334482039337432,
        0.350773207858074,
        0.3707083856575504,
        0.3940799922525946,
        0.42151996900151197,
        0.4533769554834233,
        0.4896627488016653,
        0.5300470117630248,
        0.5739031236963833,
        0.6203962045445109,
        0.6685939702671341,
        0.7175756048320925,
        0.7665153802888536,
        0.81472621911547,
        0.8616612658219468,
        0.906884638373426,
        0.9500314486459895,
        0.9907788790975876,
        1.028844082006557,
        1.064013185230173,
        1.096192924562702,
        1.1254669159827618,
        1.1521355511931369,
        1.1767227190729797,
        1.1999421939334496,
        1.2226279931582165,
        1.2456423725029589,
        1.2697795921292628,
        1.2956823348279385,
        1.3237818987643116,
        1.354265547454067,
        1.3870674617157178,
        1.4218756811817566,
        1.4581470912009614,
        1.4951254823510197,
        1.5318626221020757,
        1.567247300972746,
        1.6000506127103427,
        1.6289958664114708,
        1.652857841348291,
        1.6705889700185404,
        1.6814610103254917,
        1.6852022966519036,
        1.6821054855658578,
        1.673080995763246,
        1.6596378467338946,
        1.6437852837535814,
        1.6278627920635787,
        1.614319360801968,
        1.6054718551192764,
        1.60327491178213,
        1.6091303889032247,
        1.6237543472975849,
        1.647106552969727,
        1.6783751507449403,
        1.7160010713689249,
        1.7577255421344782,
        1.800650483942586,
        1.8413137124856305,
        1.875794300020411,
        1.8998723013665562,
        1.909265894267718,
        1.8999551941353164,
        1.8685773906115284,
        1.812848866703509,
        1.7319460038638884,
        1.6267666856649415,
        1.5000047204715057,
        1.3559991531707032,
        1.2003630745734757,
        1.0394410780627728,
        0.8796791492286107,
        0.7270066203701373,
        0.5863235343293017,
        0.46116119359280596,
        0.353546508498551,
        0.2640618229183768,
        0
    ]
}
RISK_THRESHOLD = {
    2: [0.5818, 0.9123],
    5: [0.555, 0.8654],
    10: [0.4986, 0.7934]
}

NAME_TO_DISPLAY_NAME = {
    'cholesHDL': 'HbA1c in Blood mmol/L',
    'choles': "Cholesterol in Serum or Plasma mmol/L",
    'creatinine': "Creatinine Renal Clearance mmol/L",
    'fastingGlucose': "Fasting Glucose in Serum or Plasma mmol/L",
    'triglyceride': "Triglyceride in Serum or Plasma mmol/L",
    'cholesLDL_1': "Cholesterol in LDL in Serum or Plasma by Calculation mmol/L",
    'potassiumSerumOrPlasma': "Potassium in Serum or Plasma mmol/L",
    'HBA1C': 'HbA1c in Blood %'
}
service_functions = [
	{
		"name": "analysis",
		"description": "calculate the risk level of diabetes onset, if user input tests result",
		"parameters": {
			"type": "object",
			"properties": {
				"labtest_date": {
                    "type": "string",
                    "description": """blood test date in format yyyy-mm-dd, if not given please specify to the earliest valid date for the given date"""
                },
                "cholesHDL":  {
                    "type": "number",
                    "description": "blood test result for Cholesterol in HDL in Serum or Plasma in mmol/L"
                },
                "choles": {
                    "type": "number",
                    "description": "blood test result for Cholesterol in Serum or Plasma in mmol/L"
                },
                "creatinine": {
                    "type": "number",
                    "description": "blood test for Creatinine Renal Clearance in mmol/L"
                },
                "fastingGlucose": {
                    "type": "number",
                    "description": "blood test result for Fasting Glucose in Serum or Plasma in mmol/L"
                },
                "triglyceride": {
                    "type": "number",
                    "description": "blood test result for Triglyceride in Serum or Plasma in mmol/L"
                },
                "potassiumSerumOrPlasma": {
                    "type": "number",
                    "description": "blood test result for Potassium in Serum or Plasma in mmol/L"
                },
                "HBA1C": {
                    "type": "number",
                    "description": "blood test result for HbA1c in Blood in %"
                },
                "time_spec": {
                    "type": "number",
                    "description": "the length of time period about which the use want to know the diabetes onset risk"
                }
			}
		}
	},
    {
        "name": "advise",
        "description": "provide health advise on weight management, diet plan and medical situation; provide exercise plan, return the basic personal information if the user mentioned the personal data like weight, smoking status, drinking history and diabetes onset risk，etc.",
        "parameters": {
            "type": "object",
            "properties": {
            }
        }
    },
    {
        "name": "check",
        "description": "retrieve the user previous analysis result from database based on a give test date.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_date": {
                    "type": "string",
                    "description": """blood test date in format yyyy-mm-dd, if it is not given please return undefined"""
                }
            }
        }
    },
    {
        "name": "tutorial",
        "description": "give a tutorial and introduction of the application to the user",
        "parameters": {
            "type": "object",
            "properties": {

            }
        }
    },
    {
        'name': 'margin',
        'description': 'calculate the risk reduction for the improvement of the tests result',
        'parameters': {
            'type': 'object',
            "properties": {
				"test_date": {
                    "type": "string",
                    "description": """the test date for the test of the evaluation case in format yyyy-mm-dd, if not given please specify to the earliest valid date for the given date"""
                },
                "cholesHDL":  {
                    "type": "number",
                    "description": "reduction of blood test result for Cholesterol in HDL in Serum or Plasma in mmol/L"
                },
                "choles": {
                    "type": "number",
                    "description": "reduction of blood test result for Cholesterol in Serum or Plasma in mmol/L"
                },
                "creatinine": {
                    "type": "number",
                    "description": "reduction of blood test for Creatinine Renal Clearance in mmol/L"
                },
                "fastingGlucose": {
                    "type": "number",
                    "description": "reduction of blood test result for Fasting Glucose in Serum or Plasma in mmol/L"
                },
                "triglyceride": {
                    "type": "number",
                    "description": "reduction of blood test result for Triglyceride in Serum or Plasma in mmol/L"
                },
                "potassiumSerumOrPlasma": {
                    "type": "number",
                    "description": "reduction of blood test result for Potassium in Serum or Plasma in mmol/L"
                },
                "HBA1C": {
                    "type": "number",
                    "description": "reduction of blood test result for HbA1c in Blood in %"
                }
        }
        }
    }
]


def analysis(
    q: Query,
    current_session: Session,
    labtest_date: Union[str, None] = None,
    cholesHDL: Union[float, None] = None,
    choles: Union[float, None] = None,
    creatinine: Union[float, None] = None,
    fastingGlucose: Union[float, None] = None,
    triglyceride: Union[float, None] = None,
    cholesLDL_1: Union[float, None] = None,
    potassiumSerumOrPlasma: Union[float, None] = None,
    HBA1C: Union[float, None] = None,
    time_spec: int = 2
) -> str:
    tail = ""
    if HBA1C != None and HBA1C > 6.4:
        return "Notice: your HbA1c level has exceeded the normal range, under this circumstance, a risk evaluation is not necessary. Also, a medical appointment with doctor is strongly recommended."
    if labtest_date == None:
        return "Please provide the test date, otherwise I cannot evaluate the validity of the risk."
    if fastingGlucose != None and fastingGlucose > 5.6:
        tail = f" Warning: Your fasting glucose level is above the normal range, please consult your doctor."
    if labtest_date != None:
        since = datetime.strptime(labtest_date, "%Y-%m-%d")
        interval = datetime.now() - since
        days = interval.days
        if days < 0:
            return "The test date is not valid"
        if days > 6 * 30.5:
            return "It has been a while since the test, you need to provide a test that is less than six months old."
    db = SessionLocal()
    upload_body = UploadBody(
        labtest_date=labtest_date,
        cholesHDL=cholesHDL,
        choles=choles,
        creatinine=creatinine,
        fastingGlucose=fastingGlucose,
        triglyceride=triglyceride,
        cholesLDL_1=cholesLDL_1,
        potassiumSerumOrPlasma=potassiumSerumOrPlasma,
        HBA1C=HBA1C,
        time_spec=time_spec
    )
    print(upload_body.dict())
    db_case = Case(**upload_body.dict(), user_id=current_session.user.user_id)
    db_case = create_case(db, db_case)

    case_id = db_case.case_id
    db_case: Case = get_case_by_id(db, case_id)
    if db_case == None:
        raise HTTPException(status_code=406, detail="please upload your test result first")
    re = RiskEngine(case=db_case)
    result, score = re()
    db_case.analysis_result = result
    db_case.score = score
    # write to database
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    return "Your risk level of developing diabetes within the " + str(time_spec) + " year is: " + result + "." + tail

def advise(q: Query, current_session: Session) -> str:
    enquiry = q.enquiry
    db = SessionLocal()
    # db_case = get_latest_case(db, user_id=current_session.user_id)
    # try:
    #     system_setting = assemble(user=current_session.user, case=db_case)
    # except Exception as e:
    #     print(e)
    #     return enquiry
    return enquiry

def check(q: Query, current_session: Session, test_date: Union[str, None]=None) -> str:

    if test_date == None:
        test_date = str(datetime.datetime.now().date())
    db = SessionLocal()
    db_case = get_case_by_closest_date(db, test_date, user_id=current_session.user_id)
    test_results = "Test result :"
    for name in NAME_TO_DISPLAY_NAME.keys():
        if getattr(db_case, name) != None:
            test_results += f"{NAME_TO_DISPLAY_NAME[name]}: {getattr(db_case, name)}\n"
    prompt: str = '''
    According to this evaluation result, your risk score is {score}, risk level is {level}
    '''\
    .format(score=db_case.score, level=db_case.analysis_result)
    return test_results + prompt


def tutorial(q: Query, current_session: Session) -> str:
    return '''
    To evaluate your diabetes onset risk, you can input your blood test results in the following items to evaluate\
        you risk level in a two-year five-year and ten-year period:
        
        HbA1c in Blood %
        Fasting Glucose in Serum or Plasma mmol/L
        Cholesterol in HDL in Serum or Plasma mmol/L
        Cholesterol in Serum or Plasma mmol/L
        Cholesterol in LDL in Serum or Plasma by Calculation mmol/L
        Creatinine Renal Clearance mmol/L
        Triglyceride in Serum or Plasma mmol/L
        Potassium in Serum or Plasma mmol/L
        Latest Lab Test Date
    '''

'''
        Dia-LOG system is an evaluation tool for diabetes onset based on the SOTA machine learning algorithms developed by Dr.Yang Lin's research team from Hong Kong Polytechnic University.
        
        To evaluate your diabetes onset risk, you can input your blood test results in the following items to evaluate\
        you risk level in a two-year five-year and ten-year period:
        
        HbA1c in Blood %
        Fasting Glucose in Serum or Plasma mmol/L
        Cholesterol in HDL in Serum or Plasma mmol/L
        Cholesterol in Serum or Plasma mmol/L
        Cholesterol in LDL in Serum or Plasma by Calculation mmol/L
        Creatinine Renal Clearance mmol/L
        Triglyceride in Serum or Plasma mmol/L
        Potassium in Serum or Plasma mmol/L
        Latest Lab Test Date
        
        Note you don't need to fill out all the required tests field, you can leave it blank if you don't know
        the result.
        For example, you can input:
        I want to know my diabetes progression risk within five years, my blood test of HbA1c is 4.5%, my Cholesterol in 4.65 mmol/L, the test date is Sep 9th, 2023.
        
        After the evaluation, you can also enquiry your result searched by date.
        For example, you can ask:
        What is my evaluation result for the test on September 9th, 2023?
        
        You can check your overall health status and ask for health advice.
        For example, you can ask:
        How is my health status, do I need to book a medical appointment with doctor?
        Our system will automatically analyze the your health status based on your personal health status and provide you appropriate information.
        
        A sensitive check is also available, you can check how much risk will be reduced if you improve your health status.
        For example, you can ask:
        If I lower my HbA1c level for 1%, how much improvement can be made on my health status, the test is Sep 9th, 2023
         
    '''

def margin(
    q: Query,
    current_session: Session,
    cholesHDL: float = 0.0,
    choles: float = 0.0,
    creatinine: float = 0.0,
    fastingGlucose: float = 0.0,
    triglyceride: float = 0.0,
    cholesLDL_1: float = 0.0,
    potassiumSerumOrPlasma: float = 0.0,
    HBA1C: float = 0.0,
    test_date: str = None,
) -> str:
    if test_date == None:
        return "Please give me the test date."
    step: Step = Step(
        cholesHDL=abs(cholesHDL),
        choles = abs(choles),
        creatinine= abs(creatinine),
        fastingGlucose= abs(fastingGlucose),
        triglyceride= abs(triglyceride),
        cholesLDL_1= abs(cholesLDL_1),
        potassiumSerumOrPlasma= abs(potassiumSerumOrPlasma),
        HBA1C= abs(HBA1C)
    )
    db = SessionLocal()
    db_case = get_case_by_closest_date(db, test_date, current_session.user_id)
    print(db_case.labtest_date)
    margin = Margin(case = db_case, step=step)
    mr = margin.get_margin()
    reduced = -1 * mr / db_case.score
    return f"Your risk is lowered by {reduced:.00%} if you make the changes."

registration_list = {
    "prompt_functions": {
        "advise": advise
    },
    "direct_functions": {
        "analysis": analysis,
        "tutorial": tutorial,
        "check": check,
        "margin": margin
    }
}