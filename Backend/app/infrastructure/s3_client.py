import time
import boto3
from botocore.exceptions import EndpointConnectionError, ClientError
from core.config import settings 

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    region_name="us-east-1",  
)

BUCKET_NAME = "images"

def init_s3():
    """Создать бакет с повторными попытками при старте."""
    max_retries = 10
    for attempt in range(max_retries):
        try:
            s3_client.create_bucket(Bucket=BUCKET_NAME)
            print(f"Bucket '{BUCKET_NAME}' ready.")
            return
        except s3_client.exceptions.BucketAlreadyOwnedByYou:
            print(f"Bucket '{BUCKET_NAME}' already exists.")
            return
        except (EndpointConnectionError, ClientError) as e:
            if attempt < max_retries - 1:
                print(f"Waiting for MinIO... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"Failed to connect to S3 after {max_retries} attempts: {e}")
                raise
        except Exception as e:
            print(f"Error connecting to S3: {e}")
            raise