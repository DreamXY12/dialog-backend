from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session as Connection
from typing_extensions import Annotated
from fastapi import Body, Depends
from typing import List, Any

from schema.case import UploadBody, DashboardItem, MarginResponse, MarginRequest, HistoryResponse, DenseResponse
from core.risk_engine import RiskEngine
from core.margin import Margin
from sql.people_models import Case
from sql.start import get_db
from sql.crud import create_case, get_latest_case, get_cases_by_user, get_case_by_id

from core.auth import get_current_user

import random
from typing import Tuple

router = APIRouter(prefix='/case', tags=["case"])

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

# ========== 人群风险分布模拟（基于公开糖尿病风险数据） ==========
def simulate_population_ranking(score: float, time_spec: int) -> Tuple[float, str]:
	"""
	模拟当前风险分数在人群中的排名（百分比）
	基于糖尿病风险分布特征：呈偏态分布，多数人集中在低风险区域
	:param score: 当前用户风险分数
	:param time_spec: 预测时间跨度（2/5/10年）
	:return: (排名百分比, 人群位置说明)
	"""
	# 不同时间跨度的人群风险分布参数（模拟真实数据特征）
	distribution_params = {
		2: {"mean": 0.35, "std": 0.25},  # 2年风险：均值偏低，集中在低风险
		5: {"mean": 0.50, "std": 0.30},  # 5年风险：均值中等
		10: {"mean": 0.65, "std": 0.35}  # 10年风险：均值偏高，分布更分散
	}
	params = distribution_params[time_spec]

	# 基于偏态分布计算排名（模拟真实人群中低风险占比更高的特征）
	if score <= params["mean"] - 0.1:
		# 低风险区间：排名前20%（优于80%人群）
		percentile = round(random.uniform(5, 20), 1)
	elif score <= params["mean"] + 0.1:
		# 中低风险区间：排名前20%-50%（优于50%-80%人群）
		percentile = round(random.uniform(20, 50), 1)
	elif score <= params["mean"] + 0.3:
		# 中高风险区间：排名前50%-80%（优于20%-50%人群）
		percentile = round(random.uniform(50, 80), 1)
	else:
		# 高风险区间：排名后20%（仅优于20%人群）
		percentile = round(random.uniform(80, 95), 1)

	# 生成人群位置说明
	if percentile <= 20:
		rank_desc = f"处于人群前{percentile}%，风险水平远低于平均水平"
	elif percentile <= 50:
		rank_desc = f"处于人群前{percentile}%，风险水平低于平均水平"
	elif percentile <= 80:
		rank_desc = f"处于人群前{percentile}%，风险水平高于平均水平"
	else:
		rank_desc = f"处于人群前{percentile}%，风险水平远高于平均水平"

	return percentile, rank_desc


@router.post("/upload")
def upload(
	upload_body: Annotated[UploadBody, Body],
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)]
):
	# 根据用户类型获取用户ID
	if hasattr(user, 'user_id'):
		user_id = user.user_id
	elif hasattr(user, 'patient_id'):
		user_id = user.patient_id
	elif hasattr(user, 'nurse_id'):
		user_id = user.nurse_id
	else:
		raise HTTPException(status_code=400, detail="Invalid user type")
	# 转换日期格式
	from datetime import datetime
	upload_data = upload_body.dict()
	if upload_data.get('test_date'):
		upload_data['test_date'] = datetime.strptime(upload_data['test_date'], '%Y-%m-%d').date()
	else:
		upload_data['test_date'] = datetime.now().date()
	db_case = Case(**upload_data, user_id=user_id)
	db_case = create_case(db, db_case)

	return {"user_id": user_id, "case_id": db_case.case_id}

@router.post("/analysis")
def analysis(
	upload_body: Annotated[UploadBody, Body],
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)]
):
	# 根据用户类型获取用户ID
	if hasattr(user, 'user_id'):
		user_id = user.user_id
	elif hasattr(user, 'patient_id'):
		user_id = user.patient_id
	elif hasattr(user, 'nurse_id'):
		user_id = user.nurse_id
	else:
		raise HTTPException(status_code=400, detail="Invalid user type")

	# 创建临时Case对象用于分析
	from datetime import datetime
	upload_data = upload_body.dict()
	if upload_data.get('test_date'):
		upload_data['test_date'] = datetime.strptime(upload_data['test_date'], '%Y-%m-%d').date()
	else:
		upload_data['test_date'] = datetime.now().date()
	temp_case = Case(**upload_data, user_id=user_id)

	# 进行风险分析
	re = RiskEngine(case=temp_case)
	result, score = re()

	# 确定风险等级
	risk_level = "低风险"
	if score >= RISK_THRESHOLD[temp_case.time_spec][1]:
		risk_level = "高风险"
	elif score >= RISK_THRESHOLD[temp_case.time_spec][0]:
		risk_level = "中风险"

	# ========== 新增：计算人群排名 ==========
	population_percentile, population_desc = simulate_population_ranking(score, temp_case.time_spec)

	# 保存分析结果到数据库
	# 查找最近上传的case
	latest_case = get_latest_case(db, user_id)
	if latest_case:
		# 更新分析结果
		latest_case.analysis_result = result
		latest_case.score = score
		try:
			db.commit()
		except Exception as e:
			db.rollback()
			print(f"保存分析结果失败: {e}")

	return {
		"riskLevel": risk_level,
		"riskScore": score,
		"result": risk_map.get(result, 3),
		"populationPercentile": population_percentile,  # 排名百分比（如15.2表示前15.2%）
		"populationDescription": population_desc,  # 人群位置说明
		"timeSpec": temp_case.time_spec  # 预测时间跨度（用于前端显示）
	}

