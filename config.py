import boto3
from botocore.config import Config

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

# ==========================
# 生成 S3 预签名 URL（正式token）
# 自动读取你本地的 AWS 配置，不需要密钥代码！
# ==========================
def generate_s3_presigned_url(bucket: str, key: str, expires_in=3600):
    # 🔥 核心：直接用本地已有的 AWS 登录凭证，不需要手动填 AK/SK
    s3 = boto3.client(
        "s3",
        region_name="ap-southeast-1",
        config=Config(signature_version="s3v4")
    )

    # 生成预签名 URL（1小时过期）
    signed_url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": bucket,
            "Key": key
        },
        ExpiresIn=expires_in
    )
    return signed_url




