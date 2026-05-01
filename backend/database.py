"""
Database operations using Supabase.
Handles user sessions, resume metadata, and analysis history.
"""
from typing import Optional, Dict, Any
from supabase import create_client, Client
from .config import settings
import json
from datetime import datetime

class DatabaseManager:
    """
    Manages all database operations with Supabase.
    Provides methods for user management and analysis storage.
    """
    
    def __init__(self):
        self._client: Optional[Client] = None
    
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
    
    async def get_user_session(self, whatsapp_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user session by WhatsApp number.
        Returns None if user doesn't exist.
        """
        if not self.client:
            return None
            
        try:
            response = self.client.table("user_sessions")\
                .select("*")\
                .eq("whatsapp_number", whatsapp_number)\
                .single()\
                .execute()
            return response.data
        except Exception:
            return None
    
    async def create_user_session(self, whatsapp_number: str) -> Dict[str, Any]:
        """
        Create a new user session.
        Initializes with default state.
        """
        if not self.client:
            return {
                "whatsapp_number": whatsapp_number,
                "state": "awaiting_resume",
                "resume_url": None,
                "last_analysis": None
            }
            
        data = {
            "whatsapp_number": whatsapp_number,
            "state": "awaiting_resume",
            "created_at": datetime.utcnow().isoformat(),
            "resume_url": None,
            "last_analysis": None
        }
        
        response = self.client.table("user_sessions")\
            .insert(data)\
            .execute()
        return response.data[0]
    
    async def update_user_state(
        self, 
        whatsapp_number: str, 
        state: str,
        extra_data: Optional[Dict] = None
    ) -> bool:
        """
        Update user session state.
        Used for conversation flow management.
        """
        if not self.client:
            return False
            
        update_data = {"state": state, "updated_at": datetime.utcnow().isoformat()}
        if extra_data:
            update_data.update(extra_data)
        
        try:
            self.client.table("user_sessions")\
                .update(update_data)\
                .eq("whatsapp_number", whatsapp_number)\
                .execute()
            return True
        except Exception as e:
            print(f"Error updating user state: {e}")
            return False
    
    async def save_analysis(
        self,
        whatsapp_number: str,
        resume_url: str,
        ats_score: int,
        strengths: list,
        weaknesses: list,
        missing_sections: list,
        ai_insights: list
    ) -> Dict[str, Any]:
        """
        Save complete analysis to database.
        Creates a historical record for the user.
        """
        if not self.client:
            return {
                "whatsapp_number": whatsapp_number,
                "ats_score": ats_score
            }
            
        data = {
            "whatsapp_number": whatsapp_number,
            "resume_url": resume_url,
            "ats_score": ats_score,
            "strengths": json.dumps(strengths),
            "weaknesses": json.dumps(weaknesses),
            "missing_sections": json.dumps(missing_sections),
            "ai_insights": json.dumps(ai_insights),
            "created_at": datetime.utcnow().isoformat()
        }
        
        response = self.client.table("analyses")\
            .insert(data)\
            .execute()
        return response.data[0]
    
    async def get_user_analyses(self, whatsapp_number: str, limit: int = 5) -> list:
        """
        Retrieve user's analysis history.
        Limited to most recent analyses.
        """
        if not self.client:
            return []
            
        response = self.client.table("analyses")\
            .select("*")\
            .eq("whatsapp_number", whatsapp_number)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data

# Singleton instance
db = DatabaseManager()
