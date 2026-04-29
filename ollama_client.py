"""
Ollama local LLM client for AI-powered resume analysis.
Provides enhanced insights using open-source models.
"""
from typing import Dict, List, Optional
import httpx
import json
from config import settings

class OllamaClient:
    """
    Client for Ollama local inference.
    Falls back gracefully if unavailable.
    """
    
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = 60.0  # Longer timeout for LLM inference
    
    async def is_available(self) -> bool:
        """
        Check if Ollama server is running.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    async def generate(
        self, 
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate text using Ollama API.
        Returns generated text or None on failure.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 1024
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "")
                return None
        except Exception as e:
            print(f"Ollama generation error: {e}")
            return None
    
    async def analyze_resume(
        self, 
        resume_text: str,
        ats_analysis: Dict
    ) -> Dict:
        """
        Enhance ATS analysis with LLM insights.
        Returns structured AI analysis.
        """
        system_prompt = """You are an expert resume analyst and career coach. 
Analyze resumes for ATS optimization, content quality, and job market competitiveness.
Provide specific, actionable feedback in JSON format."""

        analysis_prompt = f"""Analyze this resume and provide insights in JSON format.

Resume:
{resume_text[:3000]}

Current ATS Score: {ats_analysis.get('ats_score', 0)}

Provide analysis in this exact JSON format:
{{
    "overall_assessment": "Brief 2-sentence assessment",
    "key_strengths": ["strength1", "strength2", "strength3"],
    "improvement_areas": ["area1", "area2", "area3"],
    "skill_gaps": ["missing skill1", "missing skill2"],
    "bullet_point_suggestions": [
        {{"original": "weak bullet", "improved": "strong bullet"}}
    ],
    "summary_recommendation": "How to improve the professional summary",
    "competitive_advantage": "What makes this candidate stand out"
}}

Respond ONLY with valid JSON, no additional text."""

        try:
            response = await self.generate(analysis_prompt, system_prompt)
            
            if response:
                # Extract JSON from response
                json_match = response[response.find("{"):response.rfind("}")+1]
                ai_insights = json.loads(json_match)
                return ai_insights
            return {}
            
        except Exception as e:
            print(f"Resume analysis error: {e}")
            return {}
    
    async def suggest_improvements(
        self,
        section_type: str,
        current_content: str
    ) -> List[str]:
        """
        Generate specific improvements for a resume section.
        """
        prompt = f"""Improve this {section_type} section of a resume.
Current content:
{current_content}

Provide 3 improved versions that are:
1. More impactful with action verbs
2. Quantified with metrics where possible
3. ATS-optimized with relevant keywords

Format as a JSON array: ["improvement1", "improvement2", "improvement3"]
Respond ONLY with the JSON array."""

        response = await self.generate(prompt)
        
        if response:
            try:
                # Extract and parse JSON array
                json_match = response[response.find("["):response.rfind("]")+1]
                return json.loads(json_match)
            except:
                pass
        
        return []

# Singleton instance
ollama = OllamaClient()