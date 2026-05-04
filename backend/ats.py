"""
ATS (Applicant Tracking System) scoring engine.
Rule-based analysis for resume optimization and role-fit evaluation.
"""
from typing import Dict, List, Optional
import re

from .config import settings


JOB_PROFILES = {
    "software engineer": {
        "skills": ["python", "java", "javascript", "sql", "git", "api", "data structures", "algorithms"],
        "nice_to_have": ["aws", "docker", "microservices", "testing"],
    },
    "frontend developer": {
        "skills": ["javascript", "typescript", "react", "html", "css", "frontend", "ui"],
        "nice_to_have": ["next.js", "tailwind", "figma", "accessibility"],
    },
    "backend developer": {
        "skills": ["python", "java", "node", "sql", "api", "backend", "database"],
        "nice_to_have": ["docker", "aws", "microservices", "graphql"],
    },
    "full stack developer": {
        "skills": ["javascript", "typescript", "react", "node", "sql", "api", "frontend", "backend"],
        "nice_to_have": ["docker", "aws", "testing", "ci/cd"],
    },
    "data analyst": {
        "skills": ["sql", "excel", "python", "data analysis", "statistics", "dashboard"],
        "nice_to_have": ["power bi", "tableau", "pandas", "visualization"],
    },
    "data scientist": {
        "skills": ["python", "machine learning", "statistics", "data science", "sql", "modeling"],
        "nice_to_have": ["pandas", "numpy", "tensorflow", "pytorch"],
    },
    "machine learning engineer": {
        "skills": ["python", "machine learning", "ml", "deployment", "apis", "modeling"],
        "nice_to_have": ["tensorflow", "pytorch", "docker", "aws"],
    },
    "devops engineer": {
        "skills": ["aws", "docker", "kubernetes", "ci/cd", "linux", "infrastructure"],
        "nice_to_have": ["terraform", "monitoring", "python", "bash"],
    },
    "product manager": {
        "skills": ["roadmap", "stakeholder", "analytics", "communication", "requirements", "research"],
        "nice_to_have": ["sql", "experimentation", "leadership", "prioritization"],
    },
    "ui ux designer": {
        "skills": ["figma", "wireframes", "prototyping", "research", "design systems", "ui"],
        "nice_to_have": ["accessibility", "usability", "interaction design", "frontend"],
    },
    "qa engineer": {
        "skills": ["testing", "qa", "automation", "bug tracking", "api testing", "selenium"],
        "nice_to_have": ["postman", "python", "javascript", "ci/cd"],
    },
    "internship": {
        "skills": ["projects", "python", "javascript", "sql", "communication", "teamwork"],
        "nice_to_have": ["internship", "leadership", "git", "problem solving"],
    },
}

PREP_LEVELS = {
    "just starting": 35,
    "learning basics": 40,
    "some projects": 58,
    "coursework and projects": 62,
    "internship-ready": 75,
    "interview-ready": 85,
    "already applying": 78,
}


