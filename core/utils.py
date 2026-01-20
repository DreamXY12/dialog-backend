from sql.models import User, Case


def assemble(user: User, case: Case = None) -> str:
    '''
    assemble the prompts and enquiry into a sentence.
    '''
    bmi = user.weight * 10000 / (user.height * user.height)
    smoking = ""
    height = user.height
    weight = user.weight
    drinking = ""
    family_history = ""
    if user.smoking_status:
        smoking = "I smoke" if user.smoking_status == "Yes" else "I do not smoke."
    if user.drinking_history:
        drinking = f"I drink {user.drinking_history}"
    if user.family_history:
        family_history = "I have family history of diabetes, "
    conclusion = "I have " + case.analysis_result if case!= None else ""+ " on diabetes, "
    background = f"My BMI is {bmi}, my height is {height}, my weight is {weight}" + smoking + drinking + family_history + "and "
    return ". Here is my health status: " + background + conclusion + "."