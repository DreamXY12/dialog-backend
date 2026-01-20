import boto3

__session = boto3.Session()
__parameter_store = __session.client('ssm', region_name="ap-southeast-1")

def get_parameter(config_type, key):
    name = f"/dialog/{config_type}/{key}"
     #测试用
    #print("所访问的资源路径:",name)
    try:
        # Retrieve the parameter
        response = __parameter_store.get_parameter(Name=name, WithDecryption=True)
       
        #print("获取到的结果",response['Parameter']['Value'])
        return response['Parameter']['Value']
    except __parameter_store.exceptions.ParameterNotFound:
        print(f"Parameter {name} not found.")
    except Exception as e:
        print(f"Error retrieving parameter: {e}")
        