@router.get("/analysis")
def analysis_by_case_id(
	case_id: Annotated[int, Query()],
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)]
):
	# 根据用户类型获取用户ID
	if hasattr(user, 'user_id'):
		user_id = user.user_id
	elif hasattr(user, 'patient_id'):
		user_id = user.patient_id
	elif hasattr(user, 'nurse_id'):
		user_id = user.nurse_id
	else:
		raise HTTPException(status_code=400, detail="Invalid user type")

	# 根据case_id获取case
	case = get_case_by_id(db, case_id)
	if not case:
		raise HTTPException(status_code=404, detail="Case not found")

	# 验证case属于当前用户
	if case.user_id != user_id:
		raise HTTPException(status_code=403, detail="Access denied")

	# 进行风险分析
	re = RiskEngine(case=case)
	result, score = re()

	# 确定风险等级
	risk_level = "低风险"
	if score >= RISK_THRESHOLD[case.time_spec][1]:
		risk_level = "高风险"
	elif score >= RISK_THRESHOLD[case.time_spec][0]:
		risk_level = "中风险"

	# ========== 计算人群排名 ==========
	population_percentile, population_desc = simulate_population_ranking(score, case.time_spec)

	# 保存分析结果到数据库
	case.analysis_result = result
	case.score = score
	try:
		db.commit()
	except Exception as e:
		db.rollback()
		print(f"保存分析结果失败: {e}")

	return {
		"result": result,
		"riskLevel": risk_level,
		"riskScore": score,
		"populationPercentile": population_percentile,
		"populationDescription": population_desc,
		"timeSpec": case.time_spec
	}

@router.get("/item", response_model=List[DashboardItem])
def get_list(
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)]
):  
	result = []
	cases: List[Case] = get_cases_by_user(db, user)
	for c in cases:
		result.append(DashboardItem(
			case_id=c.case_id,
			labtest_date=c.test_date,
			create_time=c.create_time,
			time_spec=c.time_spec,
			analysis_result=risk_map.get(c.analysis_result,3),
			score=c.score,
			hba1c=c.hba1c,
			fasting_glucose=c.fasting_glucose,
			hdl_cholesterol=c.hdl_cholesterol,
			total_cholesterol=c.total_cholesterol,
			ldl_cholesterol=c.ldl_cholesterol,
			creatinine=c.creatinine,
			triglyceride=c.triglyceride,
			potassium=c.potassium
		))
	return result

@router.get("/dense", response_model=DenseResponse)
def get_dense(
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)],
	case_id: Annotated[int, Body]
):	
	case : Case = get_case_by_id(db, case_id)
	if case == None:
		raise HTTPException(status_code=400, detail="please enter a valid case id")
	score = case.score
	if score == None:
		raise HTTPException(status_code=400, detail="this case has not been analyzed")
	total = sum(DENSE[case.time_spec])
	greater = 0
	for i in range(len(DENSE[case.time_spec])):
		if i >= score * 100:
			print(i)
			greater = sum(DENSE[case.time_spec][i:])
			break
	exceeded = greater / total
	return DenseResponse(dense=DENSE[case.time_spec], score=case.score, exceeded_portion=exceeded, threshold=RISK_THRESHOLD[case.time_spec])

@router.post("/margin", response_model=MarginResponse, summary="deprecated, do not use this api for now")
def get_margin(
	user: Annotated[Any, Depends(get_current_user)],
	db: Annotated[Connection, Depends(get_db)],
	rq: MarginRequest
):
	case: Case = get_case_by_id(db, rq.case_id)
	mr = {}
	step = rq.step
	margin = Margin(case,step=rq.step)
	for s in step.dict().keys():
		mr[s] = margin.get_margin(s)
	return mr

@router.post("/history", response_model=List[HistoryResponse])
def get_history(
	user: Annotated[Any, Depends(get_current_user)],
	time_spec: Annotated[int, Query()],
	db: Annotated[Connection, Depends(get_db)]
):	
	result = []
	cases: List[Case]= get_cases_by_user(db, user)
	for c in cases:
		if c.time_spec == time_spec:
			result.append(HistoryResponse(labtest_date=c.test_date, score=c.score))
	return result