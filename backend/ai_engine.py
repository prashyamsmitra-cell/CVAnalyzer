"""
AI Abstraction Layer for resume analysis.
Provides unified interface for multiple AI providers.
"""
from typing import Dict, List, Optional
import logging

from .ats import analyze_resume
from .config import settings
from .ollama_client import ollama

logger = logging.getLogger(__name__)


class AIEngine:
    """Unified AI interface supporting multiple providers."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or settings.AI_PROVIDER
        self._validate_provider()

    def _validate_provider(self):
        valid_providers = ["rule_based", "ollama", "openai"]
        if self.provider not in valid_providers:
            logger.warning("Invalid provider '%s', falling back to rule_based", self.provider)
            self.provider = "rule_based"

    async def analyze(
        self,
        resume_text: str,
        target_job: Optional[str] = None,
        current_prep: Optional[str] = None,
        job_description: Optional[str] = None,
    ) -> Dict:
        baseline_analysis = analyze_resume(
            resume_text,
            target_job=target_job,
            current_prep=current_prep,
        )

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

    async def _enhance_with_ollama(self, resume_text: str, baseline: Dict) -> Optional[Dict]:
        try:
            if not await ollama.is_available():
                logger.info("Ollama not available, using baseline analysis")
                return None
            return await ollama.analyze_resume(resume_text, baseline)
        except Exception as exc:
            logger.error("Ollama enhancement failed: %s", exc)
            return None

    async def _enhance_with_openai(self, resume_text: str, baseline: Dict) -> Optional[Dict]:
        if not settings.OPENAI_API_KEY:
            logger.info("OpenAI API key not configured")
            return None
        logger.info("OpenAI integration not implemented, using baseline")
        return None

    async def get_improvement_suggestions(self, section_type: str, content: str) -> List[str]:
        if self.provider == "ollama" and await ollama.is_available():
            return await ollama.suggest_improvements(section_type, content)
        return self._get_rule_based_suggestions(section_type)

    def _get_rule_based_suggestions(self, section_type: str) -> List[str]:
        suggestions = {
            "experience": [
                "Add quantifiable metrics (for example, increased efficiency by 25%)",
                "Start bullets with strong action verbs",
                "Include relevant technologies and tools used",
            ],
            "skills": [
                "Group skills by category such as technical, tools, and soft skills",
                "Match the skills to the target role keywords",
                "Include stronger evidence for core tools and technologies",
            ],
            "summary": [
                "Tailor the summary to the target role",
                "Include years of experience and strongest expertise",
                "End with a focused value proposition",
            ],
        }
        return suggestions.get(section_type, [
            "Add more specific details and metrics",
            "Use industry-standard terminology",
            "Ensure the content is ATS-readable",
        ])


def get_ai_engine(provider: Optional[str] = None) -> AIEngine:
    return AIEngine(provider)
