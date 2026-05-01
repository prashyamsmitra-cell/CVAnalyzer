"""
ATS (Applicant Tracking System) scoring engine.
Rule-based analysis for resume optimization.
"""
from typing import Dict, List, Tuple
import re
from .config import settings

class ATSScorer:
    """
    Rule-based ATS scoring system.
    Analyzes resumes for common ATS requirements.
    """
    
    # Standard resume sections
    REQUIRED_SECTIONS = [
        "experience", "education", "skills", "contact",
        "summary", "objective", "projects", "certifications"
    ]
    
    # Action verbs for impact statements
    ACTION_VERBS = [
        "achieved", "improved", "developed", "managed", "created",
        "implemented", "designed", "led", "increased", "reduced",
        "launched", "built", "optimized", "delivered", "coordinated",
        "analyzed", "established", "streamlined", "generated", "executed"
    ]
    
    # Common technical skills keywords
    TECHNICAL_SKILL_PATTERNS = [
        r'\b(python|java|javascript|typescript|react|node|sql|aws|docker|kubernetes)\b',
        r'\b(machine learning|data science|cloud|api|rest|graphql)\b',
        r'\b(git|agile|scrum|ci\/cd|microservices|backend|frontend)\b'
    ]
    
    # Soft skills keywords
    SOFT_SKILL_PATTERNS = [
        r'\b(leadership|communication|teamwork|problem.solving|analytical)\b',
        r'\b(collaboration|presentation|project.management|mentoring)\b'
    ]
    
    def __init__(self, text: str):
        """
        Initialize scorer with resume text.
        """
        self.text = text.lower()
        self.original_text = text
        self.lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    def calculate_score(self) -> Dict:
        """
        Calculate comprehensive ATS score.
        Returns detailed breakdown with recommendations.
        """
        scores = {
            "keyword_score": self._score_keywords(),
            "format_score": self._score_format(),
            "sections_score": self._score_sections(),
            "length_score": self._score_length(),
            "action_verbs_score": self._score_action_verbs()
        }
        
        # Weighted average
        ats_score = (
            scores["keyword_score"] * settings.ATS_WEIGHT_KEYWORDS +
            scores["format_score"] * settings.ATS_WEIGHT_FORMAT +
            scores["sections_score"] * settings.ATS_WEIGHT_SECTIONS +
            scores["length_score"] * settings.ATS_WEIGHT_LENGTH +
            scores["action_verbs_score"] * settings.ATS_WEIGHT_ACTION_VERBS
        )
        
        return {
            "ats_score": round(ats_score),
            "breakdown": scores,
            "strengths": self._get_strengths(scores),
            "weaknesses": self._get_weaknesses(scores),
            "missing_sections": self._get_missing_sections(),
            "recommendations": self._get_recommendations(scores)
        }
    
    def _score_keywords(self) -> float:
        """
        Score based on technical and soft skill keywords.
        """
        tech_matches = sum(
            len(re.findall(pattern, self.text))
            for pattern in self.TECHNICAL_SKILL_PATTERNS
        )
        soft_matches = sum(
            len(re.findall(pattern, self.text))
            for pattern in self.SOFT_SKILL_PATTERNS
        )
        
        # Normalize to 0-100
        total_matches = tech_matches + soft_matches
        score = min(total_matches * 5, 100)  # 5 points per keyword match
        return score
    
    def _score_format(self) -> float:
        """
        Score based on formatting best practices.
        """
        score = 100
        
        # Check for email
        if not re.search(r'[\w\.-]+@[\w\.-]+\.\w+', self.text):
            score -= 20
        
        # Check for phone
        if not re.search(r'\+?[\d\s\-\(\)]{10,}', self.text):
            score -= 15
        
        # Check for bullet points or structured content
        bullet_count = len(re.findall(r'[•\-\*]|\d+\.', self.original_text))
        if bullet_count < 5:
            score -= 15
        
        # Check for dates (experience timeline)
        if not re.search(r'\b(19|20)\d{2}\b', self.text):
            score -= 20
        
        return max(score, 0)
    
    def _score_sections(self) -> float:
        """
        Score based on presence of standard sections.
        """
        found_sections = 0
        for section in self.REQUIRED_SECTIONS:
            if section in self.text:
                found_sections += 1
        
        # At least 4 sections required for full score
        score = (found_sections / 4) * 100
        return min(score, 100)
    
    def _score_length(self) -> float:
        """
        Score based on appropriate resume length.
        Optimal: 400-800 words for 1-2 pages.
        """
        word_count = len(self.text.split())
        
        if word_count < 200:
            return 40  # Too short
        elif word_count < 400:
            return 70  # Slightly short
        elif word_count <= 800:
            return 100  # Optimal
        elif word_count <= 1000:
            return 80  # Slightly long
        else:
            return 60  # Too long
    
    def _score_action_verbs(self) -> float:
        """
        Score based on use of impact-driven action verbs.
        """
        verb_count = sum(
            1 for verb in self.ACTION_VERBS
            if verb in self.text
        )
        
        # Normalize: 10+ action verbs = full score
        score = min(verb_count * 10, 100)
        return score
    
    def _get_strengths(self, scores: Dict) -> List[str]:
        """
        Identify resume strengths based on scores.
        """
        strengths = []
        
        if scores["keyword_score"] >= 70:
            strengths.append("Strong technical keyword presence")
        if scores["format_score"] >= 80:
            strengths.append("Well-formatted with proper contact info")
        if scores["sections_score"] >= 75:
            strengths.append("Complete resume sections")
        if scores["action_verbs_score"] >= 60:
            strengths.append("Good use of action verbs")
        if scores["length_score"] >= 80:
            strengths.append("Appropriate resume length")
        
        return strengths if strengths else ["Resume submitted successfully"]
    
    def _get_weaknesses(self, scores: Dict) -> List[str]:
        """
        Identify areas for improvement.
        """
        weaknesses = []
        
        if scores["keyword_score"] < 50:
            weaknesses.append("Limited technical keywords - add relevant skills")
        if scores["format_score"] < 70:
            weaknesses.append("Missing contact information or poor formatting")
        if scores["sections_score"] < 60:
            weaknesses.append("Incomplete sections - add Experience, Education, Skills")
        if scores["action_verbs_score"] < 40:
            weaknesses.append("Weak action verbs - use 'achieved', 'developed', 'led'")
        if scores["length_score"] < 60:
            weaknesses.append("Resume length needs adjustment")
        
        return weaknesses
    
    def _get_missing_sections(self) -> List[str]:
        """
        Identify missing standard sections.
        """
        missing = []
        section_names = {
            "experience": "Work Experience",
            "education": "Education",
            "skills": "Skills",
            "summary": "Professional Summary",
            "projects": "Projects",
            "certifications": "Certifications"
        }
        
        for key, display_name in section_names.items():
            if key not in self.text:
                missing.append(display_name)
        
        return missing[:4]  # Return top 4 missing
    
    def _get_recommendations(self, scores: Dict) -> List[str]:
        """
        Generate actionable recommendations.
        """
        recommendations = []
        
        if scores["keyword_score"] < 60:
            recommendations.append(
                "Add 5-10 relevant technical skills from the job description"
            )
        
        if scores["action_verbs_score"] < 50:
            recommendations.append(
                "Replace passive language: 'Responsible for' → 'Managed', 'Helped' → 'Contributed to'"
            )
        
        if scores["sections_score"] < 70:
            recommendations.append(
                "Add missing sections with specific achievements and metrics"
            )
        
        if scores["length_score"] < 70:
            word_count = len(self.text.split())
            if word_count < 400:
                recommendations.append(
                    "Expand resume with more project details and achievements"
                )
            else:
                recommendations.append(
                    "Condense to 1-2 pages focusing on recent, relevant experience"
                )
        
        return recommendations

def analyze_resume(text: str) -> Dict:
    """
    Convenience function to analyze resume.
    Returns ATS analysis results.
    """
    scorer = ATSScorer(text)
    return scorer.calculate_score()
