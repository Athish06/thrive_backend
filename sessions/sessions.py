from typing import List, Optional, Dict, Any
from datetime import date, datetime, time
from pydantic import BaseModel, validator
import logging
from db import get_supabase_client
from utils.date_utils import (
    get_current_utc_datetime, utc_now_iso, today_local_iso, today_local_iso,
    parse_date_string, parse_time_string, format_date_iso
)

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== DATA MODELS ====================
# Pydantic models for session and activity data validation and serialization

class SessionCreate(BaseModel):
    """
    Data model for creating new therapy sessions
    - child_id: Student/child receiving therapy
    - session_date: Date when session is scheduled
    - start_time/end_time: Session duration with validation
    - therapist_notes: Optional session notes
    - session_activities: Optional list of activities to include
    """
    child_id: int  # Updated to match new schema
    session_date: date
    start_time: time
    end_time: time
    therapist_notes: Optional[str] = None
    session_activities: Optional[List[Dict[str, Any]]] = []  # List of session activities to create

    @validator('end_time')
    def validate_end_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v

class SessionUpdate(BaseModel):
    """
    Data model for updating existing therapy sessions
    - All fields optional for partial updates
    - Used for session modifications and status changes
    """
    session_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    status: Optional[str] = None
    therapist_notes: Optional[str] = None
    parent_feedback: Optional[str] = None

class SessionComplete(BaseModel):
    """
    Data model for completing a therapy session
    - Includes therapist notes to be added when session is marked as completed
    """
    therapist_notes: Optional[str] = None

class SessionResponse(BaseModel):
    """
    Complete session data model for API responses
    - Includes all session details plus related information
    - Contains calculated fields for activity progress
    - Used for session displays and management interfaces
    """
    id: int
    child_id: int
    therapist_id: int
    session_date: date
    start_time: time
    end_time: time
    status: str
    therapist_notes: Optional[str]
    parent_feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Related data
    student_name: Optional[str] = None
    therapist_name: Optional[str] = None
    total_planned_activities: int = 0
    completed_activities: int = 0

class SessionActivityCreate(BaseModel):
    """
    Data model for adding activities to therapy sessions
    - child_goal_id: Links to specific child goals rather than generic activities
    - actual_duration: Time spent on activity (optional)
    - performance_notes: Therapist observations and notes
    """
    child_goal_id: int  # Links to child_goals table instead of student_activity_id
    actual_duration: Optional[int] = None
    performance_notes: Optional[str] = None

class SessionActivityUpdate(BaseModel):
    """
    Data model for updating session activity information
    - Used for recording actual performance and duration
    - Supports partial updates of activity data
    """
    actual_duration: Optional[int] = None
    performance_notes: Optional[str] = None

class SessionActivityResponse(BaseModel):
    """
    Complete session activity data for API responses
    - Includes activity details from master activities table
    - Contains performance tracking and notes
    - Used for session planning and review interfaces
    """
    id: int
    session_id: int
    child_goal_id: int
    actual_duration: Optional[int]
    performance_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    # Related data from child_goals
    child_id: Optional[int] = None
    activity_id: Optional[int] = None
    current_status: Optional[str] = None  # Status from child_goals (in_progress, completed, etc.)
    
    # Related activity data from master activities table
    activity_name: Optional[str] = None
    activity_description: Optional[str] = None
    domain: Optional[str] = None
    difficulty_level: Optional[int] = None
    estimated_duration: Optional[int] = None

class ChildGoalResponse(BaseModel):
    """
    Child-specific goal data with progress tracking
    - Links individual children to specific therapeutic activities
    - Tracks progress, attempts, and mastery status
    - Used for personalized session planning
    """
    id: int
    child_id: int
    activity_id: int
    current_status: str
    total_attempts: int
    successful_attempts: int
    date_started: Optional[date]
    date_mastered: Optional[date]
    last_attempted: Optional[date]
    created_at: datetime
    updated_at: datetime
    
    # Related activity data from master activities table
    activity_name: str
    activity_description: Optional[str]
    domain: Optional[str]
    difficulty_level: int
    estimated_duration: Optional[int]

class ActivityResponse(BaseModel):
    """
    Master activity library data model
    - Represents therapeutic activities available system-wide
    - Used for activity selection and session planning
    - Contains standardized activity information
    """
    id: int
    activity_name: str
    activity_description: Optional[str]
    domain: Optional[str]
    difficulty_level: int
    estimated_duration: Optional[int]
    created_at: datetime
    updated_at: datetime

# ==================== HELPER FUNCTIONS ====================
# Utility functions for common database operations and data processing

async def _get_student_name(child_id: int) -> Optional[str]:
    """
    Helper function to get formatted student name
    - Reduces code duplication across session functions
    - Returns 'First Last' format or None if not found
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table('children').select('first_name, last_name').eq('id', child_id).execute()
        
        if result.data:
            student = result.data[0]
            return f"{student['first_name']} {student['last_name']}"
        return None
    except Exception as e:
        logger.warning(f"Could not fetch student name for child_id {child_id}: {e}")
        return None

async def _get_therapist_name(therapist_id: int) -> Optional[str]:
    """
    Helper function to get formatted therapist name
    - Reduces code duplication across session functions
    - Returns 'First Last' format or None if not found
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table('therapists').select('first_name, last_name').eq('user_id', therapist_id).execute()
        
        if result.data:
            therapist = result.data[0]
            return f"{therapist['first_name']} {therapist['last_name']}"
        return None
    except Exception as e:
        logger.warning(f"Could not fetch therapist name for therapist_id {therapist_id}: {e}")
        return None

