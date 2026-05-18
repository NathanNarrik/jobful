from __future__ import annotations

from typing import Any


STRONG_CS_TITLE_TERMS = (
    "ai engineer",
    "android",
    "application developer",
    "application engineer",
    "applied scientist",
    "backend",
    "back end",
    "cloud engineer",
    "computer vision",
    "cybersecurity",
    "data engineer",
    "data scientist",
    "database administrator",
    "devops",
    "embedded software",
    "frontend",
    "front end developer",
    "front end engineer",
    "full stack",
    "fullstack",
    "ios engineer",
    "machine learning",
    "ml engineer",
    "mobile engineer",
    "platform engineer",
    "product security",
    "qa automation",
    "robotics software",
    "security engineer",
    "site reliability",
    "software",
    "sre",
    "technical program manager",
    "web developer",
)

WEAK_CS_TITLE_TERMS = (
    "analytics engineer",
    "business intelligence",
    "cloud",
    "cyber",
    "data analyst",
    "developer",
    "engineer",
    "information security",
    "network",
    "programmer",
    "qa engineer",
    "security analyst",
    "solutions architect",
    "systems administrator",
    "systems engineer",
    "technology analyst",
)

CS_DEPARTMENT_TERMS = (
    "ai",
    "cloud engineering",
    "computer science",
    "cybersecurity",
    "data platform",
    "data science",
    "developer platform",
    "information security",
    "information technology",
    "machine learning",
    "platform engineering",
    "product engineering",
    "security engineering",
    "software",
)

CS_SKILLS = {
    "aws",
    "azure",
    "c#",
    "c++",
    "docker",
    "graphql",
    "java",
    "javascript",
    "kubernetes",
    "linux",
    "machine learning",
    "postgresql",
    "python",
    "react",
    "redis",
    "ruby",
    "rust",
    "sql",
    "swift",
    "typescript",
}

NON_CS_TITLE_TERMS = (
    "account executive",
    "account manager",
    "accountant",
    "accounting",
    "assistant manager",
    "business development",
    "cashier",
    "cart attendant",
    "courier",
    "creative",
    "customer success",
    "customer service",
    "delivery driver",
    "department supervisor",
    "industry principal",
    "marketing",
    "merchandising",
    "freight handler",
    "handler",
    "material handler",
    "nurse",
    "order filler",
    "pharmacy technician",
    "production coordinator",
    "production worker",
    "quality inspector",
    "retail operations",
    "retail sales",
    "sales associate",
    "shift supervisor",
    "store associate",
    "store support",
    "truck driver",
    "warehouse worker",
)

TECHNICAL_ROLE_NOUNS = (
    "administrator",
    "analyst",
    "architect",
    "developer",
    "devops",
    "engineer",
    "programmer",
    "scientist",
    "sdet",
    "sre",
)

CS_DESCRIPTION_TERMS = (
    " computer science ",
    " software engineering ",
    " programming ",
    " build software ",
    " distributed systems ",
)


def is_cs_relevant_job(
    *,
    title: str,
    departments: list[str] | None = None,
    required_skills: list[str] | None = None,
    nice_to_have_skills: list[str] | None = None,
    description: str | None = None,
) -> bool:
    title_text = _normalize(title)
    department_text = _normalize(" ".join(departments or []))
    skill_values = {skill.strip().lower() for skill in (required_skills or []) + (nice_to_have_skills or [])}
    description_text = _normalize(description or "")

    has_negative_title = _contains_any(title_text, NON_CS_TITLE_TERMS)
    has_technical_role_noun = _contains_any(title_text, TECHNICAL_ROLE_NOUNS)
    has_strong_title = _contains_any(title_text, STRONG_CS_TITLE_TERMS)
    has_weak_title = _contains_any(title_text, WEAK_CS_TITLE_TERMS)
    has_cs_department = _contains_any(department_text, CS_DEPARTMENT_TERMS)
    has_cs_skill = bool(skill_values.intersection(CS_SKILLS))
    has_cs_description = _contains_any(description_text, CS_DESCRIPTION_TERMS)

    if has_negative_title and not has_technical_role_noun:
        return False

    if has_strong_title:
        return True

    if has_weak_title and (has_cs_department or has_cs_skill or has_cs_description):
        return True

    if has_cs_department and has_cs_skill and not has_negative_title:
        return True

    return False


def is_cs_relevant_record(record: dict[str, Any]) -> bool:
    job = record.get("job") or {}
    normalization = record.get("normalization") or {}
    return is_cs_relevant_job(
        title=str(job.get("job_title") or ""),
        departments=[str(item) for item in job.get("departments") or []],
        required_skills=[str(item) for item in normalization.get("required_skills") or []],
        nice_to_have_skills=[str(item) for item in normalization.get("nice_to_have_skills") or []],
        description=str(record.get("cleaned_description") or job.get("raw_description") or ""),
    )


def _normalize(value: str) -> str:
    return f" {value.lower().replace('/', ' ').replace('-', ' ').replace('_', ' ')} "


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize(term) in text for term in terms)
