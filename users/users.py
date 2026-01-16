import bcrypt
from datetime import datetime
from typing import Optional, Dict, Any
from db import get_supabase_client, format_supabase_response, handle_supabase_error
import logging

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================
# Utility functions for user creation and validation

def _validate_user_role(role: str) -> None:
    """
    Validate user role is supported
    - Ensures only valid roles are accepted
    - Raises ValueError for invalid roles
    """
    if role not in ("therapist", "parent"):
        raise ValueError("Invalid role. Must be 'therapist' or 'parent'")

def _hash_password(password: str) -> str:
    """
    Generate secure password hash using bcrypt
    - Uses bcrypt with salt for secure password storage
    - Returns base64-encoded hash string suitable for database storage
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _prepare_user_data(email: str, password_hash: str, role: str) -> Dict[str, Any]:
    """
    Prepare user data dictionary for database insertion
    - Creates standardized user record structure
    - Sets default values for new user accounts
    """
    return {
        'email': email,
        'password_hash': password_hash,
        'role': role,
        'is_active': True,
        'is_verified': False
    }

def _prepare_therapist_profile_data(user_id: int, email: str, first_name: str, last_name: str, phone: Optional[str]) -> Dict[str, Any]:
    """
    Prepare therapist profile data for database insertion
    - Creates therapist-specific profile structure
    - Includes default values for therapist accounts
    """
    return {
        'user_id': user_id,
        'first_name': first_name or "",
        'last_name': last_name or "",
        'email': email,
        'phone': phone,
        'bio': '',  # Default empty bio
        'is_active': True
    }

def _prepare_parent_profile_data(user_id: int, email: str, first_name: str, last_name: str, 
                                phone: Optional[str], address: Optional[str], emergency_contact: Optional[str]) -> Dict[str, Any]:
    """
    Prepare parent profile data for database insertion
    - Creates parent-specific profile structure
    - Includes parent-specific fields like address and emergency contact
    """
    return {
        'user_id': user_id,
        'first_name': first_name or "",
        'last_name': last_name or "",
        'email': email,
        'phone': phone,
        'address': address,
        'emergency_contact': emergency_contact,
        'is_active': True
    }

def _handle_user_creation_error(error: Exception, email: str) -> None:
    """
    Handle and classify user creation errors
    - Provides specific error messages for different failure types
    - Logs appropriate error information
    - Raises appropriate exceptions for API consumption
    """
    error_msg = str(error).lower()
    if 'unique' in error_msg or 'duplicate' in error_msg:
        logger.error(f"Email already exists: {email}")
        raise ValueError("Email already exists")
    
    logger.error(f"Error creating user {email}: {error}")
    raise Exception(f"Failed to create user: {error}")

# ==================== USER ACCOUNT CREATION ====================
# Functions for creating new user accounts and associated profiles

async def _create_user_record(client, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create the main user record in the users table
    - Handles user account creation
    - Returns created user data with ID
    """
    response = client.table('users').insert(user_data).execute()
    handle_supabase_error(response)
    
    users = format_supabase_response(response)
    if not users:
        raise Exception("Failed to create user - no data returned from database")
    
    return users[0]

