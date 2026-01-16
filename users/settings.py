from datetime import datetime
from typing import Optional, Dict, Any, List
from db import get_supabase_client, format_supabase_response, handle_supabase_error
import logging
import json

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================
# Utility functions for settings operations

def _add_timestamp_to_update(update_data: Dict[str, Any]) -> None:
    """
    Add current timestamp to update data
    - Modifies update_data dictionary in place
    - Ensures updated_at field is set for all updates
    """
    update_data['updated_at'] = datetime.utcnow().isoformat()

def _handle_settings_error(operation: str, user_id: int, error: Exception) -> None:
    """
    Handle and log settings operation errors
    - Provides consistent error logging format
    - Includes operation context and user identification
    """
    logger.error(f"Error {operation} settings for user {user_id}: {error}")

# ==================== THERAPIST SETTINGS OPERATIONS ====================
# Functions for managing therapist settings data

def get_therapist_settings(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get therapist settings by user_id using Supabase

    Args:
        user_id: The user ID to look up therapist settings for

    Returns:
        Dictionary containing therapist settings data, or None if not found

    Usage:
        - Used by API endpoints to retrieve therapist settings
        - Returns complete therapist settings including profile_settings and account_settings
        - Returns None if user has no therapist profile
    """
    try:
        client = get_supabase_client()

        response = client.table('therapists').select('id, user_id, profile_settings, account_settings, updated_at').eq('user_id', user_id).execute()
        handle_supabase_error(response)

        settings = format_supabase_response(response)
        if settings:
            therapist_data = settings[0]
            # Parse JSONB fields
            profile_section = therapist_data.get('profile_settings')
            account_section = therapist_data.get('account_settings')

            # Ensure they are dictionaries (JSONB columns return dicts directly)
            if not isinstance(profile_section, dict):
                profile_section = {}
            if not isinstance(account_section, dict):
                account_section = {}

            return {
                'id': therapist_data.get('id'),
                'user_id': therapist_data.get('user_id'),
                'profile_section': profile_section or {},
                'account_section': account_section or {},
                'updated_at': therapist_data.get('updated_at')
            }
        return None
    except Exception as e:
        _handle_settings_error("getting", user_id, e)
        return None

def update_therapist_profile_settings(user_id: int, settings_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update therapist profile_settings settings using Supabase

    Args:
        user_id: The user ID of the therapist to update
        settings_data: Dictionary containing profile settings to update

    Returns:
        Dictionary containing updated therapist settings data, or None if update failed

    Usage:
        - Used by settings update endpoints to modify therapist profile settings
        - Only updates the profile_settings JSONB field
        - Automatically sets updated_at timestamp
    """
    try:
        client = get_supabase_client()

        # Prepare update data
        update_data = {
            'profile_settings': settings_data
        }
        _add_timestamp_to_update(update_data)

        response = client.table('therapists').update(update_data).eq('user_id', user_id).execute()
        handle_supabase_error(response)

        settings = format_supabase_response(response)
        if settings:
            logger.info(f"Updated profile settings for therapist user {user_id}")
            therapist_data = settings[0]
            return {
                'id': therapist_data.get('id'),
                'user_id': therapist_data.get('user_id'),
                'profile_section': therapist_data.get('profile_settings') or {},
                'account_section': therapist_data.get('account_settings') or {},
                'updated_at': therapist_data.get('updated_at')
            }
        return None
    except Exception as e:
        _handle_settings_error("updating profile", user_id, e)
        return None

def update_therapist_account_settings(user_id: int, settings_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update therapist account_settings settings using Supabase

    Args:
        user_id: The user ID of the therapist to update
        settings_data: Dictionary containing account settings to update

    Returns:
        Dictionary containing updated therapist settings data, or None if update failed

    Usage:
        - Used by settings update endpoints to modify therapist account settings
        - Only updates the account_settings JSONB field
        - Automatically sets updated_at timestamp
    """
    try:
        client = get_supabase_client()

        # Prepare update data
        update_data = {
            'account_settings': settings_data
        }
        _add_timestamp_to_update(update_data)

        response = client.table('therapists').update(update_data).eq('user_id', user_id).execute()
        handle_supabase_error(response)

        settings = format_supabase_response(response)
        if settings:
            logger.info(f"Updated account settings for therapist user {user_id}")
            therapist_data = settings[0]
            return {
                'id': therapist_data.get('id'),
                'user_id': therapist_data.get('user_id'),
                'profile_section': therapist_data.get('profile_settings') or {},
                'account_section': therapist_data.get('account_settings') or {},
                'updated_at': therapist_data.get('updated_at')
            }
        return None
    except Exception as e:
        _handle_settings_error("updating account", user_id, e)
        return None

def get_therapist_profile_settings(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get only the profile_settings settings for a therapist

    Args:
        user_id: The user ID to look up therapist profile settings for

    Returns:
        Dictionary containing therapist profile settings, or None if not found
    """
    settings = get_therapist_settings(user_id)
    if settings:
        return settings.get('profile_section', {})
    return None

def get_therapist_account_settings(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get only the account_section settings for a therapist

    Args:
        user_id: The user ID to look up therapist account settings for

    Returns:
        Dictionary containing therapist account settings, or None if not found
    """
    settings = get_therapist_settings(user_id)
    if settings:
        return settings.get('account_section', {})
    return None