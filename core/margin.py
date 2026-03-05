from typing import Union
# 尝试导入 TensorFlow，如果失败则使用模拟实现

try:
    import tensorflow as tf
    has_tensorflow = True
except ImportError:
    has_tensorflow = False
    print("Warning: TensorFlow not available, using mock implementation")

from sql.models import Case
from schema.case import Step
from core.risk_engine import RiskEngine
import copy

class Margin():

    def __init__(self, case: Case, step: Step) -> None:
        '''
        This class serves as the main operator for calculating the margin effect
        caused by the improvement of the test result

        Due to straightforward data input, we just simulate the result based on the improved
        result

        Args:
            case: the target case, implemented by sql.models.Case
            step: a dictionary for the minimal change for each input variable
        '''
        self.case = case
        self.step = step.dict()
        self.score = case.score
        print("the original score is %d".format(self.score))

    def get_margin(self) -> Union[float, None]:
        case = copy.deepcopy(self.case)
        for input_variable in self.step.keys():
            try:
                variable_step = self.step[input_variable]
            except ValueError as e:
                raise ValueError("please make sure the input value is in the given variable list")

            value = getattr(case, input_variable)
            # if the value is none, then we ignore the variable effect, so we return None
            if value == None:
                continue
        
            try:
                assert value - variable_step >= 0
                setattr(case, input_variable, value-variable_step)
            except AssertionError:
                print(f"Warning: Cannot decrease {input_variable} below zero, skipping")
        
        _, after_score = RiskEngine(case)()
        return after_score - self.score
        


        