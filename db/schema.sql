CREATE TABLE IF NOT EXISTS courses (
  code TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 6),
  category TEXT NOT NULL,
  track TEXT
);

CREATE TABLE IF NOT EXISTS course_prereqs (
  course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  prereq_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  PRIMARY KEY (course_code, prereq_code)
);

CREATE TABLE IF NOT EXISTS course_coreqs (
  course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  coreq_code  TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  PRIMARY KEY (course_code, coreq_code)
);

CREATE TABLE IF NOT EXISTS course_slots (
  course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  slot TEXT NOT NULL,
  PRIMARY KEY (course_code, slot)
);

CREATE TABLE IF NOT EXISTS course_offerings (
  course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  term TEXT NOT NULL CHECK (term IN ('fall','spring')),
  PRIMARY KEY (course_code, term)
);

CREATE TABLE IF NOT EXISTS profiles (
  name TEXT PRIMARY KEY,
  target_track TEXT NOT NULL,
  max_credits INTEGER NOT NULL DEFAULT 18,
  start_term TEXT NOT NULL DEFAULT 'fall',
  elective_credits_required INTEGER NOT NULL DEFAULT 9
);

CREATE TABLE IF NOT EXISTS profile_completed (
  profile_name TEXT NOT NULL REFERENCES profiles(name) ON DELETE CASCADE,
  course_code  TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
  PRIMARY KEY (profile_name, course_code)
);

CREATE TABLE IF NOT EXISTS saved_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_name TEXT NOT NULL,
  target_track TEXT NOT NULL,
  algorithm TEXT NOT NULL,
  max_credits INTEGER NOT NULL,
  total_terms INTEGER NOT NULL,
  total_credits INTEGER NOT NULL,
  expanded INTEGER NOT NULL,
  elapsed_ms REAL NOT NULL,
  cost REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  plan_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES saved_plans(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  rule TEXT NOT NULL,
  subject TEXT NOT NULL,
  ok INTEGER NOT NULL,
  detail TEXT
);
