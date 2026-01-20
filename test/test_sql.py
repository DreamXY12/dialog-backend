from sqlalchemy import create_engine, text
from sqlalchemy import URL
from sqlalchemy.orm import sessionmaker
import boto3

__session = boto3.Session()
__parameter_store = __session.client('ssm', region_name="ap-southeast-1")

def get_parameter(config_type, key):
    name = f"/dialog/{config_type}/{key}"
    try:
        # Retrieve the parameter
        response = __parameter_store.get_parameter(Name=name, WithDecryption=True)
        return response['Parameter']['Value']
    except __parameter_store.exceptions.ParameterNotFound:
        print(f"Parameter {name} not found.")
    except Exception as e:
        print(f"Error retrieving parameter: {e}")
        


# Retrieve database connection parameters
USERNAME = get_parameter("rdb", "username")
PASSWORD = get_parameter("rdb", "password")
HOST = get_parameter("rdb", "host")
DATABASE = get_parameter("rdb", "database")

# Create the database URL
SQLALCHEMY_DATABASE_URL = URL.create(
    "mysql+mysqlconnector",
    username=USERNAME,
    password=PASSWORD,
    host=HOST,
    database=DATABASE
)

# Create the SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_database_connection():
    try:
        # Create a new session
        with SessionLocal() as session:
            # Execute a simple query to test connectivity
            result = session.execute(text("SELECT 1"))
            if result.scalar() == 1:
                print("Successfully connected to the database!")
            else:
                print("Failed to execute test query.")
    except Exception as e:
        print(f"An error occurred: {e}")

# Test the database connection
test_database_connection()