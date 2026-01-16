import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import jwt
from jwt import PyJWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import get_supabase_client, format_supabase_response, handle_supabase_error
from users.profiles import get_therapist_profile, get_parent_profile
from dotenv import load_dotenv
import logging

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)
load_dotenv()

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# FastAPI Security
security = HTTPBearer()

# ==================== PASSWORD VERIFICATION ====================
# Functions for password hashing and verification

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a hashed password
    - Uses bcrypt for secure password comparison
    - Returns True if passwords match, False otherwise
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# ==================== USER DATA RETRIEVAL ====================
# Functions for fetching user information from database

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve user from database by email address with profile data
    - Fetches user from Supabase users table
    - Includes role-specific profile data (therapist/parent)
    - Returns None if user not found
    """
    try:
        client = get_supabase_client()
        
        # Get user from users table
        response = client.table('users').select('*').eq('email', email).execute()
        handle_supabase_error(response)
        
        users = format_supabase_response(response)
        if not users:
            return None
        
        user = users[0]
        
        # Get profile data based on role
        if user["role"] == "therapist":
            profile = get_therapist_profile(user["id"])
        elif user["role"] == "parent":
            profile = get_parent_profile(user["id"])
        else:
            profile = None
        
        if profile:
            user["profile"] = profile
        
        return user
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {e}")
        return None

def update_last_login(user_id: int) -> None:
    """
    Update user's last login timestamp in database
    - Records current UTC timestamp for login tracking
    - Used for security monitoring and user activity tracking
    """
    try:
        client = get_supabase_client()
        
        response = client.table('users').update({
            'last_login': datetime.utcnow().isoformat()
        }).eq('id', user_id).execute()
        
        handle_supabase_error(response)
        logger.info(f"Updated last login for user {user_id}")
    except Exception as e:
        logger.error(f"Error updating last login for user {user_id}: {e}")

# ==================== USER AUTHENTICATION ====================
# Functions for user login and credential validation

def authenticate_user_detailed(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Authenticate user with detailed error reporting
    - Validates email/password combination
    - Checks account status (active/inactive)
    - Returns (user_data, error_message) tuple for detailed error handling
    """
    user = get_user_by_email(email)
    if not user:
        return None, "User not found"
    
    if not verify_password(password, user["password_hash"]):
        return None, "Invalid password"
    
    if not user["is_active"]:
        return None, "Account is inactive"
    
    return user, ""

# ==================== JWT TOKEN MANAGEMENT ====================
# Functions for creating, verifying, and validating JWT tokens

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token for authenticated users
    - Encodes user data (ID, email, role) into secure token
    - Sets expiration time (default from environment config)
    - Used for stateless authentication in API requests
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Verify and decode JWT token from Authorization header
    - Validates token signature and expiration
    - Extracts user ID, email, and role from token payload
    - Returns user data for authenticated requests
    - Raises HTTPException for invalid tokens
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        logger.debug(f"Received token: {credentials.credentials[:20]}...")
        logger.debug(f"SECRET_KEY exists: {SECRET_KEY is not None}")
        
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        
        logger.debug(f"Decoded payload - user_id_str: {user_id_str}, email: {email}, role: {role}")
        
        if user_id_str is None or email is None:
            logger.debug("Missing user_id or email in token")
            raise credentials_exception
        
        # Convert user_id from string to int
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            logger.debug(f"Invalid user_id format: {user_id_str}")
            raise credentials_exception
            
        return {
            "id": user_id,
            "email": email,
            "role": role
        }
    except PyJWTError as e:
        logger.debug(f"JWT Error: {e}")
        raise credentials_exception

# ==================== FASTAPI DEPENDENCY FUNCTIONS ====================
# Functions used as FastAPI dependencies for route protection

def get_current_user(token_data: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user
    - Validates token and retrieves full user data from database
    - Used as dependency in protected API routes
    - Ensures user still exists and is active
    - Raises HTTPException if user not found
    """
    user = get_user_by_email(token_data["email"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

# ==================== LEGACY CODE (COMMENTED OUT) ====================
# Direct PostgreSQL implementations kept for reference
# These functions were replaced with Supabase equivalents above

"""
# LEGACY PostgreSQL Database Functions (replaced with Supabase)

def get_user_by_email_postgres(email: str) -> Optional[Dict[str, Any]]:
    '''Get user from database by email with profile data using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash, role, is_active, is_verified, created_at FROM users WHERE email = %s",
                (email,)
            )
            user = cur.fetchone()
            
            if user:
                # Get profile data based on role
                if user["role"] == "therapist":
                    profile = get_therapist_profile(user["id"])
                elif user["role"] == "parent":
                    profile = get_parent_profile(user["id"])
                else:
                    profile = None
                
                if profile:
                    user["profile"] = profile
            
            return user
    finally:
        conn.close()

def update_last_login_postgres(user_id: int):
    '''Update user's last login timestamp using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login = NOW() WHERE id = %s",
                (user_id,)
            )
        conn.commit()
    finally:
        conn.close()
"""