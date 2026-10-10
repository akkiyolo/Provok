import pytest
from backend.app.storage.s3 import S3StorageManager
import io

def test_s3_storage_manager_initialization():
    manager = S3StorageManager()
    # It might be None if AWS credentials aren't provided correctly,
    # but the manager should handle it gracefully.
    assert hasattr(manager, 's3_client')
    
def test_upload_file_mock_fallback():
    manager = S3StorageManager()
    # Force client to None to test the fallback URL generation
    manager.s3_client = None
    
    file_obj = io.BytesIO(b"dummy image data")
    url = manager.upload_file(file_obj, "test_avatar.jpg")
    
    assert url is not None
    assert "dummy-s3-bucket" in url
    assert "test_avatar.jpg" in url
