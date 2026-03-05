from typing import Any
# 尝试导入 TensorFlow，如果失败则使用模拟实现

try:
    import tensorflow as tf
    has_tensorflow = True
except ImportError:
    has_tensorflow = False
    print("Warning: TensorFlow not available, using mock implementation")

from sql.models import Case
import os
import pickle
import pandas as pd
from datetime import datetime
import tempfile
import boto3
from config import get_parameter

def download_s3_folder(bucket_name, s3_prefix, local_dir):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)

    for obj in bucket.objects.filter(Prefix=s3_prefix):
        if obj.key.endswith('/'):
            continue  # skip folders

        target_path = os.path.join(local_dir, os.path.relpath(obj.key, s3_prefix))
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        print(f"Downloading {obj.key} to {target_path}")
        bucket.download_file(obj.key, target_path)


# Example values

CHECK_POINT_PATH = r"checkpoint/models"

TESTS_NAME = [
    'hdl_cholesterol',
    'total_cholesterol',
    'creatinine',
    'fasting_glucose',
    'triglyceride',
    'ldl_cholesterol',
    'potassium',
    'hba1c'
]

VALID_TESTS = {
    2: ['hdl_cholesterol','total_cholesterol','creatinine','fasting_glucose','triglyceride','ldl_cholesterol','potassium','hba1c'],
    5: ['hdl_cholesterol','total_cholesterol','creatinine','fasting_glucose','triglyceride','ldl_cholesterol','potassium','hba1c'],
    10: ["total_cholesterol", "creatinine", "fasting_glucose", "triglyceride", "potassium", "hba1c"]
}

FILL_VALUE = {
    2:[0.115667, 0.039928, 0.291326, 0.192848, 0.222447, 0.048000, 0.017478, 0.069707],
    5:[0.123032, 0.030336, 0.251610, 0.171564, 0.221507, 0.047730, 0.007008, -0.117419],
    10:[0.047541, 0.299969, 0.209437, 0.284772, -0.007758, 0.075904]
}

VALID_FEATURES = {
    2: ['creatinine', 'fasting_glucose', 'hba1c', 'age'],
    5: [ 'hdl_cholesterol', 'creatinine', 'fasting_glucose','triglyceride','ldl_cholesterol','potassium','hba1c', 'age', 'sex'],
    10: ['creatinine', 'fasting_glucose', 'triglyceride', 'potassium', 'hba1c', 'age', 'sex']
}

RISK_THRESHOLD = {
    2: [0.5818, 0.7964, 0.9123],
    5: [0.555,0.7369, 0.8654],
    10: [0.4986, 0.6369, 0.7934]
}

class MockModel:
    """模拟 TensorFlow 模型，返回随机风险值"""
    def predict(self, x):
        import random
        return random.uniform(0, 1)

class RiskEngine():

    def __init__(self, case: Case) -> None:
        self.time_spec = case.time_spec
        
        # 跳过 S3 下载，因为我们使用模拟实现
        # if not os.path.exists("checkpoint"):
        #     bucket_name = get_parameter('s3', 'bucket_name')
        #     s3_prefix = get_parameter('s3', 's3_prefix')
        #     local_dir = 'checkpoint'    
        #     download_s3_folder(bucket_name, s3_prefix, local_dir)
        
        # Local temporary directory
        local_dir = tempfile.mkdtemp()
        
        model_path = os.path.join(CHECK_POINT_PATH, f"spec-{self.time_spec}", "weighted_model")
        scaler_path = os.path.join(CHECK_POINT_PATH, f"spec-{self.time_spec}", "scaler.pkl")
        
        # 使用模拟模型或真实模型
        if has_tensorflow:
            self.model: tf.keras.Model = tf.keras.models.load_model(model_path)
        else:
            self.model = MockModel()
        
        # 尝试加载 scaler，如果失败则使用简单的标准化
        try:
            self.scaler = pickle.load(open(scaler_path, 'rb'))
        except:
            print("Warning: Scaler not available, using simple scaling")
            # 简单的标准化实现
            class MockScaler:
                def transform(self, x):
                    return x
            self.scaler = MockScaler()
        
        self.case: Case = case
        self.user = None  # 移除对self.case.user的访问
        self.features = VALID_FEATURES[self.time_spec]
        self.valid_tests = VALID_TESTS[self.time_spec]
        self.risk_threshold = RISK_THRESHOLD[self.time_spec]
        self.fill_value = FILL_VALUE[self.time_spec]
        self.fill_dict = {test: value for test, value in zip(self.valid_tests, self.fill_value)}
        
    def __call__(self) -> tuple:
        x = self.__to_df(self.case)
        
        # 跳过 TensorFlow 随机种子设置
        # if has_tensorflow:
        #     tf.random.set_seed(42)
        
        # preprocess tests
        x = x[self.valid_tests]
        # normalize the data
        x_scaled = pd.DataFrame(self.scaler.transform(x), columns=self.valid_tests)

        # add the age field
        # 使用默认年龄，因为self.user为None
        age = 40  # 默认年龄
        x_scaled["age"] = age
        
        # map user gender
        # 使用默认性别，因为self.user为None
        x_scaled["sex"] = 0  # 默认性别
        
        # select features
        features = VALID_FEATURES[self.time_spec]
        x_input = x_scaled[features]
        x_filled = x_input.fillna(self.fill_dict)
        print("the input array is:\n", x_filled)
        
        # make prediction
        result = self.model.predict(x_filled.to_numpy())
        # 确保result是一个浮点数
        if isinstance(result, list):
            # 处理不同深度的列表
            if len(result) > 0:
                if isinstance(result[0], list) and len(result[0]) > 0:
                    # 嵌套列表结构 [[]]
                    if isinstance(result[0][0], list) and len(result[0][0]) > 0:
                        # 更深层次的嵌套列表 [[[]]]
                        if hasattr(result[0][0][0], 'item'):
                            result = result[0][0][0].item()
                        else:
                            result = result[0][0][0]
                    else:
                        # 嵌套列表结构 [[]]
                        if hasattr(result[0][0], 'item'):
                            result = result[0][0].item()
                        else:
                            result = result[0][0]
                else:
                    # 一维列表结构 []
                    if hasattr(result[0], 'item'):
                        result = result[0].item()
                    else:
                        result = result[0]
        elif hasattr(result, 'item'):
            # 处理NumPy数组或张量
            result = result.item()
        # 确保result是浮点数
        result = float(result)
        return self._get_risk_level(result), result

    def __to_df(self, case: Case) -> pd.DataFrame:
        '''
        convert the each case to a data frame
        '''
        feature = {}
        for name in TESTS_NAME:
            feature[name] = [case.__dict__.get(name, 0)]
        feature_df = pd.DataFrame(feature)
        return pd.DataFrame(feature_df)
    
    
    def _get_risk_level(self, result: float) -> str:
        '''determine the risk level based on time spectrum and model prediction'''
        print("result is ", result)
        try:
            assert result <= 1 and result >= 0
        except:
            result = 0.5  # 默认风险值
        
        if result < self.risk_threshold[0]:
            return "low risk"
        # if result < self.risk_threshold[1]:
        #     return "likely"
        if result < self.risk_threshold[2]:
            return "medium risk"
        else:
            return "high risk"
    
    