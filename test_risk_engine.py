from core.risk_engine import RiskEngine
from sql.models import Case

# 创建一个测试用的 Case 对象
class TestCase:
    def __init__(self):
        self.hba1c = 5.6
        self.fasting_glucose = 5.2
        self.hdl_cholesterol = 1.2
        self.total_cholesterol = 4.5
        self.ldl_cholesterol = 2.8
        self.creatinine = 70
        self.triglyceride = 1.5
        self.potassium = 4.0
        self.time_spec = 2

# 测试 RiskEngine
def test_risk_engine():
    print("测试 RiskEngine...")
    print("=" * 50)
    
    # 创建测试用例
    case = TestCase()
    
    try:
        # 实例化 RiskEngine
        engine = RiskEngine(case)
        # 调用预测方法
        risk_level, risk_score = engine()
        print(f"风险等级: {risk_level}")
        print(f"风险分数: {risk_score}")
        print("测试成功！没有出现 'list' object has no attribute 'item' 错误")
    except Exception as e:
        print(f"测试失败: {e}")
    
    print("=" * 50)

if __name__ == "__main__":
    test_risk_engine()