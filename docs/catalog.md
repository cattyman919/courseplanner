# Catalog and demo profiles

Source of truth: `domain/catalog.py` and `domain/profiles.py`. The database is seeded from
these on first launch.

## Graduation rule

A student finishes a track when they have completed every `math` and `core` course, every
`track` course of their target track (plus any prerequisites), and at least
`elective_credits_required` elective credits. Gen-ed is never required.

## Courses (25)

| Code | Title | Cr | Category | Prereqs | Offered | Slots |
|---|---|---|---|---|---|---|
| MATH101 | Calculus I | 4 | math | — | both | MW 08:00-09:30 |
| MATH201 | Calculus II | 4 | math | MATH101 | both | TR 08:00-09:30 |
| MATH210 | Discrete Mathematics | 3 | math | MATH101 | both | MW 10:00-11:30 |
| MATH301 | Linear Algebra | 3 | math | MATH201 | fall | TR 10:00-11:30 |
| CS101 | Intro to Programming | 4 | core | — | both | MW 13:00-14:30, F 10:00-11:00 |
| CS201 | Data Structures | 4 | core | CS101 | both | TR 13:00-14:30 |
| CS210 | Computer Organization | 3 | core | CS101 | spring | MW 10:00-11:30 |
| CS301 | Algorithms | 4 | core | CS201, MATH210 | fall | MW 13:00-14:30 |
| CS310 | Software Engineering | 3 | core | CS201 | both | TR 15:00-16:30 |
| AI320 | Intro to Artificial Intelligence | 3 | track/ai | CS301 | spring | MW 15:00-16:30 |
| AI330 | Machine Learning | 4 | track/ai | CS301, MATH301 | both | TR 10:00-11:30 |
| AI401 | Symbolic AI | 3 | track/ai | AI320 | fall | MW 10:00-11:30 |
| SYS320 | Operating Systems | 4 | track/systems | CS201, CS210 | fall | TR 15:00-16:30 |
| SYS330 | Computer Networks | 3 | track/systems | CS210 | both | MW 16:30-18:00, F 10:00-11:00 |
| SYS401 | Distributed Systems | 3 | track/systems | SYS320 | spring | TR 10:00-11:30 |
| TH320 | Theory of Computation | 3 | track/theory | CS301 | both | TR 08:00-09:30 |
| TH330 | Cryptography | 3 | track/theory | CS301, MATH210 | spring | MW 08:00-09:30 |
| TH401 | Computational Complexity | 3 | track/theory | TH320 | both | F 14:00-15:00 |
| CS350 | Databases | 3 | elective | CS201 | both | MW 15:00-16:30 |
| CS360 | Human-Computer Interaction | 3 | elective | CS101 | both | F 14:00-15:00 |
| CS370 | Computer Graphics | 3 | elective | CS201, MATH301 | fall | TR 13:00-14:30 |
| CS380 | Compilers | 4 | elective | CS301, CS210 | both | MW 18:00-19:30 |
| CS390 | Computer Security | 3 | elective | CS210 | both | TR 16:30-18:00 |
| GE101 | Academic Writing | 3 | gened | — | both | MW 11:30-12:30 |
| GE102 | Ethics in Computing | 3 | gened | — | both | TR 11:30-12:30 |

## Spec checks (§2)

- **Longest prerequisite chain:** 5 — CS101 → CS201 → CS301 → AI320 → AI401.
- **Single-term courses:** 9 — MATH301, CS210, CS301, AI320, AI401, SYS320, SYS401, TH330, CS370.
- **Shared slots:** 14 course pairs. Pairs a student can be eligible for in the same term:
  MATH210/CS210 (spring), AI320/CS350, CS310/SYS320, TH401/CS360.
- **Credits:** all 3 or 4.

## Profiles

| Profile | Track | Start | Electives needed | Completed |
|---|---|---|---|---|
| On-track | ai | fall | 9 | MATH101, MATH201, MATH210, CS101, CS201, CS210, GE101 |
| Transfer | ai | spring | 9 | MATH101, MATH201, CS101, GE101, GE102 |
| Heavy electives | theory | fall | 12 | MATH101, MATH201, MATH210, MATH301, CS101, CS201, CS210, CS301, CS310, GE101, GE102 |

- **Transfer** is missing CS201 and MATH210 (mid-chain) plus CS210. Starting in spring puts
  MATH210 and CS210 in the same term and slot, so `CONFLICT` fires; CS301 being fall-only
  forces extra terms.
- **Heavy electives** needs 4 of the 5 electives, so the combo generator has real choices.
