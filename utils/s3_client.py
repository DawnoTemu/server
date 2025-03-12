# utils/s3_client.py
import boto3
from botocore.config import Config as BotoConfig
import os
import logging
from functools import lru_cache

# Configure logger
logger = logging.getLogger('s3_client')

class S3Client:
    """
    Singleton S3 client with connection pooling and retry configuration
    """
    # Class variable to store the singleton instance
    _instance = None
    _client = None
    _initialized = False
    
    # Cache environment variables
    _aws_access_key = None
    _aws_secret_key = None 
    _aws_region = None
    _bucket_name = None
    _max_pool_connections = None
    _max_retries = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(S3Client, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def initialize(cls):
        """Initialize the client once at application startup"""
        if cls._initialized:
            return
            
        # Cache environment variables
        cls._aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        cls._aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        cls._aws_region = os.getenv("AWS_REGION")
        cls._bucket_name = os.getenv("S3_BUCKET_NAME")
        cls._max_pool_connections = int(os.getenv("AWS_MAX_POOL_CONNECTIONS", "10"))
        cls._max_retries = int(os.getenv("AWS_MAX_RETRIES", "5"))
        
        # Configure boto3 with connection pooling and retry strategy
        boto_config = BotoConfig(
            region_name=cls._aws_region,
            retries={
                'max_attempts': cls._max_retries,
                'mode': 'adaptive'  # Adaptive retry mode with exponential backoff
            },
            max_pool_connections=cls._max_pool_connections
        )
        
        try:
            # Create the client with our optimized configuration
            cls._client = boto3.client(
                's3',
                aws_access_key_id=cls._aws_access_key,
                aws_secret_access_key=cls._aws_secret_key,
                config=boto_config
            )
            
            # Mark as initialized to avoid redundant configuration
            cls._initialized = True
            
            logger.info(f"S3 client initialized with max_pool_connections={cls._max_pool_connections}, max_retries={cls._max_retries}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise
    
    @classmethod
    def get_client(cls):
        """Get the configured S3 client instance"""
        if not cls._initialized:
            cls.initialize()
        return cls._client
    
    @classmethod
    def get_bucket_name(cls):
        """Get S3 bucket name from cached environment variables"""
        if not cls._initialized:
            cls.initialize()
        return cls._bucket_name
    
    @classmethod
    def generate_presigned_url(cls, key, expires_in=3600, response_headers=None):
        """
        Generate a presigned URL with optimized parameter handling
        
        Args:
            key: S3 object key
            expires_in: URL expiration time in seconds
            response_headers: Optional dict of response headers
            
        Returns:
            str: Presigned URL
        """
        params = {
            'Bucket': cls.get_bucket_name(),
            'Key': key
        }
        
        if response_headers:
            params.update(response_headers)
        
        return cls.get_client().generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expires_in
        )
    
    @classmethod
    def upload_fileobj(cls, file_obj, key, extra_args=None):
        """
        Upload a file object to S3 with optimized settings
        
        Args:
            file_obj: File-like object
            key: S3 object key
            extra_args: Optional dict of extra arguments
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Reset file pointer
            file_obj.seek(0)
            
            # Default extras for better performance
            if extra_args is None:
                extra_args = {}
            
            if 'ACL' not in extra_args:
                extra_args['ACL'] = 'private'
                
            cls.get_client().upload_fileobj(
                file_obj,
                cls.get_bucket_name(),
                key,
                ExtraArgs=extra_args
            )
            
            # Verify upload success
            try:
                cls.get_client().head_object(
                    Bucket=cls.get_bucket_name(),
                    Key=key
                )
                logger.debug(f"Successfully uploaded file to {key}")
                return True
            except Exception as e:
                logger.error(f"Upload verification failed for {key}: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to upload file to {key}: {str(e)}")
            return False
    
    @classmethod
    def delete_objects(cls, keys):
        """
        Delete multiple objects efficiently using batching
        
        Args:
            keys: List of keys to delete
            
        Returns:
            tuple: (success, deleted_count, errors)
        """
        if not keys:
            return True, 0, []
            
        try:
            # S3 API can delete up to 1000 objects per request
            errors = []
            deleted_count = 0
            
            # Process in batches of 1000
            for i in range(0, len(keys), 1000):
                batch = keys[i:i+1000]
                objects_to_delete = [{'Key': key} for key in batch]
                
                response = cls.get_client().delete_objects(
                    Bucket=cls.get_bucket_name(),
                    Delete={'Objects': objects_to_delete}
                )
                
                # Count successful deletes
                deleted_count += len(batch) - len(response.get('Errors', []))
                
                # Collect errors
                if 'Errors' in response:
                    errors.extend(response['Errors'])
            
            return len(errors) == 0, deleted_count, errors
            
        except Exception as e:
            logger.error(f"Failed to delete objects: {str(e)}")
            return False, 0, [str(e)]