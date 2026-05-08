import os
import time
import boto3
from botocore.exceptions import EndpointConnectionError, ClientError

s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY", "admin"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY", "password123"),
    region_name="us-east-1",  # MinIO требует любой регион
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
