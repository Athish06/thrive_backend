"""
Supabase Setup Script for ThrivePath
This script helps set up tables and RLS policies in Supabase
"""

import os
from dotenv import load_dotenv
from db import get_supabase_client, get_db_connection
import logging

load_dotenv()
logger = logging.getLogger(__name__)

def create_tables_with_rls():
    """
    Create tables in Supabase with Row Level Security enabled
    This uses direct PostgreSQL connection to create tables
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Create users table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
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
            """)
            
            # Create therapists table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS therapists (
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
            """)
            
            # Create parents table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parents (
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
            """)
            
            # Enable RLS on all tables
            cur.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE therapists ENABLE ROW LEVEL SECURITY;")
            cur.execute("ALTER TABLE parents ENABLE ROW LEVEL SECURITY;")
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_therapists_user_id ON therapists(user_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parents_user_id ON parents(user_id);")
            
            conn.commit()
            logger.info("Tables created successfully with RLS enabled")
            return True
            
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_rls_policies():
    """
    Create Row Level Security policies
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Users table policies
            cur.execute("""
                DROP POLICY IF EXISTS "Users can view own data" ON users;
                CREATE POLICY "Users can view own data" ON users
                    FOR SELECT USING (auth.uid()::text = id::text);
            """)
            
            cur.execute("""
                DROP POLICY IF EXISTS "Users can update own data" ON users;
                CREATE POLICY "Users can update own data" ON users
                    FOR UPDATE USING (auth.uid()::text = id::text);
            """)
            
            # Therapists table policies
            cur.execute("""
                DROP POLICY IF EXISTS "Therapists can view own profile" ON therapists;
                CREATE POLICY "Therapists can view own profile" ON therapists
                    FOR SELECT USING (auth.uid()::text = user_id::text);
            """)
            
            cur.execute("""
                DROP POLICY IF EXISTS "Therapists can update own profile" ON therapists;
                CREATE POLICY "Therapists can update own profile" ON therapists
                    FOR UPDATE USING (auth.uid()::text = user_id::text);
            """)
            
            # Parents table policies
            cur.execute("""
                DROP POLICY IF EXISTS "Parents can view own profile" ON parents;
                CREATE POLICY "Parents can view own profile" ON parents
                    FOR SELECT USING (auth.uid()::text = user_id::text);
            """)
            
            cur.execute("""
                DROP POLICY IF EXISTS "Parents can update own profile" ON parents;
                CREATE POLICY "Parents can update own profile" ON parents
                    FOR UPDATE USING (auth.uid()::text = user_id::text);
            """)
            
            conn.commit()
            logger.info("RLS policies created successfully")
            return True
            
    except Exception as e:
        logger.error(f"Error creating RLS policies: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def setup_supabase():
    """
    Complete Supabase setup
    """
    print("🚀 Setting up Supabase for ThrivePath...")
    
    # Test connection first
    print("📡 Testing database connection...")
    try:
        conn = get_db_connection()
        print("✅ Database connection successful!")
        conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # Create tables
    print("📋 Creating tables...")
    if create_tables_with_rls():
        print("✅ Tables created successfully!")
    else:
        print("❌ Failed to create tables")
        return False
    
    # Setup RLS policies (optional - only if using Supabase auth)
    print("🔒 Setting up Row Level Security policies...")
    try:
        create_rls_policies()
        print("✅ RLS policies created successfully!")
    except Exception as e:
        print(f"⚠️  RLS policies creation failed (this is OK if not using Supabase auth): {e}")
    
    print("🎉 Supabase setup complete!")
    return True

if __name__ == "__main__":
    setup_supabase()
