import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from jwt import PyJWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import get_supabase_client, format_supabase_response, handle_supabase_error
from users.profiles import get_therapist_profile, get_parent_profile
import logging

# ==================== CONFIGURATION & SETUP ====================

load_dotenv()
logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# FastAPI Security
security = HTTPBearer()

# Authentication error messages
AUTH_ERROR_MESSAGES = {
    "user_not_found": "User not found",
    "invalid_password": "Invalid password", 
    "account_inactive": "Account is inactive",
    "invalid_credentials": "Could not validate credentials",
    "token_expired": "Token has expired",
    "user_not_found_token": "User not found"
}

# ==================== HELPER FUNCTIONS ====================
# Utility functions for authentication and user management

def _validate_jwt_config() -> None:
    """
    Validate JWT configuration on startup
    - Ensures required environment variables are set
    - Raises ValueError if configuration is incomplete
    """
    if not SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY environment variable is required")
    if not ALGORITHM:
        raise ValueError("JWT_ALGORITHM environment variable is required")

def _create_credentials_exception(detail: str = None) -> HTTPException:
    """
    Create standardized credentials exception
    - Returns consistent HTTP 401 exception for authentication failures
    - Includes proper WWW-Authenticate header
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail or AUTH_ERROR_MESSAGES["invalid_credentials"],
        headers={"WWW-Authenticate": "Bearer"},
    )

def _get_user_profile_by_role(user_id: int, role: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile based on role
    - Routes to appropriate profile function based on user role
    - Returns profile data or None if not found
    """
    if role == "therapist":
        return get_therapist_profile(user_id)
    elif role == "parent":
        return get_parent_profile(user_id)
    else:
        logger.warning(f"Unknown role '{role}' for user {user_id}")
        return None

