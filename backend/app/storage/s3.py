"""PROVOK — AWS S3 Storage Client."""
import logging
import uuid
import boto3
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO

from backend.app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class S3StorageManager:
    """Manager for AWS S3 operations."""
    
    def __init__(self):
        # Initialize boto3 client. It uses environment variables or explicit settings.
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
            self.bucket_name = settings.s3_bucket_name
            self.prefix = settings.s3_upload_prefix
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None

    def upload_file(self, file_obj: BinaryIO, filename: str, content_type: str = "image/jpeg") -> Optional[str]:
        """
        Upload a file to S3 and return the public URL.
        """
        if not self.s3_client:
            logger.warning("S3 Client not initialized. Returning dummy URL.")
            return f"https://dummy-s3-bucket.s3.amazonaws.com/{filename}"
            
        # Generate a unique object name to prevent collisions
        unique_id = str(uuid.uuid4())[:8]
        object_name = f"{self.prefix}{unique_id}_{filename}"
        
        try:
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={'ContentType': content_type, 'ACL': 'public-read'}
            )
            
            # Construct the public URL
            url = f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{object_name}"
            return url
            
        except ClientError as e:
            logger.error(f"S3 Upload failed: {e}")
            return None

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL to share an S3 object securely.
        """
        if not self.s3_client:
            return None
            
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            return response
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None

storage_manager = S3StorageManager()