class ATSScorer:
    """Rule-based ATS scoring system with job-fit evaluation."""

    REQUIRED_SECTIONS = [
        "experience", "education", "skills", "contact",
        "summary", "objective", "projects", "certifications",
    ]

    ACTION_VERBS = [
        "achieved", "improved", "developed", "managed", "created",
        "implemented", "designed", "led", "increased", "reduced",
        "launched", "built", "optimized", "delivered", "coordinated",
        "analyzed", "established", "streamlined", "generated", "executed",
    ]

    TECHNICAL_SKILL_PATTERNS = [
        r"\b(python|java|javascript|typescript|react|node|sql|aws|docker|kubernetes)\b",
        r"\b(machine learning|data science|cloud|api|rest|graphql|html|css)\b",
        r"\b(git|agile|scrum|ci\/cd|microservices|backend|frontend|testing)\b",
    ]

    SOFT_SKILL_PATTERNS = [
        r"\b(leadership|communication|teamwork|problem solving|analytical)\b",
        r"\b(collaboration|presentation|project management|mentoring|stakeholder)\b",
    ]

    def __init__(self, text: str, target_job: Optional[str] = None, current_prep: Optional[str] = None):
        self.text = text.lower()
        self.original_text = text
        self.lines = [line.strip() for line in text.split("\n") if line.strip()]
        self.target_job = (target_job or "software engineer").strip().lower()
        self.current_prep = (current_prep or "some projects").strip().lower()
        self.job_key = self._resolve_job_key(self.target_job)
        self.job_profile = JOB_PROFILES[self.job_key]

    def calculate_score(self) -> Dict:
        scores = {
            "keyword_score": self._score_keywords(),
            "format_score": self._score_format(),
            "sections_score": self._score_sections(),
            "length_score": self._score_length(),
            "action_verbs_score": self._score_action_verbs(),
        }

        ats_score = (
            scores["keyword_score"] * settings.ATS_WEIGHT_KEYWORDS +
            scores["format_score"] * settings.ATS_WEIGHT_FORMAT +
            scores["sections_score"] * settings.ATS_WEIGHT_SECTIONS +
            scores["length_score"] * settings.ATS_WEIGHT_LENGTH +
            scores["action_verbs_score"] * settings.ATS_WEIGHT_ACTION_VERBS
        )

        job_fit = self._score_job_fit()
        prep_score = self._score_prep_level()
        likelihood_score = round((ats_score * 0.55) + (job_fit["score"] * 0.35) + (prep_score * 0.10))

        return {
            "ats_score": round(ats_score),
            "breakdown": scores,
            "strengths": self._get_strengths(scores, job_fit),
            "weaknesses": self._get_weaknesses(scores, job_fit),
            "missing_sections": self._get_missing_sections(),
            "recommendations": self._get_recommendations(scores, job_fit),
            "provider": "rule_based",
            "target_job": self.job_key.title(),
            "current_prep": self.current_prep.title(),
            "job_fit_score": job_fit["score"],
            "job_fit_label": self._label_score(job_fit["score"]),
            "matched_job_skills": job_fit["matched_skills"],
            "missing_job_skills": job_fit["missing_skills"],
            "likelihood_score": likelihood_score,
            "likelihood_label": self._likelihood_label(likelihood_score),
            "prep_score": prep_score,
        }

    def _resolve_job_key(self, target_job: str) -> str:
        if target_job in JOB_PROFILES:
            return target_job
        for job_key in JOB_PROFILES:
            if job_key in target_job or target_job in job_key:
                return job_key
        return "software engineer"

    def _score_keywords(self) -> float:
        tech_matches = sum(len(re.findall(pattern, self.text)) for pattern in self.TECHNICAL_SKILL_PATTERNS)
        soft_matches = sum(len(re.findall(pattern, self.text)) for pattern in self.SOFT_SKILL_PATTERNS)
        return min((tech_matches + soft_matches) * 5, 100)

    def _score_format(self) -> float:
        score = 100
        if not re.search(r"[\w\.-]+@[\w\.-]+\.\w+", self.text):
            score -= 20
        if not re.search(r"\+?[\d\s\-\(\)]{10,}", self.text):
            score -= 15
        bullet_count = len(re.findall(r"[-*]|\d+\.", self.original_text))
        if bullet_count < 5:
            score -= 15
        if not re.search(r"\b(19|20)\d{2}\b", self.text):
            score -= 20
        return max(score, 0)

    def _score_sections(self) -> float:
        found_sections = sum(1 for section in self.REQUIRED_SECTIONS if section in self.text)
        return min((found_sections / 4) * 100, 100)

    def _score_length(self) -> float:
        word_count = len(self.text.split())
        if word_count < 200:
            return 40
        if word_count < 400:
            return 70
        if word_count <= 800:
            return 100
        if word_count <= 1000:
            return 80
        return 60

    def _score_action_verbs(self) -> float:
        verb_count = sum(1 for verb in self.ACTION_VERBS if verb in self.text)
        return min(verb_count * 10, 100)

    def _score_job_fit(self) -> Dict:
        required = self.job_profile["skills"]
        optional = self.job_profile["nice_to_have"]
        matched_required = [skill for skill in required if self._has_skill(skill)]
        matched_optional = [skill for skill in optional if self._has_skill(skill)]
        missing_required = [skill for skill in required if skill not in matched_required]
        required_score = (len(matched_required) / max(len(required), 1)) * 80
        optional_score = (len(matched_optional) / max(len(optional), 1)) * 20
        score = round(min(required_score + optional_score, 100))
        return {
            "score": score,
            "matched_skills": matched_required[:6] + matched_optional[:3],
            "missing_skills": missing_required[:6],
        }

    def _score_prep_level(self) -> int:
        if self.current_prep in PREP_LEVELS:
            return PREP_LEVELS[self.current_prep]
        for level, score in PREP_LEVELS.items():
            if level in self.current_prep or self.current_prep in level:
                return score
        return 55

    def _has_skill(self, skill: str) -> bool:
        return bool(re.search(r"\b" + re.escape(skill.lower()) + r"\b", self.text))

    def _get_strengths(self, scores: Dict, job_fit: Dict) -> List[str]:
        strengths: List[str] = []
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
        if job_fit["score"] >= 70:
            strengths.append(f"Strong alignment with {self.job_key.title()} skill requirements")
        return strengths if strengths else ["Resume submitted successfully"]

    def _get_weaknesses(self, scores: Dict, job_fit: Dict) -> List[str]:
        weaknesses: List[str] = []
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
        if job_fit["missing_skills"]:
            weaknesses.append(f"Missing role-relevant skills for {self.job_key.title()}")
        return weaknesses

    def _get_missing_sections(self) -> List[str]:
        missing: List[str] = []
        section_names = {
            "experience": "Work Experience",
            "education": "Education",
            "skills": "Skills",
            "summary": "Professional Summary",
            "projects": "Projects",
            "certifications": "Certifications",
        }
        for key, display_name in section_names.items():
            if key not in self.text:
                missing.append(display_name)
        return missing[:4]

    def _get_recommendations(self, scores: Dict, job_fit: Dict) -> List[str]:
        recommendations: List[str] = []
        if scores["keyword_score"] < 60:
            recommendations.append("Add 5-10 relevant technical skills from the target job")
        if scores["action_verbs_score"] < 50:
            recommendations.append("Use stronger action verbs and measurable outcomes in experience bullets")
        if scores["sections_score"] < 70:
            recommendations.append("Add missing sections with specific achievements and project outcomes")
        if scores["length_score"] < 70:
            recommendations.append("Expand the resume with clearer project impact and relevant experience")
        if job_fit["missing_skills"]:
            recommendations.append("Highlight or build evidence for these role-specific skills: " + ", ".join(job_fit["missing_skills"][:4]))
        if self._score_prep_level() < 60:
            recommendations.append("Strengthen your current prep with 2-3 strong portfolio or internship-ready projects")
        return recommendations[:5]

    def _label_score(self, score: int) -> str:
        if score >= 75:
            return "Strong"
        if score >= 55:
            return "Moderate"
        return "Weak"

    def _likelihood_label(self, score: int) -> str:
        if score >= 78:
            return "High Shortlist Potential"
        if score >= 62:
            return "Moderate Shortlist Potential"
        if score >= 45:
            return "Needs More Role Alignment"
        return "Early Stage for This Role"


def analyze_resume(text: str, target_job: Optional[str] = None, current_prep: Optional[str] = None) -> Dict:
    return ATSScorer(text, target_job=target_job, current_prep=current_prep).calculate_score()