async def _create_therapist_profile(client, user_id: int, profile_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Create therapist profile record
    - Links therapist profile to user account
    - Returns created profile data
    """
    try:
        profile_response = client.table('therapists').insert(profile_data).execute()
        handle_supabase_error(profile_response)
        
        profiles = format_supabase_response(profile_response)
        if profiles:
            logger.info(f"Created therapist profile with ID: {profiles[0]['id']}")
            return profiles[0]
        return None
    except Exception as e:
        logger.error(f"Failed to create therapist profile for user {user_id}: {e}")
        return None

async def _create_parent_profile(client, user_id: int, profile_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Create parent profile record
    - Links parent profile to user account
    - Returns created profile data
    """
    try:
        profile_response = client.table('parents').insert(profile_data).execute()
        handle_supabase_error(profile_response)
        
        profiles = format_supabase_response(profile_response)
        if profiles:
            logger.info(f"Created parent profile with ID: {profiles[0]['id']}")
            return profiles[0]
        return None
    except Exception as e:
        logger.error(f"Failed to create parent profile for user {user_id}: {e}")
        return None

def create_user(email: str, password: str, role: str, first_name: str = None, last_name: str = None, 
                phone: str = None, address: str = None, emergency_contact: str = None) -> Dict[str, Any]:
    """
    Create a new user account with associated profile
    
    Args:
        email: User's email address (must be unique)
        password: Plain text password (will be hashed)
        role: User role ('therapist' or 'parent')
        first_name: User's first name (optional, defaults to empty string)
        last_name: User's last name (optional, defaults to empty string)
        phone: Phone number (optional)
        address: Address (for parents only, optional)
        emergency_contact: Emergency contact info (for parents only, optional)
    
    Returns:
        Dictionary containing created user data with associated profile
    
    Raises:
        ValueError: If role is invalid or email already exists
        Exception: If user creation fails for other reasons
    
    Usage:
        - Used by registration endpoint to create new accounts
        - Automatically creates role-specific profile records
        - Handles both therapist and parent account types
        - Provides secure password hashing and storage
    """
    try:
        # Validate inputs
        _validate_user_role(role)
        
        # Prepare data
        password_hash = _hash_password(password)
        user_data = _prepare_user_data(email, password_hash, role)
        
        # Create user account
        client = get_supabase_client()
        user = _create_user_record(client, user_data)
        user_id = user["id"]
        
        logger.info(f"Created user with ID: {user_id}, email: {email}, role: {role}")
        
        # Create role-specific profile
        profile = None
        if role == "therapist":
            profile_data = _prepare_therapist_profile_data(user_id, email, first_name, last_name, phone)
            profile = _create_therapist_profile(client, user_id, profile_data)
        elif role == "parent":
            profile_data = _prepare_parent_profile_data(user_id, email, first_name, last_name, phone, address, emergency_contact)
            profile = _create_parent_profile(client, user_id, profile_data)
        
        # Add profile to user data if created successfully
        if profile:
            user["profile"] = profile
        
        return user
        
    except Exception as e:
        _handle_user_creation_error(e, email)

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional user management functions

# TODO: Implement user update functionality
# def update_user(user_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
#     """Update user account information"""
#     pass

# TODO: Implement user deactivation functionality
# def deactivate_user(user_id: int) -> bool:
#     """Deactivate user account"""
#     pass

# TODO: Implement password change functionality
# def change_user_password(user_id: int, old_password: str, new_password: str) -> bool:
#     """Change user password with verification"""
#     pass

# TODO: Implement email verification functionality
# def verify_user_email(user_id: int, verification_token: str) -> bool:
#     """Verify user email address"""
#     pass

# TODO: Implement user search functionality
# def search_users(search_term: str, role: Optional[str] = None) -> List[Dict[str, Any]]:
#     """Search users by email, name, or other criteria"""
#     pass

# ==================== LEGACY CODE (COMMENTED OUT) ====================
# Direct PostgreSQL implementation kept for reference
# This code was replaced with Supabase equivalents above

"""
# LEGACY PostgreSQL Database Functions (replaced with Supabase)

def create_user_postgres(email: str, password: str, role: str, first_name: str = None, last_name: str = None, 
                phone: str = None, address: str = None, emergency_contact: str = None) -> dict:
    '''
    Create a new user in the database and corresponding therapist/parent record using direct PostgreSQL.
    Returns the created user dict (without password hash).
    Raises psycopg2.IntegrityError if email already exists.
    '''
    if role not in ("therapist", "parent"):
        raise ValueError("Invalid role. Must be 'therapist' or 'parent'")
    
    # Ensure we have required fields
    if not first_name:
        first_name = ""
    if not last_name:
        last_name = ""
    
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    
    try:
        with conn:
            with conn.cursor() as cur:
                # Create user record
                cur.execute(
                    '''
                    INSERT INTO users (email, password_hash, role)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, role, is_active, is_verified, last_login, created_at, updated_at;
                    ''',
                    (email, password_hash, role)
                )
                user = cur.fetchone()
                user_id = user["id"]
                logger.info(f"Created user with ID: {user_id}, email: {email}, role: {role}")
                
                # Create corresponding therapist or parent record
                if role == "therapist":
                    cur.execute(
                        '''
                        INSERT INTO therapists (user_id, first_name, last_name, email, phone, bio, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, user_id, first_name, last_name, email, phone, bio, is_active, created_at, updated_at;
                        ''',
                        (user_id, first_name, last_name, email, phone, '', True)
                    )
                    profile = cur.fetchone()
                    user["profile"] = profile
                    logger.info(f"Created therapist profile with ID: {profile['id']}")
                    
                elif role == "parent":
                    cur.execute(
                        '''
                        INSERT INTO parents (user_id, first_name, last_name, email, phone, address, emergency_contact, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, user_id, first_name, last_name, email, phone, address, emergency_contact, is_active, created_at, updated_at;
                        ''',
                        (user_id, first_name, last_name, email, phone, address, emergency_contact, True)
                    )
                    profile = cur.fetchone()
                    user["profile"] = profile
                    logger.info(f"Created parent profile with ID: {profile['id']}")
                
                conn.commit()
        return user
    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error creating user {email}: {e}")
        conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error creating user {email}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
"""