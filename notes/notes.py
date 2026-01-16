from typing import List, Optional
from datetime import date, datetime, time
from pydantic import BaseModel
import logging
from db import get_supabase_client

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== DATA MODELS ====================
# Pydantic models for session notes data validation and serialization

class SessionNoteCreate(BaseModel):
    """
    Data model for creating new session notes
    - session_date: Date of the therapy session
    - note_content: Main content/body of the session note
    - note_title: Optional title for the note
    - session_time: Optional specific time when session occurred
    """
    session_date: date
    note_content: str
    note_title: Optional[str] = None
    session_time: Optional[time] = None

class SessionNoteResponse(BaseModel):
    """
    Data model for session note responses from database
    - Complete note information including metadata
    - Used for API responses and data transfer
    - Includes creation and modification timestamps
    """
    notes_id: int
    therapist_id: int
    session_date: date
    note_content: str
    note_title: Optional[str]
    session_time: Optional[time]
    created_at: datetime
    last_edited_at: datetime

# ==================== NOTE RETRIEVAL FUNCTIONS ====================
# Functions for fetching and querying session notes

async def get_notes_by_date_and_therapist(therapist_id: int, session_date: date) -> List[SessionNoteResponse]:
    """
    Retrieve all session notes for a specific therapist on a specific date
    
    Args:
        therapist_id: ID of the therapist whose notes to retrieve
        session_date: Specific date to get notes for
    
    Returns:
        List of SessionNoteResponse objects ordered by creation time (newest first)
    
    Usage:
        - Used by calendar component to show notes for selected date
        - Powers the notes modal when therapist clicks on a date
        - Enables daily note review and session documentation viewing
    """
    try:
        supabase = get_supabase_client()
        
        # Query session_notes for the specific therapist and date
        query = supabase.table('session_notes').select('''
            notes_id,
            therapist_id,
            session_date,
            note_content,
            note_title,
            session_time,
            created_at,
            last_edited_at
        ''').eq('therapist_id', therapist_id).eq('session_date', session_date.isoformat()).order('created_at', desc=True)
        
        result = query.execute()
        
        if not result.data:
            logger.info(f"No notes found for therapist {therapist_id} on date {session_date}")
            return []
        
        notes = []
        for note_data in result.data:
            note = SessionNoteResponse(
                notes_id=note_data['notes_id'],
                therapist_id=note_data['therapist_id'],
                session_date=note_data['session_date'],
                note_content=note_data['note_content'],
                note_title=note_data.get('note_title'),
                session_time=note_data.get('session_time'),
                created_at=note_data['created_at'],
                last_edited_at=note_data['last_edited_at']
            )
            notes.append(note)
        
        logger.info(f"Retrieved {len(notes)} notes for therapist {therapist_id} on date {session_date}")
        return notes
        
    except Exception as e:
        logger.error(f"Error getting notes by date and therapist: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_notes_with_dates_for_therapist(therapist_id: int) -> List[date]:
    """
    Get all dates that have session notes for a specific therapist
    
    Args:
        therapist_id: ID of the therapist to get note dates for
    
    Returns:
        Sorted list of dates that have associated notes
    
    Usage:
        - Used for calendar highlighting to show which dates have notes
        - Enables quick visual identification of documented sessions
        - Powers the notes indicator dots on calendar component
        - Helps therapists navigate to days with existing documentation
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('session_notes').select('session_date').eq('therapist_id', therapist_id).execute()
        
        if not result.data:
            logger.info(f"No notes found for therapist {therapist_id}")
            return []
        
        # Extract unique dates and sort them
        dates = list(set([datetime.fromisoformat(note['session_date']).date() for note in result.data]))
        dates.sort()
        
        logger.info(f"Found notes on {len(dates)} different dates for therapist {therapist_id}")
        return dates
        
    except Exception as e:
        logger.error(f"Error getting notes dates for therapist: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

# ==================== NOTE CREATION & MODIFICATION ====================
# Functions for creating, updating, and managing session notes

async def create_session_note(therapist_id: int, note_data: SessionNoteCreate) -> SessionNoteResponse:
    """
    Create a new session note in the database
    
    Args:
        therapist_id: ID of the therapist creating the note
        note_data: SessionNoteCreate object with note information
    
    Returns:
        SessionNoteResponse object representing the created note
    
    Usage:
        - Called when therapists document new therapy sessions
        - Used by notes modal when saving new session documentation
        - Creates permanent record of session activities and observations
        - Supports both scheduled and ad-hoc session documentation
    """
    try:
        supabase = get_supabase_client()
        
        # Prepare the data for insertion
        current_time = datetime.now().isoformat()
        insert_data = {
            'therapist_id': therapist_id,
            'session_date': note_data.session_date.isoformat(),
            'note_content': note_data.note_content,
            'note_title': note_data.note_title,
            'session_time': note_data.session_time.isoformat() if note_data.session_time else None,
            'created_at': current_time,
            'last_edited_at': current_time
        }
        
        result = supabase.table('session_notes').insert(insert_data).execute()
        
        if not result.data:
            raise Exception("Failed to create session note - no data returned from database")
        
        note_data_response = result.data[0]
        
        created_note = SessionNoteResponse(
            notes_id=note_data_response['notes_id'],
            therapist_id=note_data_response['therapist_id'],
            session_date=note_data_response['session_date'],
            note_content=note_data_response['note_content'],
            note_title=note_data_response.get('note_title'),
            session_time=note_data_response.get('session_time'),
            created_at=note_data_response['created_at'],
            last_edited_at=note_data_response['last_edited_at']
        )
        
        logger.info(f"Created new session note with ID: {created_note.notes_id} for therapist {therapist_id}")
        return created_note
        
    except Exception as e:
        logger.error(f"Error creating session note: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional note management functions

# TODO: Implement note update functionality
# async def update_session_note(note_id: int, therapist_id: int, update_data: SessionNoteUpdate) -> SessionNoteResponse:
#     """Update an existing session note"""
#     pass

# TODO: Implement note deletion functionality  
# async def delete_session_note(note_id: int, therapist_id: int) -> bool:
#     """Delete a session note"""
#     pass

# TODO: Implement note search functionality
# async def search_notes_by_content(therapist_id: int, search_term: str) -> List[SessionNoteResponse]:
#     """Search notes by content for a specific therapist"""
#     pass

# TODO: Implement bulk note operations
# async def get_notes_by_date_range(therapist_id: int, start_date: date, end_date: date) -> List[SessionNoteResponse]:
#     """Get notes within a date range"""
#     pass