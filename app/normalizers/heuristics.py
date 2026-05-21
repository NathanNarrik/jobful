from __future__ import annotations

import re

from app.models import AcademicLevel, JobListing, JobNormalization, ProgramType, RemoteType, VisaStatus


SKILL_ALIASES = {
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "c++": ("c++",),
    "c#": ("c#",),
    "docker": ("docker",),
    "go": ("golang", "go"),
    "graphql": ("graphql",),
    "java": ("java",),
    "javascript": ("javascript", "node.js", "nodejs"),
    "kubernetes": ("kubernetes", "k8s"),
    "linux": ("linux",),
    "machine learning": ("machine learning", "ml engineer"),
    "postgresql": ("postgres", "postgresql"),
    "python": ("python",),
    "react": ("react", "react.js", "reactjs"),
    "redis": ("redis",),
    "ruby": ("ruby",),
    "rust": ("rust",),
    "sql": ("sql",),
    "swift": ("swift",),
    "typescript": ("typescript",),
}

NICE_TO_HAVE_MARKERS = (
    "nice to have",
    "preferred qualifications",
    "preferred skills",
    "bonus",
    "plus if",
)

STUDENT_YEAR_CONTEXT_MARKERS = (
    "graduat",
    "class of",
    "degree",
    "student",
    "intern",
    "internship",
    "undergrad",
    "new grad",
    "university",
    "college",
    "summer",
    "fall",
    "winter",
    "spring",
)


def heuristic_normalize(job: JobListing, cleaned_description: str) -> JobNormalization:
    searchable = _searchable(job, cleaned_description)
    program_type = _program_type(searchable)
    academic_levels = _academic_levels(searchable)
    degree_requirements = _degree_requirements(searchable)
    grad_years = _grad_years(searchable)
    visa_status = _visa_status(searchable)
    required_skills = _skills(searchable)
    nice_to_have_skills = _nice_to_have_skills(searchable)
    remote_type = _remote_type(job, searchable)
    review_reasons = _review_reasons(
        cleaned_description=cleaned_description,
        program_type=program_type,
        academic_levels=academic_levels,
        grad_years=grad_years,
        visa_status=visa_status,
        remote_type=remote_type,
    )
    return JobNormalization(
        program_type=program_type,
        academic_levels=academic_levels,
        degree_requirements=degree_requirements,
        required_grad_years=grad_years,
        visa_sponsorship=_visa_sponsorship_from_status(visa_status),
        visa_status=visa_status,
        required_skills=required_skills,
        nice_to_have_skills=nice_to_have_skills,
        min_gpa=_min_gpa(searchable),
        clearance_required=_clearance_required(searchable),
        remote_type=remote_type,
        normalization_status=_normalization_status(review_reasons),
        confidence=_confidence(review_reasons),
        review_reasons=review_reasons,
    )


def _searchable(job: JobListing, cleaned_description: str) -> str:
    parts = [
        job.job_title,
        job.company_name,
        " ".join(job.location),
        job.employment_type or "",
        " ".join(job.departments),
        cleaned_description,
    ]
    return f" {' '.join(parts).lower()} "


def _program_type(text: str) -> ProgramType:
    new_grad_markers = ("new grad", "new graduate", "entry level", "university grad", "graduate program")
    if re.search(r"\b(?:intern|interns|internship|internships|co-op|co-ops|coop|coops)\b", text):
        return "internship"
    if "summer analyst" in text:
        return "internship"
    if any(_contains_alias(text, marker) for marker in new_grad_markers):
        return "new_grad"
    if re.search(r"\b[3-9]\+?\s+years?\b", text) or "senior" in text or "staff " in text:
        return "experienced"
    return "other"


def _academic_levels(text: str) -> list[AcademicLevel]:
    levels: list[AcademicLevel] = []
    markers: list[tuple[AcademicLevel, tuple[str, ...]]] = [
        ("freshman", ("freshman", "first-year", "first year")),
        ("sophomore", ("sophomore", "second-year", "second year")),
        ("junior", ("junior", "third-year", "third year")),
        ("senior", ("senior year", "college senior", "final year", "rising senior")),
        ("undergraduate", ("undergrad", "undergraduate", "bachelor", "b.s.", "bs degree", "ba degree")),
        ("masters", ("master's", "masters", "m.s.", "ms degree", "mba")),
        ("phd", ("phd", "ph.d", "doctorate", "doctoral")),
        ("new_grad", ("new grad", "new graduate", "recent graduate")),
    ]
    for level, aliases in markers:
        if any(alias in text for alias in aliases):
            levels.append(level)
    return levels


def _degree_requirements(text: str) -> list[str]:
    requirements: list[str] = []
    degree_patterns = [
        ("bachelors", ("bachelor", "b.s.", "bs degree", "ba degree", "undergrad", "undergraduate degree")),
        ("masters", ("master's", "masters", "m.s.", "ms degree", "mba")),
        ("phd", ("phd", "ph.d", "doctorate", "doctoral")),
    ]
    for requirement, aliases in degree_patterns:
        if any(alias in text for alias in aliases):
            requirements.append(requirement)
    return requirements


