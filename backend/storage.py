"""
Supabase Storage operations for resume files.
Handles upload, download, and file management.
"""
from typing import Optional
from supabase import create_client, Client
from .config import settings
import uuid
from datetime import datetime

class StorageManager:
    """
    Manages file storage with Supabase Storage.
    Handles resume uploads and retrieval.
    """
    
    def __init__(self):
        self._client: Optional[Client] = None
        self.bucket = settings.SUPABASE_BUCKET
    
    @property
    def client(self) -> Optional[Client]:
        """Lazy initialization of Supabase client."""
        if self._client is None:
            if settings.SUPABASE_URL and settings.SUPABASE_KEY:
                self._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_KEY
                )
        return self._client
    
    async def upload_resume(
        self, 
        file_content: bytes, 
        filename: str,
        whatsapp_number: str
    ) -> Optional[str]:
        """
        Upload resume to Supabase Storage.
        Returns public URL on success, None on failure.
        """
        if not self.client:
            print("Storage not configured - skipping upload")
            return None
            
        # Generate unique filename with user context
        file_ext = filename.split(".")[-1].lower()
        unique_name = f"{whatsapp_number}/{uuid.uuid4()}.{file_ext}"
        
        try:
            # Upload to Supabase Storage
            self.client.storage.from_(self.bucket).upload(
                unique_name,
                file_content,
                file_options={"content-type": f"application/{file_ext}"}
            )
            
            # Get public URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(unique_name)
            return public_url
        except Exception as e:
            print(f"Storage upload error: {e}")
            return None
    
    async def download_resume(self, path: str) -> Optional[bytes]:
        """
        Download resume from storage.
        Returns file content as bytes.
        """
        if not self.client:
            print("Storage not configured")
            return None
            
        try:
            response = self.client.storage.from_(self.bucket).download(path)
            return response
        except Exception as e:
            print(f"Storage download error: {e}")
            return None
    
    async def delete_resume(self, path: str) -> bool:
        """
        Delete resume from storage.
        Used for cleanup and GDPR compliance.
        """
        if not self.client:
            print("Storage not configured")
            return False
            
        try:
            self.client.storage.from_(self.bucket).remove([path])
            return True
        except Exception as e:
            print(f"Storage delete error: {e}")
            return False

# Singleton instance
storage = StorageManager()
