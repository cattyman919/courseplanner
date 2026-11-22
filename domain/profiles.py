"""Preset student profiles used as demo scenarios."""

from domain.models import StudentProfile

PROFILES: list[StudentProfile] = [
    StudentProfile(
        name="On-track",
        completed=frozenset({
            "MATH101", "MATH201", "MATH210", "CS101", "CS201", "CS210", "GE101",
        }),
        target_track="ai",
    ),
    StudentProfile(
        name="Transfer",
        completed=frozenset({"MATH101", "MATH201", "CS101", "GE101", "GE102"}),
        target_track="ai",
        start_term="spring",
    ),
    StudentProfile(
        name="Heavy electives",
        completed=frozenset({
            "MATH101", "MATH201", "MATH210", "MATH301",
            "CS101", "CS201", "CS210", "CS301", "CS310", "GE101", "GE102",
        }),
        target_track="theory",
        elective_credits_required=12,
    ),
]
