from core.translate import to_other_language

data = [
    '''Hello!  It's good you're being proactive about your health. Your BMI is within a healthy range, but having a family history of diabetes means staying vigilant is important. 

Focus on maintaining a healthy weight through balanced eating and regular exercise. Talk to your doctor about getting checked for prediabetes or diabetes. 

    '''
    
]

def test_language():
    for d in data:
        print(to_other_language(d, "yue"))
        
test_language()