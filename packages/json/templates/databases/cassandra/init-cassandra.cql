-- This script runs when Cassandra starts for the first time
-- It creates a keyspace and table with sample data

-- Create keyspace with SimpleStrategy (for single datacenter)
-- For production multi-datacenter, use NetworkTopologyStrategy
CREATE KEYSPACE IF NOT EXISTS myapp
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

-- Switch to the keyspace
USE myapp;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
  user_id UUID PRIMARY KEY,
  username TEXT,
  email TEXT,
  created_at TIMESTAMP,
  last_login TIMESTAMP
);

-- Create index on email for efficient lookups
CREATE INDEX IF NOT EXISTS ON users (email);

-- Insert sample data
INSERT INTO users (user_id, username, email, created_at, last_login)
VALUES (uuid(), 'sample_user', 'user@example.com', toTimestamp(now()), toTimestamp(now()));

-- Create a simple counter table example
CREATE TABLE IF NOT EXISTS page_views (
  page_name TEXT PRIMARY KEY,
  view_count COUNTER
);

-- Note: You cannot INSERT into counter columns, only UPDATE
-- Example: UPDATE page_views SET view_count = view_count + 1 WHERE page_name = 'homepage';
