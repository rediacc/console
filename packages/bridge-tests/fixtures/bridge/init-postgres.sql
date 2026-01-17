-- PostgreSQL Fork Test Schema
-- This schema is designed to test data isolation between repository forks

-- Create test tables
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    repo_origin VARCHAR(100)  -- Track which repo created this record
);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    repo_origin VARCHAR(100)
);

-- Create index for efficient repo_origin queries
CREATE INDEX IF NOT EXISTS idx_users_repo_origin ON users(repo_origin);
CREATE INDEX IF NOT EXISTS idx_posts_repo_origin ON posts(repo_origin);

-- Insert seed data (marked with 'seed' origin)
INSERT INTO users (username, email, repo_origin) VALUES
    ('alice', 'alice@example.com', 'seed'),
    ('bob', 'bob@example.com', 'seed'),
    ('charlie', 'charlie@example.com', 'seed');

INSERT INTO posts (user_id, title, content, repo_origin) VALUES
    (1, 'First Post', 'Hello from Alice!', 'seed'),
    (2, 'Bobs Blog', 'Greetings from Bob', 'seed');
