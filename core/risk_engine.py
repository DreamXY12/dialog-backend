from typing import Any
import tensorflow as tf
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
    'cholesHDL',
    'choles',
    'creatinine',
    'fastingGlucose',
    'triglyceride',
    'cholesLDL_1',
    'potassiumSerumOrPlasma',
    'HBA1C'
]

VALID_TESTS = {
    2: ['cholesHDL','choles','creatinine','fastingGlucose','triglyceride','cholesLDL_1','potassiumSerumOrPlasma','HBA1C'],
    5: ['cholesHDL','choles','creatinine','fastingGlucose','triglyceride','cholesLDL_1','potassiumSerumOrPlasma','HBA1C'],
    10: ["choles", "creatinine", "fastingGlucose", "triglyceride", "potassiumSerumOrPlasma", "HBA1C"]
}

FILL_VALUE = {
    2:[0.115667, 0.039928, 0.291326, 0.192848, 0.222447, 0.048000, 0.017478, 0.069707],
    5:[0.123032, 0.030336, 0.251610, 0.171564, 0.221507, 0.047730, 0.007008, -0.117419],
    10:[0.047541, 0.299969, 0.209437, 0.284772, -0.007758, 0.075904]
}

VALID_FEATURES = {
    2: ['creatinine', 'fastingGlucose', 'HBA1C', 'age'],
    5: [ 'cholesHDL', 'creatinine', 'fastingGlucose','triglyceride','cholesLDL_1','potassiumSerumOrPlasma','HBA1C', 'age', 'sex'],
    10: ['creatinine', 'fastingGlucose', 'triglyceride', 'potassiumSerumOrPlasma', 'HBA1C', 'age', 'sex']
}

RISK_THRESHOLD = {
    2: [0.5818, 0.7964, 0.9123],
    5: [0.555,0.7369, 0.8654],
    10: [0.4986, 0.6369, 0.7934]
}

class RiskEngine():

    def __init__(self, case: Case) -> None:
        self.time_spec = case.time_spec
        
        if not os.path.exists("checkpoint"):
            bucket_name = get_parameter('s3', 'bucket_name')
            s3_prefix = get_parameter('s3', 's3_prefix')
            local_dir = 'checkpoint'    
            download_s3_folder(bucket_name, s3_prefix, local_dir)
        
        # Local temporary directory
        local_dir = tempfile.mkdtemp()
        
        model_path = os.path.join(CHECK_POINT_PATH, f"spec-{self.time_spec}", "weighted_model")
        scaler_path = os.path.join(CHECK_POINT_PATH, f"spec-{self.time_spec}", "scaler.pkl")
        self.model: tf.keras.Model = tf.keras.models.load_model(model_path)
        self.scaler = pickle.load(open(scaler_path, 'rb'))
        self.case: Case = case
        self.user = self.case.user
        self.features = VALID_FEATURES[self.time_spec]
        self.valid_tests = VALID_TESTS[self.time_spec]
        self.risk_threshold = RISK_THRESHOLD[self.time_spec]
        self.fill_value = FILL_VALUE[self.time_spec]
        self.fill_dict = {test: value for test, value in zip(self.valid_tests, self.fill_value)}
        
    def __call__(self) -> tuple:
        x = self.__to_df(self.case)
        tf.random.set_seed(42)
        # preprocess tests
        x = x[self.valid_tests]
        # normalize the data
        x_scaled = pd.DataFrame(self.scaler.transform(x), columns=self.valid_tests)

        # add the age field
        # time_1 = datetime.strptime(self.user.date_of_birth, "%Y-%m-%d")
        time_1 = datetime.combine(self.user.date_of_birth, datetime.min.time())
        age = ((datetime.now() - time_1).days)/ 365.25
        x_scaled["age"] = age
        # map user gender
        x_scaled["sex"] = int(self.user.sex == "male")
        # select features
        features = VALID_FEATURES[self.time_spec]
        x_input = x_scaled[features]
        x_filled = x_input.fillna(self.fill_dict)
        print("the input array is:\n", x_filled)
        # make prediction
        result = self.model.predict(x_filled.to_numpy())[0][0].item()
        return self._get_risk_level(result), result

    def __to_df(self, case: Case) -> pd.DataFrame:
        '''
        convert the each case to a data frame
        '''
        feature = {}
        for name in TESTS_NAME:
            feature[name] = [case.__dict__[name]]
        feature_df = pd.DataFrame(feature)
        return pd.DataFrame(feature_df)
    
    
    def _get_risk_level(self, result: float) -> str:
        '''determine the risk level based on time spectrum and model prediction'''
        print("result is ", result)
        assert result <= 1 and result >= 0
        if result < self.risk_threshold[0]:
            return "low risk"
        # if result < self.risk_threshold[1]:
        #     return "likely"
        if result < self.risk_threshold[2]:
            return "medium risk"
        else:
            return "high risk"
    
    