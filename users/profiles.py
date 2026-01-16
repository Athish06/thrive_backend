from datetime import datetime
from typing import Optional, Dict, Any, List
from db import get_supabase_client, format_supabase_response, handle_supabase_error
import logging

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================
# Utility functions for profile operations

def _validate_therapist_update_fields(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and filter therapist profile update fields
    - Only allows updating specific therapist fields
    - Returns filtered update data
    """
    allowed_fields = ['first_name', 'last_name', 'phone', 'bio']
    update_data = {}
    
    for field in allowed_fields:
        if field in kwargs and kwargs[field] is not None:
            update_data[field] = kwargs[field]
    
    return update_data

def _validate_parent_update_fields(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and filter parent profile update fields
    - Only allows updating specific parent fields
    - Returns filtered update data
    """
    allowed_fields = ['first_name', 'last_name', 'phone', 'address', 'emergency_contact']
    update_data = {}
    
    for field in allowed_fields:
        if field in kwargs and kwargs[field] is not None:
            update_data[field] = kwargs[field]
    
    return update_data

def _add_timestamp_to_update(update_data: Dict[str, Any]) -> None:
    """
    Add current timestamp to update data
    - Modifies update_data dictionary in place
    - Ensures updated_at field is set for all updates
    """
    update_data['updated_at'] = datetime.utcnow().isoformat()

def _handle_profile_error(operation: str, user_id: int, error: Exception) -> None:
    """
    Handle and log profile operation errors
    - Provides consistent error logging format
    - Includes operation context and user identification
    """
    logger.error(f"Error {operation} profile for user {user_id}: {error}")

def _get_profile_by_user_id(table_name: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Generic function to get profile by user_id from any table
    - Reusable for both therapist and parent profile retrieval
    - Handles Supabase query and error handling
    """
    try:
        client = get_supabase_client()
        
        response = client.table(table_name).select('*').eq('user_id', user_id).execute()
        handle_supabase_error(response)
        
        profiles = format_supabase_response(response)
        if profiles:
            return profiles[0]
        return None
    except Exception as e:
        _handle_profile_error(f"getting {table_name}", user_id, e)
        return None

def _update_profile_by_user_id(table_name: str, user_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Generic function to update profile by user_id in any table
    - Reusable for both therapist and parent profile updates
    - Handles Supabase update and error handling
    """
    try:
        client = get_supabase_client()
        
        response = client.table(table_name).update(update_data).eq('user_id', user_id).execute()
        handle_supabase_error(response)
        
        profiles = format_supabase_response(response)
        if profiles:
            logger.info(f"Updated {table_name} profile for user {user_id}")
            return profiles[0]
        return None
    except Exception as e:
        _handle_profile_error(f"updating {table_name}", user_id, e)
        return None

# ==================== THERAPIST PROFILE OPERATIONS ====================
# Functions for managing therapist profile data

def get_therapist_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get therapist profile by user_id using Supabase
    
    Args:
        user_id: The user ID to look up therapist profile for
    
    Returns:
        Dictionary containing therapist profile data, or None if not found
    
    Usage:
        - Used by API endpoints to retrieve therapist information
        - Returns complete therapist profile including bio, contact info
        - Returns None if user has no therapist profile
    """
    return _get_profile_by_user_id('therapists', user_id)

def update_therapist_profile(user_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update therapist profile using Supabase
    
    Args:
        user_id: The user ID of the therapist to update
        **kwargs: Fields to update (first_name, last_name, phone, bio)
    
    Returns:
        Dictionary containing updated therapist profile data, or None if update failed
    
    Usage:
        - Used by profile update endpoints to modify therapist information
        - Only updates fields that are provided and not None
        - Automatically sets updated_at timestamp
        - Returns current profile if no valid fields provided
    """
    update_data = _validate_therapist_update_fields(kwargs)
    
    if not update_data:
        return get_therapist_profile(user_id)
    
    _add_timestamp_to_update(update_data)
    return _update_profile_by_user_id('therapists', user_id, update_data)

def get_all_therapist_profiles() -> List[Dict[str, Any]]:
    """
    Get all active therapist profiles
    
    Returns:
        List of dictionaries containing all therapist profile data
    
    Usage:
        - Used by admin interfaces to list all therapists
        - Returns only active therapist profiles
        - Useful for assignment and management operations
    """
    try:
        client = get_supabase_client()
        
        response = client.table('therapists').select('*').eq('is_active', True).execute()
        handle_supabase_error(response)
        
        return format_supabase_response(response)
    except Exception as e:
        logger.error(f"Error getting all therapist profiles: {e}")
        return []

# ==================== PARENT PROFILE OPERATIONS ====================
# Functions for managing parent profile data

def get_parent_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get parent profile by user_id using Supabase
    
    Args:
        user_id: The user ID to look up parent profile for
    
    Returns:
        Dictionary containing parent profile data, or None if not found
    
    Usage:
        - Used by API endpoints to retrieve parent information
        - Returns complete parent profile including address, emergency contact
        - Returns None if user has no parent profile
    """
    return _get_profile_by_user_id('parents', user_id)

def update_parent_profile(user_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update parent profile using Supabase
    
    Args:
        user_id: The user ID of the parent to update
        **kwargs: Fields to update (first_name, last_name, phone, address, emergency_contact)
    
    Returns:
        Dictionary containing updated parent profile data, or None if update failed
    
    Usage:
        - Used by profile update endpoints to modify parent information
        - Only updates fields that are provided and not None
        - Automatically sets updated_at timestamp
        - Returns current profile if no valid fields provided
    """
    update_data = _validate_parent_update_fields(kwargs)
    
    if not update_data:
        return get_parent_profile(user_id)
    
    _add_timestamp_to_update(update_data)
    return _update_profile_by_user_id('parents', user_id, update_data)

def get_all_parent_profiles() -> List[Dict[str, Any]]:
    """
    Get all active parent profiles
    
    Returns:
        List of dictionaries containing all parent profile data
    
    Usage:
        - Used by admin interfaces to list all parents
        - Returns only active parent profiles
        - Useful for reporting and management operations
    """
    try:
        client = get_supabase_client()
        
        response = client.table('parents').select('*').eq('is_active', True).execute()
        handle_supabase_error(response)
        
        return format_supabase_response(response)
    except Exception as e:
        logger.error(f"Error getting all parent profiles: {e}")
        return []

# ==================== PROFILE SEARCH & UTILITY FUNCTIONS ====================
# Functions for searching and managing profiles across types

def get_profile_by_user_id_and_role(user_id: int, role: str) -> Optional[Dict[str, Any]]:
    """
    Get profile data based on user ID and role
    
    Args:
        user_id: The user ID to look up
        role: The user role ('therapist' or 'parent')
    
    Returns:
        Dictionary containing profile data for the specified role, or None if not found
    
    Usage:
        - Used when user role is known and profile data is needed
        - Automatically routes to correct profile table based on role
        - Simplifies profile retrieval in authentication contexts
    """
    if role == 'therapist':
        return get_therapist_profile(user_id)
    elif role == 'parent':
        return get_parent_profile(user_id)
    else:
        logger.warning(f"Invalid role '{role}' for user {user_id}")
        return None

def search_profiles_by_name(search_term: str, role: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search profiles by first name or last name
    
    Args:
        search_term: Term to search for in first_name or last_name
        role: Optional role filter ('therapist' or 'parent')
    
    Returns:
        List of matching profile dictionaries
    
    Usage:
        - Used by search functionality to find users by name
        - Case-insensitive search across first and last names
        - Can be filtered by role or search all profiles
    """
    results = []
    search_term = search_term.lower()
    
    try:
        client = get_supabase_client()
        
        if role == 'therapist' or role is None:
            response = client.table('therapists').select('*').eq('is_active', True).execute()
            handle_supabase_error(response)
            
            therapists = format_supabase_response(response)
            for therapist in therapists:
                first_name = (therapist.get('first_name') or '').lower()
                last_name = (therapist.get('last_name') or '').lower()
                if search_term in first_name or search_term in last_name:
                    therapist['role'] = 'therapist'
                    results.append(therapist)
        
        if role == 'parent' or role is None:
            response = client.table('parents').select('*').eq('is_active', True).execute()
            handle_supabase_error(response)
            
            parents = format_supabase_response(response)
            for parent in parents:
                first_name = (parent.get('first_name') or '').lower()
                last_name = (parent.get('last_name') or '').lower()
                if search_term in first_name or search_term in last_name:
                    parent['role'] = 'parent'
                    results.append(parent)
    
    except Exception as e:
        logger.error(f"Error searching profiles by name '{search_term}': {e}")
    
    return results

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional profile management functions

# TODO: Implement profile deactivation functionality
# def deactivate_profile(user_id: int, role: str) -> bool:
#     """Deactivate user profile"""
#     pass

# TODO: Implement profile photo upload functionality
# def update_profile_photo(user_id: int, photo_url: str) -> Optional[Dict[str, Any]]:
#     """Update profile photo URL"""
#     pass

# TODO: Implement profile completion status
# def get_profile_completion_status(user_id: int, role: str) -> Dict[str, Any]:
#     """Check which profile fields are complete"""
#     pass

# TODO: Implement profile export functionality
# def export_profile_data(user_id: int, role: str) -> Dict[str, Any]:
#     """Export complete profile data for user"""
#     pass

# ==================== LEGACY CODE (COMMENTED OUT) ====================
# Direct PostgreSQL implementation kept for reference
# This code was replaced with Supabase equivalents above

"""
# LEGACY PostgreSQL Database Functions (replaced with Supabase)

def get_therapist_profile_postgres(user_id: int) -> Optional[Dict[str, Any]]:
    '''Get therapist profile by user_id using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                '''
                SELECT id, user_id, first_name, last_name, email, phone, bio, 
                       is_active, created_at, updated_at
                FROM therapists 
                WHERE user_id = %s
                ''',
                (user_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def get_parent_profile_postgres(user_id: int) -> Optional[Dict[str, Any]]:
    '''Get parent profile by user_id using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                '''
                SELECT id, user_id, first_name, last_name, email, phone, address, 
                       emergency_contact, is_active, created_at, updated_at
                FROM parents 
                WHERE user_id = %s
                ''',
                (user_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def update_therapist_profile_postgres(user_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    '''Update therapist profile using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Build dynamic update query
                update_fields = []
                values = []
                
                allowed_fields = ['first_name', 'last_name', 'phone', 'bio']
                for field in allowed_fields:
                    if field in kwargs and kwargs[field] is not None:
                        update_fields.append(f"{field} = %s")
                        values.append(kwargs[field])
                
                if not update_fields:
                    return get_therapist_profile(user_id)
                
                # Add updated_at
                update_fields.append("updated_at = NOW()")
                values.append(user_id)
                
                query = f'''
                    UPDATE therapists 
                    SET {', '.join(update_fields)}
                    WHERE user_id = %s
                    RETURNING id, user_id, first_name, last_name, email, phone, bio, 
                             is_active, created_at, updated_at
                '''
                
                cur.execute(query, values)
                return cur.fetchone()
    finally:
        conn.close()

def update_parent_profile_postgres(user_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    '''Update parent profile using direct PostgreSQL'''
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Build dynamic update query
                update_fields = []
                values = []
                
                allowed_fields = ['first_name', 'last_name', 'phone', 'address', 'emergency_contact']
                for field in allowed_fields:
                    if field in kwargs and kwargs[field] is not None:
                        update_fields.append(f"{field} = %s")
                        values.append(kwargs[field])
                
                if not update_fields:
                    return get_parent_profile(user_id)
                
                # Add updated_at
                update_fields.append("updated_at = NOW()")
                values.append(user_id)
                
                query = f'''
                    UPDATE parents 
                    SET {', '.join(update_fields)}
                    WHERE user_id = %s
                    RETURNING id, user_id, first_name, last_name, email, phone, address, 
                             emergency_contact, is_active, created_at, updated_at
                '''
                
                cur.execute(query, values)
                return cur.fetchone()
    finally:
        conn.close()
"""