def _enhance_user_with_profile(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance user data with profile information
    - Adds profile data to user dictionary based on role
    - Returns enhanced user data
    """
    profile = _get_user_profile_by_role(user["id"], user["role"])
    if profile:
        user["profile"] = profile
    return user

def _validate_user_status(user: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate user account status
    - Checks if user account is active and verified
    - Returns (is_valid, error_message) tuple
    """
    if not user.get("is_active", False):
        return False, AUTH_ERROR_MESSAGES["account_inactive"]
    
    # Additional status checks can be added here
    # if not user.get("is_verified", False):
    #     return False, "Account not verified"
    
    return True, ""

def _log_authentication_attempt(email: str, success: bool, error_msg: str = None) -> None:
    """
    Log authentication attempts for security monitoring
    - Records successful and failed login attempts
    - Includes error details for failed attempts
    """
    if success:
        logger.info(f"Successful authentication for email: {email}")
    else:
        logger.warning(f"Failed authentication for email: {email}, Error: {error_msg}")

def _create_token_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create JWT token payload from user data
    - Includes essential user information in token
    - Returns dictionary ready for JWT encoding
    """
    return {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "is_active": user.get("is_active", True)
    }

def _calculate_token_expiry(expires_delta: Optional[timedelta] = None) -> datetime:
    """
    Calculate token expiration time
    - Uses provided delta or default expiration time
    - Returns UTC datetime for token expiry
    """
    if expires_delta:
        return datetime.utcnow() + expires_delta
    else:
        return datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

# ==================== PASSWORD MANAGEMENT ====================
# Functions for password verification and security

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify plain text password against hashed password
    
    Args:
        plain_password: The plain text password to verify
        hashed_password: The stored hashed password
    
    Returns:
        True if password matches, False otherwise
    
    Usage:
        - Used during login authentication process
        - Compares user input with stored password hash
        - Uses bcrypt for secure password verification
    """
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

def hash_password(plain_password: str) -> str:
    """
    Hash a plain text password using bcrypt
    
    Args:
        plain_password: The plain text password to hash
    
    Returns:
        Base64-encoded hash string suitable for database storage
    
    Usage:
        - Used when creating new user accounts
        - Used when users change their passwords
        - Provides secure password storage
    """
    try:
        return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error hashing password: {e}")
        raise HTTPException(status_code=500, detail="Error processing password")

# ==================== USER RETRIEVAL & AUTHENTICATION ====================
# Functions for user lookup and authentication

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Get user from database by email with profile data using Supabase
    
    Args:
        email: User's email address to look up
    
    Returns:
        Dictionary containing user data with profile information, or None if not found
    
    Usage:
        - Used during authentication process to fetch user data
        - Automatically includes role-specific profile information
        - Returns None if user doesn't exist in database
        - Used by login and token verification processes
    """
    try:
        client = get_supabase_client()
        
        # Get user data using Supabase
        response = client.table('users').select('*').eq('email', email).execute()
        handle_supabase_error(response)
        
        users = format_supabase_response(response)
        if not users:
            return None
            
        user = users[0]
        
        # Enhance user with profile data
        return _enhance_user_with_profile(user)
        
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {e}")
        return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get user from database by ID with profile data
    
    Args:
        user_id: User's ID to look up
    
    Returns:
        Dictionary containing user data with profile information, or None if not found
    
    Usage:
        - Used for token verification and user data refresh
        - Automatically includes role-specific profile information
        - Returns None if user doesn't exist or is inactive
    """
    try:
        client = get_supabase_client()
        
        response = client.table('users').select('*').eq('id', user_id).execute()
        handle_supabase_error(response)
        
        users = format_supabase_response(response)
        if not users:
            return None
            
        user = users[0]
        
        # Enhance user with profile data
        return _enhance_user_with_profile(user)
        
    except Exception as e:
        logger.error(f"Error getting user by ID {user_id}: {e}")
        return None

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate user with email and password (simple version)
    
    Args:
        email: User's email address
        password: Plain text password
    
    Returns:
        User data dictionary if authentication successful, None otherwise
    
    Usage:
        - Simple authentication without detailed error messages
        - Used when only success/failure result is needed
        - Performs all standard authentication checks
    """
    user = get_user_by_email(email)
    if not user:
        return None
    
    if not verify_password(password, user["password_hash"]):
        return None
    
    is_valid, _ = _validate_user_status(user)
    if not is_valid:
        return None
    
    return user

def authenticate_user_detailed(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Authenticate user with detailed error messages using Supabase
    
    Args:
        email: User's email address
        password: Plain text password
    
    Returns:
        Tuple containing (user_data, error_message)
        - user_data: User dictionary if successful, None if failed
        - error_message: Empty string if successful, descriptive error if failed
    
    Usage:
        - Used by login endpoints that need to provide specific error messages
        - Helps distinguish between different authentication failure reasons
        - Provides better user experience with clear error feedback
    """
    # Check if user exists
    user = get_user_by_email(email)
    if not user:
        error_msg = AUTH_ERROR_MESSAGES["user_not_found"]
        _log_authentication_attempt(email, False, error_msg)
        return None, error_msg
    
    # Verify password
    if not verify_password(password, user["password_hash"]):
        error_msg = AUTH_ERROR_MESSAGES["invalid_password"]
        _log_authentication_attempt(email, False, error_msg)
        return None, error_msg
    
    # Check user status
    is_valid, error_msg = _validate_user_status(user)
    if not is_valid:
        _log_authentication_attempt(email, False, error_msg)
        return None, error_msg
    
    # Authentication successful
    _log_authentication_attempt(email, True)
    return user, ""

# ==================== JWT TOKEN MANAGEMENT ====================
# Functions for creating and verifying JWT tokens

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token with user data
    
    Args:
        data: Dictionary containing user data to encode in token
        expires_delta: Optional custom expiration time delta
    
    Returns:
        JWT token string
    
    Usage:
        - Used after successful authentication to create session token
        - Token contains user ID, email, role, and expiration time
        - Used by login endpoints to provide authentication token
        - Default expiration can be overridden with expires_delta parameter
    """
    try:
        _validate_jwt_config()
        
        to_encode = data.copy()
        expire = _calculate_token_expiry(expires_delta)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        
        logger.info(f"Created access token for user: {data.get('email', 'unknown')}")
        return encoded_jwt
        
    except Exception as e:
        logger.error(f"Error creating access token: {e}")
        raise HTTPException(status_code=500, detail="Error creating authentication token")

def create_user_token(user: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT token for authenticated user
    
    Args:
        user: User data dictionary from authentication
        expires_delta: Optional custom expiration time delta
    
    Returns:
        JWT token string
    
    Usage:
        - Convenience function to create token from user object
        - Automatically extracts necessary data for token payload
        - Used after successful authentication
    """
    token_data = _create_token_payload(user)
    return create_access_token(token_data, expires_delta)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Verify JWT token and extract user data
    
    Args:
        credentials: HTTP Bearer token from request header
    
    Returns:
        Dictionary containing user data from token
    
    Raises:
        HTTPException: If token is invalid, expired, or malformed
    
    Usage:
        - Used as FastAPI dependency for protected routes
        - Automatically extracts and validates JWT token from request
        - Returns user data for use in endpoint functions
        - Raises appropriate HTTP exceptions for invalid tokens
    """
    try:
        _validate_jwt_config()
        
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Extract user data from token
        user_id: int = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        
        if user_id is None or email is None:
            logger.warning(f"Invalid token payload: missing user_id or email")
            raise _create_credentials_exception()
            
        return {
            "id": user_id,
            "email": email,
            "role": role,
            "is_active": payload.get("is_active", True)
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning(f"Expired token attempted access")
        raise _create_credentials_exception(AUTH_ERROR_MESSAGES["token_expired"])
    except PyJWTError as e:
        logger.warning(f"Invalid token: {e}")
        raise _create_credentials_exception()
    except Exception as e:
        logger.error(f"Unexpected error verifying token: {e}")
        raise _create_credentials_exception()

def decode_token_without_verification(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode JWT token without signature verification (for debugging)
    
    Args:
        token: JWT token string to decode
    
    Returns:
        Dictionary containing token payload, or None if invalid
    
    Usage:
        - Used for debugging and token inspection
        - Does NOT verify token signature or expiration
        - Should NOT be used for authentication purposes
        - Useful for troubleshooting token issues
    """
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except Exception as e:
        logger.error(f"Error decoding token: {e}")
        return None

# ==================== FASTAPI DEPENDENCIES ====================
# FastAPI dependency functions for route protection

def get_current_user(token_data: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
    """
    Get current authenticated user from token data
    
    Args:
        token_data: User data extracted from verified JWT token
    
    Returns:
        Complete user data dictionary with profile information
    
    Raises:
        HTTPException: If user is not found or account is inactive
    
    Usage:
        - Used as FastAPI dependency for routes requiring user context
        - Provides complete user object including profile data
        - Automatically handles token verification and user lookup
        - Can be used to access current user in protected endpoints
    """
    user = get_user_by_email(token_data["email"])
    if user is None:
        logger.warning(f"Token valid but user not found: {token_data['email']}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_ERROR_MESSAGES["user_not_found_token"]
        )
    
    # Additional validation
    is_valid, error_msg = _validate_user_status(user)
    if not is_valid:
        logger.warning(f"User account status invalid: {token_data['email']}, {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )
    
    return user

def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
    """
    Get current user if token is provided (optional authentication)
    
    Args:
        credentials: Optional HTTP Bearer token from request header
    
    Returns:
        User data dictionary if valid token provided, None otherwise
    
    Usage:
        - Used for endpoints that work with or without authentication
        - Provides user context when available
        - Does not raise exceptions for missing tokens
        - Useful for endpoints with optional user features
    """
    if credentials is None:
        return None
    
    try:
        token_data = verify_token(credentials)
        return get_user_by_email(token_data["email"])
    except HTTPException:
        return None

def require_role(allowed_roles: list) -> callable:
    """
    Create dependency function that requires specific user roles
    
    Args:
        allowed_roles: List of allowed user roles for the endpoint
    
    Returns:
        FastAPI dependency function that validates user role
    
    Usage:
        - Used to create role-based access control dependencies
        - Can be applied to routes that require specific user types
        - Example: @app.get("/admin", dependencies=[Depends(require_role(["admin"]))])
    """
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker

# ==================== USER SESSION MANAGEMENT ====================
# Functions for managing user sessions and login tracking

def update_last_login(user_id: int) -> bool:
    """
    Update user's last login timestamp using Supabase
    
    Args:
        user_id: ID of the user to update
    
    Returns:
        True if update successful, False otherwise
    
    Usage:
        - Called after successful authentication to track login activity
        - Used for user activity monitoring and analytics
        - Helps identify inactive accounts
        - Updates timestamp in UTC format for consistency
    """
    try:
        client = get_supabase_client()
        
        response = client.table('users').update({
            'last_login': datetime.utcnow().isoformat()
        }).eq('id', user_id).execute()
        
        handle_supabase_error(response)
        logger.info(f"Updated last login for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating last login for user {user_id}: {e}")
        return False

def get_user_login_history(user_id: int, limit: int = 10) -> list:
    """
    Get user login history (placeholder for future implementation)
    
    Args:
        user_id: ID of the user
        limit: Maximum number of login records to return
    
    Returns:
        List of login history records
    
    Usage:
        - Future feature for tracking user login patterns
        - Can be used for security monitoring
        - Helps detect suspicious login activity
    """
    # TODO: Implement login history tracking
    # This would require a separate login_history table
    logger.info(f"Login history requested for user {user_id} (not implemented)")
    return []

def invalidate_user_sessions(user_id: int) -> bool:
    """
    Invalidate all active sessions for a user (placeholder)
    
    Args:
        user_id: ID of the user whose sessions should be invalidated
    
    Returns:
        True if sessions invalidated successfully
    
    Usage:
        - Used when user changes password or account is compromised
        - Forces user to log in again on all devices
        - Enhanced security feature for session management
    """
    # TODO: Implement session invalidation
    # This would require a session tracking mechanism
    logger.info(f"Session invalidation requested for user {user_id} (not implemented)")
    return True

# ==================== AUTHENTICATION UTILITIES ====================
# Utility functions for authentication-related operations

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password strength requirements
    
    Args:
        password: Plain text password to validate
    
    Returns:
        Tuple containing (is_valid, error_message)
    
    Usage:
        - Used during user registration and password changes
        - Enforces password security policies
        - Provides specific feedback on password requirements
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    # Additional checks can be added here
    # if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
    #     return False, "Password must contain at least one special character"
    
    return True, ""

def generate_password_reset_token(user_id: int) -> str:
    """
    Generate password reset token for user
    
    Args:
        user_id: ID of the user requesting password reset
    
    Returns:
        JWT token for password reset
    
    Usage:
        - Used for password reset functionality
        - Token contains user ID and short expiration time
        - Should be sent via secure channel (email)
    """
    try:
        _validate_jwt_config()
        
        payload = {
            "sub": user_id,
            "type": "password_reset",
            "exp": datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        }
        
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Generated password reset token for user {user_id}")
        return token
        
    except Exception as e:
        logger.error(f"Error generating password reset token: {e}")
        raise HTTPException(status_code=500, detail="Error generating reset token")

def verify_password_reset_token(token: str) -> Optional[int]:
    """
    Verify password reset token and extract user ID
    
    Args:
        token: Password reset token to verify
    
    Returns:
        User ID if token is valid, None otherwise
    
    Usage:
        - Used to validate password reset requests
        - Ensures token is valid and not expired
        - Returns user ID for password reset operation
    """
    try:
        _validate_jwt_config()
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "password_reset":
            logger.warning("Invalid token type for password reset")
            return None
        
        user_id = payload.get("sub")
        if user_id:
            logger.info(f"Valid password reset token for user {user_id}")
        
        return user_id
        
    except jwt.ExpiredSignatureError:
        logger.warning("Expired password reset token")
        return None
    except PyJWTError as e:
        logger.warning(f"Invalid password reset token: {e}")
        return None

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional authentication features

# TODO: Implement multi-factor authentication
# def setup_mfa(user_id: int, mfa_type: str) -> Dict[str, Any]:
#     """Setup multi-factor authentication for user"""
#     pass

# TODO: Implement OAuth integration
# def authenticate_with_oauth(provider: str, oauth_token: str) -> Optional[Dict[str, Any]]:
#     """Authenticate user using OAuth provider"""
#     pass

# TODO: Implement rate limiting for authentication
# def check_auth_rate_limit(email: str) -> bool:
#     """Check if authentication attempts are within rate limits"""
#     pass

# TODO: Implement session management
# def create_user_session(user_id: int, device_info: Dict[str, Any]) -> str:
#     """Create and track user session"""
#     pass

# TODO: Implement account lockout
# def check_account_lockout(email: str) -> Tuple[bool, int]:
#     """Check if account is locked due to failed attempts"""
#     pass

# ==================== LEGACY CODE (COMMENTED OUT) ====================
# Direct PostgreSQL implementation kept for reference
# This code was replaced with Supabase equivalents above

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
