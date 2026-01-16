-- Database schema for ThrivePath authentication and user management
-- Updated for Supabase compatibility

-- Users table for authentication
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL CHECK (role IN ('therapist', 'parent')),
  is_active BOOLEAN DEFAULT TRUE,
  is_verified BOOLEAN DEFAULT FALSE,
  last_login TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Therapists table (matching Supabase schema)
CREATE TABLE therapists (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT UNIQUE NOT NULL,
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  phone VARCHAR(255),
  bio TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT fk_therapist_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Parents table
CREATE TABLE parents (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT UNIQUE NOT NULL,
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  phone VARCHAR(255),
  address TEXT,
  emergency_contact VARCHAR(255),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT fk_parent_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Indexes for better performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_therapists_user_id ON therapists(user_id);
CREATE INDEX idx_therapists_email ON therapists(email);
CREATE INDEX idx_parents_user_id ON parents(user_id);
CREATE INDEX idx_parents_email ON parents(email);

-- Session Notes table for storing therapist notes
CREATE TABLE session_notes (
  notes_id BIGSERIAL PRIMARY KEY,
  therapist_id BIGINT NOT NULL,
  session_date DATE NOT NULL,  -- The date the session occurred
  note_content TEXT NOT NULL,
  note_title VARCHAR(255),  -- Optional: brief title/summary
  session_time TIME,  -- Optional: time of session
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_edited_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT fk_notes_therapist FOREIGN KEY (therapist_id) REFERENCES therapists(id) ON DELETE CASCADE
);

-- Indexes for session notes
CREATE INDEX idx_session_notes_therapist_id ON session_notes(therapist_id);
CREATE INDEX idx_session_notes_session_date ON session_notes(session_date);
CREATE INDEX idx_session_notes_therapist_date ON session_notes(therapist_id, session_date);

-- AI Preferences table for storing custom AI behavior instructions per child
CREATE TABLE ai_preferences (
  id BIGSERIAL PRIMARY KEY,
  child_id BIGINT NOT NULL UNIQUE,
  ai_instructions TEXT NOT NULL,  -- Custom instructions for how AI should behave
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT fk_ai_pref_child FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
);

-- Index for AI preferences
CREATE INDEX idx_ai_preferences_child_id ON ai_preferences(child_id);