async def _get_session_activity_counts(session_id: int) -> tuple[int, int]:
    """
    Helper function to count planned and completed activities for a session
    - Returns (total_planned, completed) tuple
    - Reduces code duplication across session retrieval functions
    """
    try:
        supabase = get_supabase_client()
        activities_result = supabase.table('session_activities').select('id, actual_duration', count='exact').eq('session_id', session_id).execute()
        
        total_planned = activities_result.count or 0
        completed = len([a for a in activities_result.data if a.get('actual_duration') is not None]) if activities_result.data else 0
        
        return total_planned, completed
    except Exception as e:
        logger.warning(f"Could not get activity counts for session {session_id}: {e}")
        return 0, 0

async def _verify_session_access(session_id: int, therapist_id: int) -> bool:
    """
    Helper function to verify therapist has access to session
    - Used by session activity functions for security
    - Returns True if access granted, False otherwise
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table('sessions').select('id').eq('id', session_id).eq('therapist_id', therapist_id).execute()
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error verifying session access: {e}")
        return False

# ==================== SESSION CRUD OPERATIONS ====================
# Core session management functions: Create, Read, Update, Delete

async def create_session(therapist_id: int, session_data: SessionCreate) -> SessionResponse:
    """
    Create a new therapy session with optional activities
    
    Args:
        therapist_id: ID of the therapist creating the session
        session_data: SessionCreate object with session details
    
    Returns:
        SessionResponse object representing the created session
    
    Usage:
        - Used by session scheduling interface
        - Creates sessions with automatic activity assignment
        - Supports bulk session creation with predefined activities
    """
    try:
        supabase = get_supabase_client()
        
        current_time = utc_now_iso()
        insert_data = {
            'therapist_id': therapist_id,
            'child_id': session_data.child_id,
            'session_date': format_date_iso(session_data.session_date),
            'start_time': session_data.start_time.isoformat(),
            'end_time': session_data.end_time.isoformat(),
            'status': 'scheduled',
            'therapist_notes': session_data.therapist_notes,
            'created_at': current_time,
            'updated_at': current_time
        }
        
        result = supabase.table('sessions').insert(insert_data).execute()
        
        if not result.data:
            raise Exception("Failed to create session - no data returned from database")
        
        session_data_result = result.data[0]
        session_id = session_data_result['id']
        
        # Create session activities if provided
        if session_data.session_activities:
            for activity_data in session_data.session_activities:
                child_goal_id = activity_data.get('child_goal_id')
                
                # If activity_id is provided instead of child_goal_id, create/get child_goal first
                if not child_goal_id and activity_data.get('activity_id'):
                    activity_id = activity_data['activity_id']
                    child_id = session_data.child_id
                    
                    # Check if child_goal already exists for this child and activity
                    existing_goal = supabase.table('child_goals').select('id').eq(
                        'child_id', child_id
                    ).eq('activity_id', activity_id).execute()
                    
                    if existing_goal.data:
                        child_goal_id = existing_goal.data[0]['id']
                        logger.info(f"Using existing child_goal {child_goal_id} for activity {activity_id}")
                    else:
                        # Create new child_goal for assessment activity
                        child_goal_insert = {
                            'child_id': child_id,
                            'activity_id': activity_id,
                            'current_status': 'in_progress',
                            'total_attempts': 0,
                            'successful_attempts': 0,
                            'created_at': current_time,
                            'updated_at': current_time
                        }
                        goal_result = supabase.table('child_goals').insert(child_goal_insert).execute()
                        if goal_result.data:
                            child_goal_id = goal_result.data[0]['id']
                            logger.info(f"Created new child_goal {child_goal_id} for assessment activity {activity_id}")
                        else:
                            logger.warning(f"Failed to create child_goal for activity {activity_id}")
                            continue
                
                if not child_goal_id:
                    logger.warning(f"No child_goal_id or activity_id provided for session activity")
                    continue
                
                activity_insert = {
                    'session_id': session_id,
                    'child_goal_id': child_goal_id,
                    'actual_duration': activity_data.get('actual_duration', 30),
                    'performance_notes': activity_data.get('performance_notes', ''),
                    'created_at': current_time,
                    'updated_at': current_time
                }
                
                activity_result = supabase.table('session_activities').insert(activity_insert).execute()
                if not activity_result.data:
                    logger.warning(f"Failed to create session activity for child_goal_id {child_goal_id}")
        
        # Get related data using helper functions
        student_name = await _get_student_name(session_data_result['child_id'])
        therapist_name = await _get_therapist_name(therapist_id)
        total_planned, completed = await _get_session_activity_counts(session_id)
        
        session_response = SessionResponse(
            id=session_data_result['id'],
            child_id=session_data_result['child_id'],
            therapist_id=session_data_result['therapist_id'],
            session_date=session_data_result['session_date'],
            start_time=session_data_result['start_time'],
            end_time=session_data_result['end_time'],
            status=session_data_result['status'],
            therapist_notes=session_data_result['therapist_notes'],
            created_at=session_data_result['created_at'],
            updated_at=session_data_result['updated_at'],
            student_name=student_name,
            therapist_name=therapist_name,
            total_planned_activities=total_planned,
            completed_activities=completed
        )
        
        logger.info(f"Created session {session_response.id} for therapist {therapist_id}")
        return session_response
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_sessions_by_therapist(therapist_id: int, limit: int = 50, offset: int = 0) -> List[SessionResponse]:
    """
    Retrieve all sessions for a specific therapist with pagination
    
    Args:
        therapist_id: ID of the therapist whose sessions to retrieve
        limit: Maximum number of sessions to return (default 50)
        offset: Number of sessions to skip for pagination (default 0)
    
    Returns:
        List of SessionResponse objects ordered by date (newest first)
    
    Usage:
        - Powers therapist dashboard session lists
        - Supports pagination for large session datasets
        - Used for session history and management interfaces
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time,
            status, therapist_notes, created_at, updated_at,
            children!child_id (first_name, last_name)
        ''').eq('therapist_id', therapist_id).order('session_date', desc=True).range(offset, offset + limit - 1).execute()
        
        if not result.data:
            logger.info(f"No sessions found for therapist {therapist_id}")
            return []
        
        sessions = []
        for session_data in result.data:
            student_name = None
            if session_data.get('children'):
                student = session_data['children']
                student_name = f"{student['first_name']} {student['last_name']}"
            
            # Get activity counts using helper function
            total_planned, completed = await _get_session_activity_counts(session_data['id'])
            
            session = SessionResponse(
                id=session_data['id'],
                child_id=session_data['child_id'],
                therapist_id=session_data['therapist_id'],
                session_date=session_data['session_date'],
                start_time=session_data['start_time'],
                end_time=session_data['end_time'],
                status=session_data['status'],
                therapist_notes=session_data['therapist_notes'],
                created_at=session_data['created_at'],
                updated_at=session_data['updated_at'],
                student_name=student_name,
                total_planned_activities=total_planned,
                completed_activities=completed
            )
            sessions.append(session)
        
        logger.info(f"Retrieved {len(sessions)} sessions for therapist {therapist_id}")
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting sessions for therapist: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_todays_sessions_by_therapist(therapist_id: int) -> List[SessionResponse]:
    """
    Retrieve today's sessions for a specific therapist
    
    Args:
        therapist_id: ID of the therapist whose today's sessions to retrieve
    
    Returns:
        List of SessionResponse objects ordered by start time
    
    Usage:
        - Powers "Today's Sessions" dashboard widgets
        - Used for daily agenda and schedule management
        - Enables quick access to current day's therapy schedule
    """
    try:
        supabase = get_supabase_client()
        
        # Get today's date in local timezone using standardized utility
        today = today_local_iso()
        
        logger.info(f"Fetching today's sessions for therapist {therapist_id} on {today}")
        
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time,
            status, therapist_notes, created_at, updated_at,
            children!child_id (first_name, last_name)
        ''').eq('therapist_id', therapist_id).eq('session_date', today).order('start_time').execute()
        
        if not result.data:
            logger.info(f"No sessions found for therapist {therapist_id} today ({today})")
            return []
        
        sessions = []
        for session_data in result.data:
            student_name = None
            if session_data.get('children'):
                student = session_data['children']
                student_name = f"{student['first_name']} {student['last_name']}"
            
            # Get activity counts using helper function
            total_planned, completed = await _get_session_activity_counts(session_data['id'])
            
            session = SessionResponse(
                id=session_data['id'],
                child_id=session_data['child_id'],
                therapist_id=session_data['therapist_id'],
                session_date=session_data['session_date'],
                start_time=session_data['start_time'],
                end_time=session_data['end_time'],
                status=session_data['status'],
                therapist_notes=session_data['therapist_notes'],
                created_at=session_data['created_at'],
                updated_at=session_data['updated_at'],
                student_name=student_name,
                total_planned_activities=total_planned,
                completed_activities=completed
            )
            sessions.append(session)
        
        logger.info(f"Retrieved {len(sessions)} today's sessions for therapist {therapist_id} on {today}")
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting today's sessions for therapist: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_session_by_id(session_id: int, therapist_id: int) -> Optional[SessionResponse]:
    """
    Retrieve a specific session by ID with access control
    
    Args:
        session_id: ID of the session to retrieve
        therapist_id: ID of the therapist requesting access
    
    Returns:
        SessionResponse object or None if not found/no access
    
    Usage:
        - Used for session detail views and editing interfaces
        - Provides security by verifying therapist ownership
        - Powers session-specific operations and displays
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time,
            status, therapist_notes, created_at, updated_at,
            children!child_id (first_name, last_name)
        ''').eq('id', session_id).eq('therapist_id', therapist_id).execute()
        
        if not result.data:
            logger.info(f"Session {session_id} not found or access denied for therapist {therapist_id}")
            return None
        
        session_data = result.data[0]
        
        student_name = None
        if session_data.get('children'):
            student = session_data['children']
            student_name = f"{student['first_name']} {student['last_name']}"
        
        # Get activity counts using helper function
        total_planned, completed = await _get_session_activity_counts(session_data['id'])
        
        session = SessionResponse(
            id=session_data['id'],
            child_id=session_data['child_id'],
            therapist_id=session_data['therapist_id'],
            session_date=session_data['session_date'],
            start_time=session_data['start_time'],
            end_time=session_data['end_time'],
            status=session_data['status'],
            therapist_notes=session_data['therapist_notes'],
            created_at=session_data['created_at'],
            updated_at=session_data['updated_at'],
            student_name=student_name,
            total_planned_activities=total_planned,
            completed_activities=completed
        )
        
        logger.info(f"Retrieved session {session_id}")
        return session
        
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def update_session(session_id: int, therapist_id: int, session_data: SessionUpdate) -> Optional[SessionResponse]:
    """
    Update an existing session with access control
    
    Args:
        session_id: ID of the session to update
        therapist_id: ID of the therapist requesting update
        session_data: SessionUpdate object with changes
    
    Returns:
        Updated SessionResponse object or None if not found/no access
    
    Usage:
        - Used for session rescheduling and modification
        - Supports partial updates of session fields
        - Maintains audit trail with updated_at timestamp
    """
    try:
        supabase = get_supabase_client()
        
        # Build update data dynamically
        update_data = {'updated_at': utc_now_iso()}
        
        if session_data.session_date is not None:
            update_data['session_date'] = format_date_iso(session_data.session_date)
        if session_data.start_time is not None:
            update_data['start_time'] = session_data.start_time.isoformat()
        if session_data.end_time is not None:
            update_data['end_time'] = session_data.end_time.isoformat()
        if session_data.status is not None:
            update_data['status'] = session_data.status
        if session_data.therapist_notes is not None:
            update_data['therapist_notes'] = session_data.therapist_notes
        
        result = supabase.table('sessions').update(update_data).eq('id', session_id).eq('therapist_id', therapist_id).execute()
        
        if not result.data:
            logger.info(f"Session {session_id} not found or access denied for therapist {therapist_id}")
            return None
        
        # Return updated session using existing function
        return await get_session_by_id(session_id, therapist_id)
        
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def update_session_notification_sent(session_id: int, therapist_id: int) -> bool:
    """
    Update the sent_notification flag for a session to true.
    
    Args:
        session_id: ID of the session to update.
        therapist_id: ID of the therapist making the request for verification.
    
    Returns:
        True if the update was successful, False otherwise.
    """
    try:
        supabase = get_supabase_client()
        
        # First, verify the therapist has access to this session
        session_check = supabase.table('sessions').select('id').eq('id', session_id).eq('therapist_id', therapist_id).execute()
        if not session_check.data:
            logger.warning(f"Access denied or session {session_id} not found for therapist {therapist_id}.")
            return False

        # Proceed with the update
        update_data = {
            'sent_notification': True,
            'updated_at': utc_now_iso()
        }
        
        result = supabase.table('sessions').update(update_data).eq('id', session_id).execute()
        
        if not result.data:
            logger.error(f"Failed to update notification status for session {session_id}.")
            return False
        
        logger.info(f"Successfully updated sent_notification for session {session_id}.")
        return True

    except Exception as e:
        logger.error(f"Error updating notification status for session {session_id}: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def delete_session(session_id: int, therapist_id: int) -> bool:
    """
    Delete a session with access control
    
    Args:
        session_id: ID of the session to delete
        therapist_id: ID of the therapist requesting deletion
    
    Returns:
        True if deleted successfully, False if not found/no access
    
    Usage:
        - Used for session cancellation and cleanup
        - Automatically removes associated session activities
        - Provides security through therapist ownership verification
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('sessions').delete().eq('id', session_id).eq('therapist_id', therapist_id).execute()
        
        success = len(result.data) > 0
        if success:
            logger.info(f"Deleted session {session_id}")
        else:
            logger.info(f"Session {session_id} not found or access denied for therapist {therapist_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

# ==================== SESSION ACTIVITY MANAGEMENT ====================
# Functions for managing activities within therapy sessions

async def add_activity_to_session(session_id: int, therapist_id: int, activity_data: SessionActivityCreate) -> SessionActivityResponse:
    """
    Add a therapeutic activity to an existing session
    
    Args:
        session_id: ID of the session to add activity to
        therapist_id: ID of the therapist adding the activity
        activity_data: SessionActivityCreate object with activity details
    
    Returns:
        SessionActivityResponse object representing the added activity
    
    Usage:
        - Used by session planning interfaces
        - Links child-specific goals to therapy sessions
        - Enables dynamic session customization
    """
    try:
        supabase = get_supabase_client()
        
        # Verify session access using helper function
        if not await _verify_session_access(session_id, therapist_id):
            raise Exception("Session not found or access denied")
        
        current_time = utc_now_iso()
        insert_data = {
            'session_id': session_id,
            'child_goal_id': activity_data.child_goal_id,
            'actual_duration': activity_data.actual_duration,
            'performance_notes': activity_data.performance_notes,
            'created_at': current_time,
            'updated_at': current_time
        }
        
        result = supabase.table('session_activities').insert(insert_data).execute()
        
        if not result.data:
            raise Exception("Failed to add activity to session")
        
        activity_data_result = result.data[0]
        
        # Get activity details from child_goals and activities tables
        child_goal_result = supabase.table('child_goals').select('''
            id, child_id, activity_id, current_status,
            activities!activity_id (activity_name, activity_description, domain, difficulty_level, estimated_duration)
        ''').eq('id', activity_data_result['child_goal_id']).execute()
        
        activity_name = None
        activity_description = None
        domain = None
        difficulty_level = None
        estimated_duration = None
        child_id = None
        activity_id = None
        current_status = None
        
        if child_goal_result.data:
            child_goal = child_goal_result.data[0]
            child_id = child_goal.get('child_id')
            activity_id = child_goal.get('activity_id')
            current_status = child_goal.get('current_status')
            
            if child_goal.get('activities'):
                activity = child_goal['activities']
                activity_name = activity['activity_name']
                activity_description = activity['activity_description']
                domain = activity['domain']
                difficulty_level = activity['difficulty_level']
                estimated_duration = activity['estimated_duration']
        
        session_activity = SessionActivityResponse(
            id=activity_data_result['id'],
            session_id=activity_data_result['session_id'],
            child_goal_id=activity_data_result['child_goal_id'],
            actual_duration=activity_data_result['actual_duration'],
            performance_notes=activity_data_result['performance_notes'],
            created_at=activity_data_result['created_at'],
            updated_at=activity_data_result['updated_at'],
            child_id=child_id,
            activity_id=activity_id,
            current_status=current_status,
            activity_name=activity_name,
            activity_description=activity_description,
            domain=domain,
            difficulty_level=difficulty_level,
            estimated_duration=estimated_duration
        )
        
        logger.info(f"Added activity {activity_data_result['child_goal_id']} to session {session_id}")
        return session_activity
        
    except Exception as e:
        logger.error(f"Error adding activity to session: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_session_activities(session_id: int, therapist_id: int) -> List[SessionActivityResponse]:
    """
    Retrieve all activities for a specific session
    
    Args:
        session_id: ID of the session whose activities to retrieve
        therapist_id: ID of the therapist requesting access
    
    Returns:
        List of SessionActivityResponse objects ordered by creation time
    
    Usage:
        - Powers session activity displays and management
        - Used for session execution and progress tracking
        - Enables activity-specific performance recording
    """
    try:
        supabase = get_supabase_client()
        
        # Verify session access using helper function
        if not await _verify_session_access(session_id, therapist_id):
            raise Exception("Session not found or access denied")
        
        result = supabase.table('session_activities').select('''
            id, session_id, child_goal_id, actual_duration, performance_notes, created_at, updated_at,
            child_goals!child_goal_id (
                id, child_id, activity_id, current_status,
                activities!activity_id (activity_name, activity_description, domain, difficulty_level, estimated_duration)
            )
        ''').eq('session_id', session_id).order('created_at').execute()
        
        if not result.data:
            logger.info(f"No activities found for session {session_id}")
            return []
        
        activities = []
        for activity_data in result.data:
            child_goal = activity_data.get('child_goals')
            activity_info = child_goal.get('activities') if child_goal else None
            
            activity = SessionActivityResponse(
                id=activity_data['id'],
                session_id=activity_data['session_id'],
                child_goal_id=activity_data['child_goal_id'],
                actual_duration=activity_data['actual_duration'],
                performance_notes=activity_data['performance_notes'],
                created_at=activity_data['created_at'],
                updated_at=activity_data['updated_at'],
                child_id=child_goal.get('child_id') if child_goal else None,
                activity_id=child_goal.get('activity_id') if child_goal else None,
                current_status=child_goal.get('current_status') if child_goal else None,
                activity_name=activity_info['activity_name'] if activity_info else None,
                activity_description=activity_info['activity_description'] if activity_info else None,
                domain=activity_info['domain'] if activity_info else None,
                difficulty_level=activity_info['difficulty_level'] if activity_info else None,
                estimated_duration=activity_info['estimated_duration'] if activity_info else None
            )
            activities.append(activity)
        
        logger.info(f"Retrieved {len(activities)} activities for session {session_id}")
        return activities
        
    except Exception as e:
        logger.error(f"Error getting session activities: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def remove_activity_from_session(session_activity_id: int, session_id: int, therapist_id: int) -> bool:
    """
    Remove an activity from a therapy session
    
    Args:
        session_activity_id: ID of the session activity to remove
        session_id: ID of the session containing the activity
        therapist_id: ID of the therapist requesting removal
    
    Returns:
        True if removed successfully, False if not found/no access
    
    Usage:
        - Used for session plan modifications
        - Enables dynamic activity management during planning
        - Provides security through session ownership verification
    """
    try:
        supabase = get_supabase_client()
        
        # Verify session access using helper function
        if not await _verify_session_access(session_id, therapist_id):
            raise Exception("Session not found or access denied")
        
        result = supabase.table('session_activities').delete().eq('id', session_activity_id).eq('session_id', session_id).execute()
        
        success = len(result.data) > 0
        if success:
            logger.info(f"Removed activity {session_activity_id} from session {session_id}")
        else:
            logger.info(f"Activity {session_activity_id} not found in session {session_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error removing activity from session: {str(e)}")
        raise Exception(f"Database error: {str(e)}")


async def update_session_activity(
    session_activity_id: int,
    session_id: int,
    therapist_id: int,
    update_data: SessionActivityUpdate
) -> SessionActivityResponse:
    """
    Update a session activity with actual duration and performance notes
    
    Args:
        session_activity_id: ID of the session activity to update
        session_id: ID of the session containing the activity
        therapist_id: ID of the therapist making the update
        update_data: SessionActivityUpdate containing fields to update
    
    Returns:
        Updated SessionActivityResponse object
    
    Usage:
        - Used to record actual activity duration after completion
        - Enables performance notes capture during active sessions
        - Provides security through session ownership verification
    """
    try:
        supabase = get_supabase_client()
        
        # Verify session access using helper function
        if not await _verify_session_access(session_id, therapist_id):
            raise Exception("Session not found or access denied")
        
        # Build update dictionary with only provided fields
        update_dict = {}
        if update_data.actual_duration is not None:
            update_dict['actual_duration'] = update_data.actual_duration
        if update_data.performance_notes is not None:
            update_dict['performance_notes'] = update_data.performance_notes
        
        if not update_dict:
            raise ValueError("No fields to update")
        
        update_dict['updated_at'] = utc_now_iso()
        
        # Update the session activity
        result = supabase.table('session_activities').update(update_dict).eq(
            'id', session_activity_id
        ).eq('session_id', session_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"Session activity {session_activity_id} not found")
        
        # Fetch the updated activity with all related data
        activities = await get_session_activities(session_id, therapist_id)
        updated_activity = next((a for a in activities if a.id == session_activity_id), None)
        
        if not updated_activity:
            raise ValueError("Failed to fetch updated activity")
        
        logger.info(f"Updated session activity {session_activity_id} in session {session_id}")
        return updated_activity
        
    except Exception as e:
        logger.error(f"Error updating session activity: {str(e)}")
        raise Exception(f"Database error: {str(e)}")


# ==================== ACTIVITY & GOAL UTILITY FUNCTIONS ====================
# Helper functions for activity selection and goal management

async def get_available_child_goals(child_id: int) -> List[ChildGoalResponse]:
    """
    Retrieve all available therapeutic goals for a specific child
    
    Args:
        child_id: ID of the child whose goals to retrieve
    
    Returns:
        List of ChildGoalResponse objects ordered by creation time
    
    Usage:
        - Used for personalized session planning
        - Powers activity selection interfaces for specific children
        - Enables goal-based therapy session customization
        - Tracks individual progress and mastery status
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('child_goals').select('''
            id, child_id, activity_id, current_status, total_attempts, successful_attempts,
            date_started, date_mastered, last_attempted, created_at, updated_at,
            activities!activity_id (activity_name, activity_description, domain, difficulty_level, estimated_duration)
        ''').eq('child_id', child_id).order('created_at').execute()
        
        if not result.data:
            logger.info(f"No goals found for child {child_id}")
            return []
        
        goals = []
        for goal_data in result.data:
            activity_info = goal_data.get('activities')
            
            goal = ChildGoalResponse(
                id=goal_data['id'],
                child_id=goal_data['child_id'],
                activity_id=goal_data['activity_id'],
                current_status=goal_data['current_status'],
                total_attempts=goal_data['total_attempts'],
                successful_attempts=goal_data['successful_attempts'],
                date_started=goal_data['date_started'],
                date_mastered=goal_data['date_mastered'],
                last_attempted=goal_data['last_attempted'],
                created_at=goal_data['created_at'],
                updated_at=goal_data['updated_at'],
                activity_name=activity_info['activity_name'] if activity_info else '',
                activity_description=activity_info['activity_description'] if activity_info else None,
                domain=activity_info['domain'] if activity_info else None,
                difficulty_level=activity_info['difficulty_level'] if activity_info else 1,
                estimated_duration=activity_info['estimated_duration'] if activity_info else None
            )
            goals.append(goal)
        
        logger.info(f"Retrieved {len(goals)} available goals for child {child_id}")
        return goals
        
    except Exception as e:
        logger.error(f"Error getting child goals: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_master_activities() -> List[ActivityResponse]:
    """
    Retrieve all activities from the master therapeutic activities library
    
    Returns:
        List of ActivityResponse objects ordered by activity name
    
    Usage:
        - Powers activity selection interfaces
        - Used for creating new child goals and session plans
        - Provides comprehensive catalog of available therapeutic exercises
        - Enables standardized activity management across the system
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('activities').select('*').order('activity_name').execute()
        
        if not result.data:
            logger.info("No activities found in master library")
            return []
        
        activities = []
        for activity_data in result.data:
            activity = ActivityResponse(
                id=activity_data['id'],
                activity_name=activity_data['activity_name'],
                activity_description=activity_data['activity_description'],
                domain=activity_data['domain'],
                difficulty_level=activity_data['difficulty_level'],
                estimated_duration=activity_data['estimated_duration'],
                created_at=activity_data['created_at'],
                updated_at=activity_data['updated_at']
            )
            activities.append(activity)
        
        logger.info(f"Retrieved {len(activities)} activities from master library")
        return activities
        
    except Exception as e:
        logger.error(f"Error getting master activities: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def get_assessment_tool_activities() -> Dict[str, Any]:
    """
    Retrieve assessment tool activities grouped by tool type
    
    Returns:
        Dictionary with assessment tools as keys and their activities as values
        {
            'isaa': {'id': 9, 'name': 'ISAA', 'activities': [...]},
            'indt-adhd': {'id': 10, 'name': 'INDT-ADHD', 'activities': [...]},
            'clinical-snapshots': {'id': 11, 'name': 'Clinical Snapshots', 'activities': [...]}
        }
    
    Usage:
        - Used for assessment session planning
        - Powers assessment tool selection and activity assignment
        - Enables structured assessment workflows for temporary enrollments
    """
    try:
        supabase = get_supabase_client()
        
        # Assessment tool parent activity IDs
        assessment_tools = {
            'isaa': {'id': 9, 'name': 'ISAA (Indian Scale for Assessment of Autism)'},
            'indt-adhd': {'id': 10, 'name': 'INDT-ADHD (Indian Scale for ADHD)'},
            'clinical-snapshots': {'id': 11, 'name': 'Clinical Snapshots'}
        }
        
        result_data = {}
        
        for tool_key, tool_info in assessment_tools.items():
            # Get the parent activity
            parent_result = supabase.table('activities').select('*').eq('id', tool_info['id']).execute()
            
            if not parent_result.data:
                logger.warning(f"Assessment tool {tool_key} (ID: {tool_info['id']}) not found in activities table")
                continue
            
            parent_activity = parent_result.data[0]
            
            # Get child activities (activities that belong to this assessment tool)
            # Assuming there's a parent_id field or similar relationship
            # If not, we'll need to adjust based on actual schema
            child_result = supabase.table('activities').select('*').eq('parent_id', tool_info['id']).order('activity_name').execute()
            
            activities_list = []
            if child_result.data:
                for activity_data in child_result.data:
                    activities_list.append({
                        'id': activity_data['id'],
                        'activity_name': activity_data['activity_name'],
                        'activity_description': activity_data.get('activity_description'),
                        'domain': activity_data.get('domain'),
                        'difficulty_level': activity_data.get('difficulty_level'),
                        'estimated_duration': activity_data.get('estimated_duration')
                    })
            
            result_data[tool_key] = {
                'id': tool_info['id'],
                'name': tool_info['name'],
                'parent_activity': {
                    'id': parent_activity['id'],
                    'activity_name': parent_activity['activity_name'],
                    'activity_description': parent_activity.get('activity_description')
                },
                'activities': activities_list,
                'activity_count': len(activities_list)
            }
        
        logger.info(f"Retrieved assessment tools with activities")
        return result_data
        
    except Exception as e:
        logger.error(f"Error getting assessment tool activities: {str(e)}")
        raise Exception(f"Database error: {str(e)}")

async def assign_ai_activity_to_child(activity_data: Dict[str, Any], child_id: int, therapist_id: int) -> Dict[str, Any]:
    """
    Assign an AI-suggested activity to a child
    - Creates activity in master library if it doesn't exist
    - Creates child_goal record linking child to activity
    - Returns assignment result with IDs

    Args:
        activity_data: AI-suggested activity data from frontend
        child_id: ID of the child to assign activity to
        therapist_id: ID of the therapist making the assignment

    Returns:
        Dictionary with assignment result
    """
    try:
        supabase = get_supabase_client()

        # Map AI activity data from multiple possible payload shapes
        activity_name = (
            activity_data.get('activity_name')
            or activity_data.get('title')
            or activity_data.get('name')
            or ''
        ).strip()

        activity_description = (
            activity_data.get('detailed_description')
            or activity_data.get('activity_description')
            or activity_data.get('description')
            or activity_data.get('summary')
            or ''
        ).strip()

        domain = _map_category_to_domain(
            activity_data.get('category')
            or activity_data.get('domain')
            or 'Other'
        )

        difficulty_level = _map_difficulty_to_level(
            activity_data.get('difficulty')
            or activity_data.get('difficulty_level')
            or 'medium'
        )

        estimated_duration = (
            activity_data.get('duration_minutes')
            or activity_data.get('duration')
            or activity_data.get('estimated_duration')
            or 30
        )

        if not activity_name:
            activity_name = f"Therapy Activity {utc_now_iso()}"

        try:
            estimated_duration = int(estimated_duration)
        except (TypeError, ValueError):
            estimated_duration = 30

        # Check if activity already exists in master library
        existing_activity = supabase.table('activities').select('id').eq('activity_name', activity_name).execute()

        if existing_activity.data and len(existing_activity.data) > 0:
            activity_id = existing_activity.data[0]['id']
            logger.info(f"Activity '{activity_name}' already exists with ID {activity_id}")
        else:
            # Create new activity in master library
            activity_insert = {
                'activity_name': activity_name,
                'activity_description': activity_description,
                'domain': domain,
                'difficulty_level': difficulty_level,
                'estimated_duration': estimated_duration,
                'created_at': utc_now_iso(),
                'updated_at': utc_now_iso()
            }

            activity_result = supabase.table('activities').insert(activity_insert).execute()

            if not activity_result.data:
                raise Exception("Failed to create activity in master library")

            activity_id = activity_result.data[0]['id']
            logger.info(f"Created new activity '{activity_name}' with ID {activity_id}")

        # Check if child_goal already exists
        existing_goal = supabase.table('child_goals').select('id').eq('child_id', child_id).eq('activity_id', activity_id).execute()

        if existing_goal.data and len(existing_goal.data) > 0:
            child_goal_id = existing_goal.data[0]['id']
            logger.info(f"Child goal already exists for child {child_id} and activity {activity_id}")

            # Update last_attempted timestamp
            supabase.table('child_goals').update({
                'last_attempted': utc_now_iso(),
                'updated_at': utc_now_iso()
            }).eq('id', child_goal_id).execute()

        else:
            # Create new child_goal record
            goal_insert = {
                'child_id': child_id,
                'activity_id': activity_id,
                'current_status': 'to_do',
                'total_attempts': 0,
                'successful_attempts': 0,
                'date_started': utc_now_iso(),
                'last_attempted': utc_now_iso(),
                'created_at': utc_now_iso(),
                'updated_at': utc_now_iso()
            }

            goal_result = supabase.table('child_goals').insert(goal_insert).execute()

            if not goal_result.data:
                raise Exception("Failed to create child goal")

            child_goal_id = goal_result.data[0]['id']
            logger.info(f"Created new child goal with ID {child_goal_id} for child {child_id}")

        return {
            'success': True,
            'message': f"Activity '{activity_name}' successfully assigned to child",
            'child_goal_id': child_goal_id,
            'activity_id': activity_id
        }

    except Exception as e:
        logger.error(f"Error assigning AI activity to child: {str(e)}")
        return {
            'success': False,
            'message': f"Failed to assign activity: {str(e)}",
            'child_goal_id': None,
            'activity_id': None
        }

def _map_category_to_domain(category: str) -> str:
    """
    Map AI activity category to database domain
    """
    category_mapping = {
        'Sensory': 'Sensory Processing',
        'Motor Skills': 'Motor Skills',
        'Cognitive': 'Cognitive',
        'Communication': 'Communication',
        'Social-Emotional': 'Social-Emotional',
        'Creative': 'Creative Arts',
        'Adaptive': 'Adaptive Skills'
    }
    return category_mapping.get(category, 'Other')

def _map_difficulty_to_level(difficulty: str) -> int:
    """
    Map AI difficulty string to database difficulty level
    """
    difficulty_mapping = {
        'easy': 1,
        'medium': 2,
        'hard': 3
    }
    if isinstance(difficulty, (int, float)):
        try:
            difficulty_int = int(difficulty)
            return difficulty_int if 1 <= difficulty_int <= 5 else 2
        except (TypeError, ValueError):
            return 2

    if isinstance(difficulty, str):
        return difficulty_mapping.get(difficulty.lower(), 2)

    return 2


# ==================== ACTIVITY COMPLETION ====================

async def mark_activity_completed(child_id: int, activity_id: int) -> Dict[str, Any]:
    """
    Mark a child goal activity as completed
    Updates the current_status in child_goals table to 'completed'
    
    Args:
        child_id: ID of the child
        activity_id: ID of the activity
        
    Returns:
        Dict containing success status and message
    """
    try:
        supabase = get_supabase_client()
        
        # Find the child_goal record
        goal_result = supabase.table('child_goals').select('id, current_status').eq(
            'child_id', child_id
        ).eq('activity_id', activity_id).execute()
        
        if not goal_result.data or len(goal_result.data) == 0:
            raise ValueError(f"No goal found for child {child_id} and activity {activity_id}")
        
        child_goal_id = goal_result.data[0]['id']
        current_status = goal_result.data[0]['current_status']
        
        # Update the status to completed
        update_result = supabase.table('child_goals').update({
            'current_status': 'completed',
            'date_mastered': date.today().isoformat(),
            'updated_at': utc_now_iso()
        }).eq('id', child_goal_id).execute()
        
        if not update_result.data:
            raise ValueError("Failed to update goal status")
        
        logger.info(f"Marked activity {activity_id} as completed for child {child_id}")
        
        return {
            'success': True,
            'message': 'Activity marked as completed',
            'child_goal_id': child_goal_id,
            'previous_status': current_status,
            'new_status': 'completed'
        }
        
    except Exception as e:
        logger.error(f"Error marking activity as completed: {str(e)}")
        return {
            'success': False,
            'message': str(e),
            'child_goal_id': None,
            'previous_status': None,
            'new_status': None
        }