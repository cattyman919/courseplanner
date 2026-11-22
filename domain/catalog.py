"""Course catalog: the knowledge base of a small university CS program.

Graduation requirements for a track are every ``math`` and ``core`` course, every
``track`` course of the target track, and enough ``elective`` credits. Gen-ed courses
are never required, so the planner prunes them.
"""

from domain.models import Course

FALL = ("fall",)
SPRING = ("spring",)
BOTH = ("fall", "spring")

CATALOG: list[Course] = [
    # --- math ---
    Course("MATH101", "Calculus I", 4, offered=BOTH,
           slots=("MW 08:00-09:30",), category="math"),
    Course("MATH201", "Calculus II", 4, prereqs=("MATH101",), offered=BOTH,
           slots=("TR 08:00-09:30",), category="math"),
    Course("MATH210", "Discrete Mathematics", 3, prereqs=("MATH101",), offered=BOTH,
           slots=("MW 10:00-11:30",), category="math"),
    Course("MATH301", "Linear Algebra", 3, prereqs=("MATH201",), offered=FALL,
           slots=("TR 10:00-11:30",), category="math"),
    # --- shared CS core ---
    Course("CS101", "Intro to Programming", 4, offered=BOTH,
           slots=("MW 13:00-14:30", "F 10:00-11:00"), category="core"),
    Course("CS201", "Data Structures", 4, prereqs=("CS101",), offered=BOTH,
           slots=("TR 13:00-14:30",), category="core"),
    Course("CS210", "Computer Organization", 3, prereqs=("CS101",), offered=SPRING,
           slots=("MW 10:00-11:30",), category="core"),
    Course("CS301", "Algorithms", 4, prereqs=("CS201", "MATH210"), offered=FALL,
           slots=("MW 13:00-14:30",), category="core"),
    Course("CS310", "Software Engineering", 3, prereqs=("CS201",), offered=BOTH,
           slots=("TR 15:00-16:30",), category="core"),
    # --- ai track ---
    Course("AI320", "Intro to Artificial Intelligence", 3, prereqs=("CS301",),
           offered=SPRING, slots=("MW 15:00-16:30",), category="track", track="ai"),
    Course("AI330", "Machine Learning", 4, prereqs=("CS301", "MATH301"), offered=BOTH,
           slots=("TR 10:00-11:30",), category="track", track="ai"),
    Course("AI401", "Symbolic AI", 3, prereqs=("AI320",), offered=FALL,
           slots=("MW 10:00-11:30",), category="track", track="ai"),
    # --- systems track ---
    Course("SYS320", "Operating Systems", 4, prereqs=("CS201", "CS210"), offered=FALL,
           slots=("TR 15:00-16:30",), category="track", track="systems"),
    Course("SYS330", "Computer Networks", 3, prereqs=("CS210",), offered=BOTH,
           slots=("MW 16:30-18:00", "F 10:00-11:00"), category="track", track="systems"),
    Course("SYS401", "Distributed Systems", 3, prereqs=("SYS320",), offered=SPRING,
           slots=("TR 10:00-11:30",), category="track", track="systems"),
    # --- theory track ---
    Course("TH320", "Theory of Computation", 3, prereqs=("CS301",), offered=BOTH,
           slots=("TR 08:00-09:30",), category="track", track="theory"),
    Course("TH330", "Cryptography", 3, prereqs=("CS301", "MATH210"), offered=SPRING,
           slots=("MW 08:00-09:30",), category="track", track="theory"),
    Course("TH401", "Computational Complexity", 3, prereqs=("TH320",), offered=BOTH,
           slots=("F 14:00-15:00",), category="track", track="theory"),
    # --- electives (count toward any track) ---
    Course("CS350", "Databases", 3, prereqs=("CS201",), offered=BOTH,
           slots=("MW 15:00-16:30",), category="elective"),
    Course("CS360", "Human-Computer Interaction", 3, prereqs=("CS101",), offered=BOTH,
           slots=("F 14:00-15:00",), category="elective"),
    Course("CS370", "Computer Graphics", 3, prereqs=("CS201", "MATH301"), offered=FALL,
           slots=("TR 13:00-14:30",), category="elective"),
    Course("CS380", "Compilers", 4, prereqs=("CS301", "CS210"), offered=BOTH,
           slots=("MW 18:00-19:30",), category="elective"),
    Course("CS390", "Computer Security", 3, prereqs=("CS210",), offered=BOTH,
           slots=("TR 16:30-18:00",), category="elective"),
    # --- gen-ed (never required) ---
    Course("GE101", "Academic Writing", 3, offered=BOTH,
           slots=("MW 11:30-12:30",), category="gened"),
    Course("GE102", "Ethics in Computing", 3, offered=BOTH,
           slots=("TR 11:30-12:30",), category="gened"),
]