def _grad_years(text: str) -> list[int]:
    years: set[int] = set()
    range_pattern = re.compile(
        r"\b20(2[4-9]|3[0-5])\b\s*(?:-|to|through|and|or|,)\s*\b20(2[4-9]|3[0-5])\b"
    )
    for match in range_pattern.finditer(text):
        start = int(f"20{match.group(1)}")
        end = int(f"20{match.group(2)}")
        window = text[max(0, match.start() - 100) : match.end() + 100]
        if start <= end and _has_student_year_context(window):
            years.update(range(start, end + 1))

    for match in re.finditer(r"\b20(2[4-9]|3[0-5])\b", text):
        year = int(match.group(0))
        window = text[max(0, match.start() - 80) : match.end() + 80]
        if _has_student_year_context(window):
            years.add(year)
    return sorted(years)


def _has_student_year_context(text: str) -> bool:
    return any(marker in text for marker in STUDENT_YEAR_CONTEXT_MARKERS)


def _visa_status(text: str) -> VisaStatus:
    negative_patterns = (
        "does not sponsor",
        "do not sponsor",
        "cannot sponsor",
        "unable to sponsor",
        "will not sponsor",
        "not sponsor",
        "without sponsorship",
    )
    auth_required_patterns = (
        "must be authorized to work",
        "must be legally authorized to work",
        "authorized to work in the united states",
        "without restriction",
    )
    opt_cpt_patterns = (
        "opt/cpt",
        "opt and cpt",
        "cpt/opt",
        "curricular practical training",
        "optional practical training",
    )
    positive_patterns = (
        "visa sponsorship is available",
        "sponsorship is available",
        "we sponsor",
        "will sponsor",
        "h-1b sponsorship",
        "h1b sponsorship",
    )
    if any(pattern in text for pattern in opt_cpt_patterns):
        return "opt_cpt_allowed"
    if any(pattern in text for pattern in negative_patterns):
        return "does_not_sponsor"
    if any(pattern in text for pattern in auth_required_patterns):
        return "requires_authorization"
    if any(pattern in text for pattern in positive_patterns):
        return "sponsors"
    if "visa" in text or "sponsorship" in text or "work authorization" in text:
        return "unclear"
    return "not_mentioned"


def _visa_sponsorship_from_status(status: VisaStatus) -> bool | None:
    if status in {"sponsors", "opt_cpt_allowed"}:
        return True
    if status in {"does_not_sponsor", "requires_authorization"}:
        return False
    return None


def _skills(text: str) -> list[str]:
    found: list[str] = []
    normalized = text.lower()
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            found.append(canonical)
    return found


def _contains_alias(text: str, alias: str) -> bool:
    escaped = re.escape(alias.lower())
    return re.search(rf"(?<![a-z0-9-]){escaped}(?![a-z0-9-])", text) is not None


def _nice_to_have_skills(text: str) -> list[str]:
    sections = []
    for marker in NICE_TO_HAVE_MARKERS:
        index = text.find(marker)
        if index >= 0:
            sections.append(text[index : index + 1000])
    return _skills(" ".join(sections)) if sections else []


def _min_gpa(text: str) -> float | None:
    match = re.search(r"\b(?:minimum\s+)?(?:gpa|grade point average)\s*(?:of|:)?\s*([0-4]\.\d{1,2})\b", text)
    if not match:
        match = re.search(r"\b([0-4]\.\d{1,2})\s*(?:minimum\s+)?gpa\b", text)
    if not match:
        return None
    value = float(match.group(1))
    return value if 0 <= value <= 4.0 else None


def _clearance_required(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "security clearance",
            "secret clearance",
            "top secret",
            "ts/sci",
            "polygraph",
        )
    )


def _remote_type(job: JobListing, text: str) -> RemoteType:
    location_text = " ".join(job.location).lower()
    combined = f"{location_text} {text}"
    if "hybrid" in combined:
        return "hybrid"
    if any(marker in combined for marker in ("remote", "work from home", "distributed team")):
        return "remote"
    if any(marker in combined for marker in ("onsite", "on-site", "in office", "office-based")):
        return "onsite"
    return "unknown"


def _review_reasons(
    *,
    cleaned_description: str,
    program_type: ProgramType,
    academic_levels: list[AcademicLevel],
    grad_years: list[int],
    visa_status: VisaStatus,
    remote_type: RemoteType,
) -> list[str]:
    reasons: list[str] = []
    if not cleaned_description.strip():
        reasons.append("missing_description")
    if len(cleaned_description.strip()) < 120:
        reasons.append("short_description")
    if program_type in {"internship", "new_grad"} and not grad_years and not academic_levels:
        reasons.append("student_role_without_explicit_eligibility")
    if visa_status == "unclear":
        reasons.append("ambiguous_visa_language")
    if remote_type == "unknown":
        reasons.append("unknown_remote_type")
    return reasons


def _confidence(review_reasons: list[str]) -> float:
    if not review_reasons:
        return 0.92
    penalty = min(0.55, len(review_reasons) * 0.12)
    if "missing_description" in review_reasons:
        penalty = max(penalty, 0.45)
    return round(max(0.2, 0.88 - penalty), 2)


def _normalization_status(review_reasons: list[str]) -> str:
    blocking_reasons = {
        "missing_description",
        "short_description",
        "student_role_without_explicit_eligibility",
    }
    return "NEEDS_REVIEW" if any(reason in blocking_reasons for reason in review_reasons) else "COMPLETE"
