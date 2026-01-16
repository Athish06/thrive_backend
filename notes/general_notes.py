from datetime import datetime
from typing import Optional, List, Dict, Any
from db import get_supabase_client, format_supabase_response, handle_supabase_error
import logging

logger = logging.getLogger(__name__)

# ==================== GENERAL NOTES CRUD OPERATIONS ====================
# Functions for managing therapist daily notes (not tied to sessions)

async def create_general_note(therapist_id: int, date: str, note_title: Optional[str], note_content: str) -> Optional[Dict[str, Any]]:
    """
    Create a general note for a therapist on a specific date
    
    Args:
        therapist_id: ID of the therapist
        date: Date in YYYY-MM-DD format
        note_title: Optional title for the note
        note_content: Content of the note
    
    Returns:
        Created note data or None if failed
    """
    try:
        client = get_supabase_client()
        
        note_data = {
            "therapist_id": therapist_id,
            "date": date,
            "note_title": note_title,
            "note_content": note_content
        }
        
        response = client.table("notes").insert(note_data).execute()
        handle_supabase_error(response)
        
        notes = format_supabase_response(response)
        if notes:
            logger.info(f"Created general note for therapist {therapist_id} on {date}")
            return notes[0]
        
        return None
        
    except Exception as e:
        logger.error(f"Error creating general note: {e}")
        raise

async def get_notes_by_date(therapist_id: int, date: str) -> List[Dict[str, Any]]:
    """
    Get all general notes for a therapist on a specific date
    
    Args:
        therapist_id: ID of the therapist
        date: Date in YYYY-MM-DD format
    
    Returns:
        List of notes for the date
    """
    try:
        client = get_supabase_client()
        
        response = client.table("notes").select("*").eq("therapist_id", therapist_id).eq("date", date).execute()
        handle_supabase_error(response)
        
        notes = format_supabase_response(response)
        return notes
        
    except Exception as e:
        logger.error(f"Error fetching notes for date {date}: {e}")
        raise

async def update_general_note(note_id: int, therapist_id: int, note_title: Optional[str] = None, note_content: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Update a general note
    
    Args:
        note_id: ID of the note to update
        therapist_id: ID of the therapist (for ownership verification)
        note_title: Optional new title
        note_content: Optional new content
    
    Returns:
        Updated note data or None if failed
    """
    try:
        client = get_supabase_client()
        
        # Verify ownership
        check_response = client.table("notes").select("*").eq("notes_id", note_id).eq("therapist_id", therapist_id).execute()
        handle_supabase_error(check_response)
        
        existing_notes = format_supabase_response(check_response)
        if not existing_notes:
            logger.warning(f"Note {note_id} not found or access denied for therapist {therapist_id}")
            return None
        
        # Prepare update data
        update_data = {"last_edited_at": datetime.utcnow().isoformat()}
        if note_title is not None:
            update_data["note_title"] = note_title
        if note_content is not None:
            update_data["note_content"] = note_content
        
        # Update note
        response = client.table("notes").update(update_data).eq("notes_id", note_id).execute()
        handle_supabase_error(response)
        
        updated_notes = format_supabase_response(response)
        if updated_notes:
            logger.info(f"Updated general note {note_id}")
            return updated_notes[0]
        
        return None
        
    except Exception as e:
        logger.error(f"Error updating note {note_id}: {e}")
        raise

async def delete_general_note(note_id: int, therapist_id: int) -> bool:
    """
    Delete a general note
    
    Args:
        note_id: ID of the note to delete
        therapist_id: ID of the therapist (for ownership verification)
    
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        client = get_supabase_client()
        
        # Delete with ownership check
        response = client.table("notes").delete().eq("notes_id", note_id).eq("therapist_id", therapist_id).execute()
        handle_supabase_error(response)
        
        deleted_notes = format_supabase_response(response)
        if deleted_notes:
            logger.info(f"Deleted general note {note_id}")
            return True
        
        logger.warning(f"Note {note_id} not found or access denied for therapist {therapist_id}")
        return False
        
    except Exception as e:
        logger.error(f"Error deleting note {note_id}: {e}")
        raise

async def get_notes_by_date_range(therapist_id: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Get all general notes for a therapist within a date range
    
    Args:
        therapist_id: ID of the therapist
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        List of notes within the date range
    """
    try:
        client = get_supabase_client()
        
        response = client.table("notes").select("*").eq("therapist_id", therapist_id).gte("date", start_date).lte("date", end_date).order("date", desc=True).execute()
        handle_supabase_error(response)
        
        notes = format_supabase_response(response)
        return notes
        
    except Exception as e:
        logger.error(f"Error fetching notes for date range {start_date} to {end_date}: {e}")
        raise
