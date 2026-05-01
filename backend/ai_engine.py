"""
AI Abstraction Layer for resume analysis.
Provides unified interface for multiple AI providers.
"""
from typing import Dict, List, Optional
from .config import settings
from .ats import analyze_resume
from .ollama_client import ollama
import logging

logger = logging.getLogger(__name__)

class AIEngine:
    """
    Unified AI interface supporting multiple providers.
    Allows switching between rule-based, Ollama, and OpenAI.
    """
    
    def __init__(self, provider: Optional[str] = None):
        """
        Initialize AI engine with specified provider.
        Falls back to config default if not specified.
        """
        self.provider = provider or settings.AI_PROVIDER
        self._validate_provider()
    
    def _validate_provider(self):
        """
        Validate provider configuration.
        Falls back to rule_based if invalid.
        """
        valid_providers = ["rule_based", "ollama", "openai"]
        if self.provider not in valid_providers:
            logger.warning(f"Invalid provider '{self.provider}', falling back to rule_based")
            self.provider = "rule_based"
    
    async def analyze(
        self,
        resume_text: str,
        job_description: Optional[str] = None
    ) -> Dict:
        """
        Analyze resume using configured provider.
        Returns comprehensive analysis with insights.
        """
        # Always run rule-based analysis as baseline
        baseline_analysis = analyze_resume(resume_text)
        
        # Enhance with AI if available and configured
        if self.provider == "ollama":
            enhanced = await self._enhance_with_ollama(resume_text, baseline_analysis)
            if enhanced:
                baseline_analysis["ai_insights"] = enhanced
                baseline_analysis["provider"] = "ollama"
            else:
                baseline_analysis["provider"] = "rule_based_fallback"
        
        elif self.provider == "openai":
            enhanced = await self._enhance_with_openai(resume_text, baseline_analysis)
            if enhanced:
                baseline_analysis["ai_insights"] = enhanced
                baseline_analysis["provider"] = "openai"
            else:
                baseline_analysis["provider"] = "rule_based_fallback"
        
        else:
            baseline_analysis["provider"] = "rule_based"
        
        return baseline_analysis
    
    async def _enhance_with_ollama(
        self,
        resume_text: str,
        baseline: Dict
    ) -> Optional[Dict]:
        """
        Enhance analysis with Ollama local LLM.
        Returns None if Ollama unavailable.
        """
        try:
            if not await ollama.is_available():
                logger.info("Ollama not available, using baseline analysis")
                return None
            
            insights = await ollama.analyze_resume(resume_text, baseline)
            return insights
            
        except Exception as e:
            logger.error(f"Ollama enhancement failed: {e}")
            return None
    
    async def _enhance_with_openai(
        self,
        resume_text: str,
        baseline: Dict
    ) -> Optional[Dict]:
        """
        Enhance analysis with OpenAI API.
        Placeholder for OpenAI integration.
        """
        if not settings.OPENAI_API_KEY:
            logger.info("OpenAI API key not configured")
            return None
        
        # TODO: Implement OpenAI integration
        # This is a placeholder for the OpenAI fallback
        logger.info("OpenAI integration not implemented, using baseline")
        return None
    
    async def get_improvement_suggestions(
        self,
        section_type: str,
        content: str
    ) -> List[str]:
        """
        Get AI-powered improvement suggestions for a section.
        """
        if self.provider == "ollama" and await ollama.is_available():
            return await ollama.suggest_improvements(section_type, content)
        
        # Fallback suggestions
        return self._get_rule_based_suggestions(section_type, content)
    
    def _get_rule_based_suggestions(
        self,
        section_type: str,
        content: str
    ) -> List[str]:
        """
        Generate rule-based improvement suggestions.
        """
        suggestions = {
            "experience": [
                "Add quantifiable metrics (e.g., 'Increased efficiency by 25%')",
                "Start bullets with strong action verbs",
                "Include relevant technologies and tools used"
            ],
            "skills": [
                "Group skills by category (Technical, Soft, Tools)",
                "Match skills to job description keywords",
                "Include proficiency levels for key skills"
            ],
            "summary": [
                "Tailor summary to target role",
                "Include years of experience and key expertise",
                "End with a value proposition"
            ]
        }
        
        return suggestions.get(section_type, [
            "Add more specific details and metrics",
            "Use industry-standard terminology",
            "Ensure content is ATS-readable"
        ])

# Factory function
def get_ai_engine(provider: Optional[str] = None) -> AIEngine:
    """
    Create AI engine instance with specified provider.
    """
    return AIEngine(provider)
