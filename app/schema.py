SCHEMA = """
CREATE TABLE IF NOT EXISTS studios (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classes (
  id INTEGER PRIMARY KEY,
  studio_id INTEGER NOT NULL REFERENCES studios(id),
  title TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  starts_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  class_id INTEGER NOT NULL REFERENCES classes(id),
  studio_id INTEGER NOT NULL REFERENCES studios(id),
  status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'cancelled')),
  created_at INTEGER NOT NULL,
  paid_at INTEGER,
  cancelled_at INTEGER,
  price_cents INTEGER NOT NULL,
  occurs_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS bookings_active_member_class_date
  ON bookings (user_id, class_id, occurs_at) WHERE status != 'cancelled';
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  occurred_at INTEGER NOT NULL,
  user_id INTEGER,
  session_id TEXT NOT NULL,
  studio_id INTEGER,
  booking_id INTEGER,
  class_id INTEGER,
  event_name TEXT NOT NULL,
  properties TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_occurred_at ON events (occurred_at);
"""
