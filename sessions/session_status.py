from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from pydantic import BaseModel
import logging
from db import get_supabase_client, format_supabase_response, handle_supabase_error
from utils.date_utils import (
    get_current_utc_datetime, get_current_utc_date, utc_now_iso,
    parse_date_string, parse_time_string, parse_datetime_string,
    format_date_iso, format_datetime_iso, ensure_utc, is_today
)

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# Session status constants
SESSION_STATUS = {
    "SCHEDULED": "scheduled",
    "ONGOING": "ongoing", 
    "COMPLETED": "completed",
    "CANCELLED": "cancelled"
}

# Notification timing (in minutes before session)
NOTIFICATION_LEAD_TIME = 5
POST_SESSION_DELAY_MINUTES = 50  # Minutes after session starts to check for next session

# Smart scheduling configuration (minimal - frontend handles scheduling)
SMART_SCHEDULER_ENABLED = False  # Disabled since frontend handles scheduling
SCHEDULED_NOTIFICATIONS = {}  # Kept for compatibility but not used
SCHEDULER_TIMERS = {}  # Kept for compatibility but not used


# ==================== DATA MODELS ====================
# Pydantic models for session status and notification operations

class SessionStatusUpdate(BaseModel):
    """
    Data model for session status updates
    - session_id: ID of session to update
    - new_status: Target status (scheduled/ongoing/completed)
    - updated_by: ID of therapist making the change
    """
    session_id: int
    new_status: str
    updated_by: Optional[int] = None

class SessionNotification(BaseModel):
    """
    Data model for session notifications
    - session_id: ID of session for notification
    - therapist_id: ID of therapist to notify
    - student_name: Name of student for the session
    - notification_type: Type of notification (upcoming/starting/ending)
    - message: Notification message content
    - scheduled_time: When notification should be sent
    """
    session_id: int
    therapist_id: int
    student_name: str
    notification_type: str
    message: str
    scheduled_time: datetime
    session_start_time: datetime
    session_end_time: datetime

class SessionStatusResponse(BaseModel):
    """
    Response model for session status operations
    - session_id: ID of the session
    - previous_status: Status before update
    - current_status: Status after update
    - updated_at: Timestamp of status change
    - updated_by: ID of therapist who made the change
    """
    session_id: int
    previous_status: str
    current_status: str
    updated_at: datetime
    updated_by: Optional[int] = None

# ==================== HELPER FUNCTIONS ====================
# Utility functions for session status and notification operations

def _validate_status_transition(current_status: str, new_status: str) -> bool:
    """
    Validate if status transition is allowed
    - Prevents invalid status changes
    - Returns True if transition is valid
    """
    valid_transitions = {
        SESSION_STATUS["SCHEDULED"]: [SESSION_STATUS["ONGOING"], SESSION_STATUS["CANCELLED"]],
        SESSION_STATUS["ONGOING"]: [SESSION_STATUS["COMPLETED"], SESSION_STATUS["CANCELLED"]],
        SESSION_STATUS["COMPLETED"]: [],  # Final status
        SESSION_STATUS["CANCELLED"]: []   # Final status
    }
    
    return new_status in valid_transitions.get(current_status, [])

def _create_notification_message(session_data: Dict[str, Any], notification_type: str) -> str:
    """
    Create appropriate notification message based on type
    - Returns formatted message for different notification types
    """
    student_name = session_data.get('student_name', 'Student')
    start_time = session_data.get('start_time', '')
    
    messages = {
        "upcoming": f"Session with {student_name} starts in 5 minutes at {start_time}",
        "starting": f"Session with {student_name} is starting now",
        "ending": f"Session with {student_name} has ended and marked as completed"
    }
    
    return messages.get(notification_type, "Session notification")

def _combine_datetime(session_date: date, session_time: time) -> datetime:
    """
    Combine date and time objects into datetime
    - Handles local datetime creation for proper comparison with current local time
    """
    combined = datetime.combine(session_date, session_time)
    
    # Keep as local time for consistent comparison with current local datetime
    logger.info(f"Combined date {session_date} and time {session_time} into LOCAL datetime: {combined}")
    return combined

def _parse_time_string(time_string: str) -> time:
    """
    Parse time string into time object
    - Handles various time formats including HH:MM:SS and HH:MM
    - Returns time object for use with datetime operations
    """
    try:
        logger.info(f"Parsing time string: '{time_string}' (type: {type(time_string)})")
        
        # If it's already a time object, return it
        if isinstance(time_string, time):
            logger.info(f"Already a time object: {time_string}")
            return time_string
        
        # Convert to string if not already
        time_str = str(time_string).strip()
        
        # Try parsing as full datetime first (in case it's a full ISO string)
        if 'T' in time_str or len(time_str) > 10:
            parsed_dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            logger.info(f"Parsed as full datetime: {parsed_dt}, time: {parsed_dt.time()}")
            return parsed_dt.time()
        
        # Parse as time-only string (HH:MM:SS or HH:MM)
        if len(time_str) == 8:  # HH:MM:SS format
            parsed_time = datetime.strptime(time_str, '%H:%M:%S').time()
            logger.info(f"Parsed as HH:MM:SS: {parsed_time}")
            return parsed_time
        elif len(time_str) == 5:  # HH:MM format
            parsed_time = datetime.strptime(time_str, '%H:%M').time()
            logger.info(f"Parsed as HH:MM: {parsed_time}")
            return parsed_time
        else:
            # Try ISO format parsing
            parsed_dt = datetime.fromisoformat(time_str)
            logger.info(f"Parsed as ISO format: {parsed_dt}, time: {parsed_dt.time()}")
            return parsed_dt.time()
            
    except ValueError as e:
        logger.error(f"Error parsing time string '{time_string}': {e}")
        # Return current time as fallback
        fallback_time = datetime.now().time()
        logger.warning(f"Using fallback time: {fallback_time}")
        return fallback_time

async def _get_session_details(session_id: int) -> Optional[Dict[str, Any]]:
    """
    Get session details for status updates and notifications
    - Returns session data with student name
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time, status,
            children!child_id (first_name, last_name)
        ''').eq('id', session_id).execute()
        
        handle_supabase_error(result)
        
        if not result.data:
            return None
        
        session = result.data[0]
        
        # Format student name
        student_name = "Unknown Student"
        if session.get('children'):
            child = session['children']
            student_name = f"{child['first_name']} {child['last_name']}"
        
        return {
            **session,
            'student_name': student_name
        }
        
    except Exception as e:
        logger.error(f"Error getting session details for {session_id}: {e}")
        return None

async def _log_status_change(session_id: int, previous_status: str, new_status: str, updated_by: int = None) -> None:
    """
    Log session status changes for audit trail
    - Records status transitions with timestamps
    """
    logger.info(f"Session {session_id} status changed: {previous_status} → {new_status} by therapist {updated_by}")

# ==================== SESSION STATUS MANAGEMENT ====================
# Core functions for managing session status transitions

async def update_session_status(session_id: int, new_status: str, therapist_id: int = None) -> Optional[SessionStatusResponse]:
    """
    Update session status with validation and logging
    
    Args:
        session_id: ID of session to update
        new_status: Target status (scheduled/ongoing/completed/cancelled)
        therapist_id: ID of therapist making the change (optional)
    
    Returns:
        SessionStatusResponse with details of the status change
    
    Usage:
        - Used to manually change session status
        - Validates status transitions before updating
        - Logs all status changes for audit trail
        - Used by UI controls and automated processes
    """
    try:
        supabase = get_supabase_client()
        
        # Get current session details
        session_details = await _get_session_details(session_id)
        if not session_details:
            logger.warning(f"Session {session_id} not found for status update")
            return None
        
        current_status = session_details['status']
        
        # Validate status transition
        if not _validate_status_transition(current_status, new_status):
            logger.warning(f"Invalid status transition for session {session_id}: {current_status} → {new_status}")
            raise ValueError(f"Invalid status transition: {current_status} → {new_status}")
        
        # Update session status
        update_data = {
            'status': new_status,
            'updated_at': utc_now_iso()
        }
        
        result = supabase.table('sessions').update(update_data).eq('id', session_id).execute()
        handle_supabase_error(result)
        
        if not result.data:
            logger.error(f"Failed to update session {session_id} status")
            return None
        
        # Log the status change
        await _log_status_change(session_id, current_status, new_status, therapist_id)
        
        response = SessionStatusResponse(
            session_id=session_id,
            previous_status=current_status,
            current_status=new_status,
            updated_at=get_current_utc_datetime(),
            updated_by=therapist_id
        )
        
        logger.info(f"Successfully updated session {session_id} status to {new_status}")
        return response
        
    except Exception as e:
        logger.error(f"Error updating session status: {e}")
        raise Exception(f"Database error: {str(e)}")

async def start_session(session_id: int, therapist_id: int = None) -> Optional[SessionStatusResponse]:
    """
    Start a scheduled session (change status to ongoing)
    
    Args:
        session_id: ID of session to start
        therapist_id: ID of therapist starting the session
    
    Returns:
        SessionStatusResponse with status change details
    
    Usage:
        - Called when therapist begins a session
        - Can be triggered manually or automatically at session start time
        - Updates status from 'scheduled' to 'ongoing'
    """
    return await update_session_status(session_id, SESSION_STATUS["ONGOING"], therapist_id)

async def complete_session(session_id: int, therapist_id: int = None, therapist_notes: str = None) -> Optional[SessionStatusResponse]:
    """
    Complete an ongoing session (change status to completed)
    
    Args:
        session_id: ID of session to complete
        therapist_id: ID of therapist completing the session
        therapist_notes: Optional notes from therapist about the session
    
    Returns:
        SessionStatusResponse with status change details
    
    Usage:
        - Called when session ends
        - Can be triggered manually or automatically at session end time
        - Updates status from 'ongoing' to 'completed'
        - Saves therapist notes if provided
        - For assessment sessions (temporary students), updates assessment_details in children table
    """
    try:
        supabase = get_supabase_client()
        
        # First update the session status
        result = await update_session_status(session_id, SESSION_STATUS["COMPLETED"], therapist_id)
        
        if result and therapist_notes is not None:
            # Update therapist notes
            update_data = {
                'therapist_notes': therapist_notes,
                'updated_at': utc_now_iso()
            }
            
            notes_result = supabase.table('sessions').update(update_data).eq('id', session_id).execute()
            handle_supabase_error(notes_result)
            
            if notes_result.data:
                logger.info(f"Updated therapist notes for session {session_id}")
            else:
                logger.warning(f"Failed to update therapist notes for session {session_id}")
        
        if result:
            # Check if this is an assessment session and update assessment details
            await _update_assessment_details_for_child(session_id)
        
        return result
    except Exception as e:
        logger.error(f"Error completing session {session_id}: {e}")
        raise

async def _update_assessment_details_for_child(session_id: int) -> None:
    """
    Update assessment details in children table after assessment session completion
    - Reads session_activities for assessment tools (ISAA, INDT, Clinical Snapshots)
    - Extracts scores from performance_notes
    - Updates assessment_details JSONB column in children table
    - Promotes status from 'assessment_due' to 'active' if criteria met
    
    Args:
        session_id: ID of the completed session
    """
    try:
        supabase = get_supabase_client()
        
        # Assessment tool activity IDs
        ASSESSMENT_TOOL_IDS = {
            9: 'isaa',
            10: 'indt-adhd',
            11: 'clinical-snapshots'
        }
        
        # Get session details to find the child
        session_result = supabase.table('sessions').select('child_id').eq('id', session_id).single().execute()
        if not session_result.data:
            logger.info(f"Session {session_id} not found")
            return
        
        child_id = session_result.data['child_id']
        
        # Get session activities for this session
        activities_result = supabase.table('session_activities').select('''
            id,
            child_goal_id,
            actual_duration,
            performance_notes,
            child_goals!child_goal_id (
                activity_id
            )
        ''').eq('session_id', session_id).execute()
        
        if not activities_result.data:
            logger.info(f"No activities found for session {session_id}")
            return
        
        # Check if any activities are assessment tools
        assessment_data = {}
        has_assessment_tools = False
        
        for activity in activities_result.data:
            child_goal = activity.get('child_goals')
            if not child_goal:
                continue
            
            activity_id = child_goal.get('activity_id')
            if activity_id in ASSESSMENT_TOOL_IDS:
                has_assessment_tools = True
                tool_key = ASSESSMENT_TOOL_IDS[activity_id]
                
                # Parse performance_notes to extract scores
                # Expected format: JSON string with assessment items and scores
                performance_notes = activity.get('performance_notes', '')
                if performance_notes:
                    try:
                        import json
                        scores = json.loads(performance_notes)
                        
                        # Calculate average if items present
                        if isinstance(scores, dict) and 'items' in scores:
                            items = scores['items']
                            if items:
                                score_values = [v for v in items.values() if isinstance(v, (int, float))]
                                if score_values:
                                    average = sum(score_values) / len(score_values)
                                    assessment_data[tool_key] = {
                                        'items': items,
                                        'average': round(average, 2)
                                    }
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        logger.warning(f"Could not parse assessment scores for activity {activity['id']}: {e}")
                        continue
        
        if not has_assessment_tools:
            logger.info(f"Session {session_id} does not contain assessment tools")
            return
        
        # Get current child assessment details and prior_diagnosis status
        child_result = supabase.table('children').select('assessment_details, prior_diagnosis, status').eq('id', child_id).single().execute()
        if not child_result.data:
            logger.warning(f"Child {child_id} not found")
            return
        
        current_assessment = child_result.data.get('assessment_details') or {}
        prior_diagnosis = child_result.data.get('prior_diagnosis', False)
        current_status = child_result.data.get('status', 'assessment_due')
        
        # Merge new assessment data with existing
        updated_assessment = {**current_assessment, **assessment_data}
        
        # Determine if child should be promoted to 'active' status
        # Rules:
        # - Prior diagnosis: needs clinical-snapshots OR any other assessment
        # - No prior diagnosis: needs ISAA or INDT (non-snapshot assessment)
        has_clinical_snapshot = 'clinical-snapshots' in updated_assessment
        has_non_snapshot = 'isaa' in updated_assessment or 'indt-adhd' in updated_assessment
        
        should_be_active = False
        if prior_diagnosis:
            should_be_active = has_clinical_snapshot or has_non_snapshot
        else:
            should_be_active = has_non_snapshot
        
        # Update children table
        update_data = {
            'assessment_details': updated_assessment,
            'updated_at': utc_now_iso()
        }
        
        # Promote to active if criteria met and currently assessment_due
        if should_be_active and current_status == 'assessment_due':
            update_data['status'] = 'active'
            logger.info(f"Promoting child {child_id} from assessment_due to active")
        
        supabase.table('children').update(update_data).eq('id', child_id).execute()
        logger.info(f"Updated assessment details for child {child_id} from session {session_id}")
        
    except Exception as e:
        logger.error(f"Error updating assessment details for session {session_id}: {e}")
        # Don't raise - we don't want to fail session completion if assessment update fails

async def cancel_session(session_id: int, therapist_id: int = None) -> Optional[SessionStatusResponse]:
    """
    Cancel a session (change status to cancelled)
    
    Args:
        session_id: ID of session to cancel
        therapist_id: ID of therapist cancelling the session
    
    Returns:
        SessionStatusResponse with status change details
    
    Usage:
        - Called when session needs to be cancelled
        - Can be used for scheduled or ongoing sessions
        - Updates status to 'cancelled'
    """
    return await update_session_status(session_id, SESSION_STATUS["CANCELLED"], therapist_id)

# ==================== AUTOMATED SESSION MONITORING ====================
# Functions for automatic session status updates based on time

async def get_sessions_needing_status_update() -> List[Dict[str, Any]]:
    """
    Get sessions that need automatic status updates based on current time
    
    Returns:
        List of sessions requiring status updates
    
    Usage:
        - Called by background monitoring service
        - Identifies sessions that should be started or completed
        - Used for automated session management
    """
    try:
        supabase = get_supabase_client()
        current_datetime = get_current_utc_datetime()
        current_date = get_current_utc_date()
        current_time = current_datetime.time()
        
        # Get today's sessions that need status updates
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time, status,
            children!child_id (first_name, last_name)
        ''').eq('session_date', format_date_iso(current_date)).execute()
        
        handle_supabase_error(result)
        
        if not result.data:
            return []
        
        sessions_needing_update = []
        
        for session in result.data:
            session_start = _parse_time_string(session['start_time'])
            session_end = _parse_time_string(session['end_time'])
            session_status = session['status']
            
            # Add student name
            student_name = "Unknown Student"
            if session.get('children'):
                child = session['children']
                student_name = f"{child['first_name']} {child['last_name']}"
            
            session_data = {
                **session,
                'student_name': student_name,
                'session_start_datetime': _combine_datetime(current_date, session_start),
                'session_end_datetime': _combine_datetime(current_date, session_end)
            }
            
            # Check if session should be started (scheduled → ongoing)
            if (session_status == SESSION_STATUS["SCHEDULED"] and 
                current_time >= session_start):
                session_data['suggested_action'] = 'start'
                sessions_needing_update.append(session_data)
            
            # Check if session should be completed (ongoing → completed)
            elif (session_status == SESSION_STATUS["ONGOING"] and 
                  current_time >= session_end):
                session_data['suggested_action'] = 'complete'
                sessions_needing_update.append(session_data)
        
        logger.info(f"Found {len(sessions_needing_update)} sessions needing status updates")
        return sessions_needing_update
        
    except Exception as e:
        logger.error(f"Error getting sessions needing status update: {e}")
        return []

async def auto_update_session_statuses() -> List[SessionStatusResponse]:
    """
    Automatically update session statuses based on current time
    
    Returns:
        List of SessionStatusResponse objects for updated sessions
    
    Usage:
        - Called by scheduled background task
        - Automatically starts sessions at start time
        - Automatically completes sessions at end time
        - Maintains session status accuracy without manual intervention
    """
    sessions_needing_update = await get_sessions_needing_status_update()
    updated_sessions = []
    
    for session in sessions_needing_update:
        try:
            session_id = session['id']
            action = session['suggested_action']
            
            if action == 'start':
                result = await start_session(session_id)
                if result:
                    updated_sessions.append(result)
                    logger.info(f"Auto-started session {session_id}")
            
            elif action == 'complete':
                result = await complete_session(session_id)
                if result:
                    updated_sessions.append(result)
                    logger.info(f"Auto-completed session {session_id}")
        
        except Exception as e:
            logger.error(f"Error auto-updating session {session['id']}: {e}")
    
    return updated_sessions

# ==================== ENHANCED NOTIFICATION FUNCTIONS ====================
# Updated notification functions that work with smart scheduling

# ==================== BULK OPERATIONS ====================
# Functions for bulk session status operations

async def get_todays_sessions_status() -> List[Dict[str, Any]]:
    """
    Get status overview of all today's sessions
    
    Returns:
        List of session dictionaries with current status information
    
    Usage:
        - Used for dashboard status overview
        - Provides quick summary of daily session progress
        - Helps therapists see session completion status
    """
    try:
        supabase = get_supabase_client()
        current_date = get_current_utc_date()
        
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time, status,
            children!child_id (first_name, last_name)
        ''').eq('session_date', current_date.isoformat()).order('start_time').execute()
        
        handle_supabase_error(result)
        
        if not result.data:
            return []
        
        sessions_status = []
        
        for session in result.data:
            student_name = "Unknown Student"
            if session.get('children'):
                child = session['children']
                student_name = f"{child['first_name']} {child['last_name']}"
            
            session_data = {
                'session_id': session['id'],
                'therapist_id': session['therapist_id'],
                'student_name': student_name,
                'start_time': session['start_time'],
                'end_time': session['end_time'],
                'current_status': session['status'],
                'session_date': session['session_date']
            }
            sessions_status.append(session_data)
        
        logger.info(f"Retrieved status for {len(sessions_status)} today's sessions")
        return sessions_status
        
    except Exception as e:
        logger.error(f"Error getting today's sessions status: {e}")
        return []

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional session management features

# TODO: Implement notification preferences
# async def get_therapist_notification_preferences(therapist_id: int) -> Dict[str, Any]:
#     """Get therapist's notification preferences"""
#     pass

# TODO: Implement session reminder scheduling
# async def schedule_session_reminders(session_id: int) -> bool:
#     """Schedule automated reminders for session"""
#     pass

# TODO: Implement session analytics
# async def get_session_completion_stats(therapist_id: int, date_range: tuple) -> Dict[str, Any]:
#     """Get session completion statistics"""
#     pass

# TODO: Implement batch status updates
# async def bulk_update_session_status(session_ids: List[int], new_status: str) -> List[SessionStatusResponse]:
#     """Update status for multiple sessions"""
#     pass

# TODO: Implement session escalation
# async def escalate_overdue_sessions() -> List[Dict[str, Any]]:
#     """Identify and escalate sessions that are overdue"""
#     pass

# =================================
# LOGIN-BASED SESSION CHECKING
# =================================

async def check_sessions_on_login(therapist_id: int) -> Dict[str, Any]:
    """
    Check session status immediately after therapist login - EXACT SPECIFICATION MATCH
    
    This function implements the exact specification:
    1. Fetch Today's Schedule: Get complete session schedule for current date, sorted by start time
    2. Identify First Session: Isolate the very first session of the day
    3. Compare Timestamps: Compare current time (login_time) against first session start_time
    4. Scenario A (Late): If login_time > first_session.start_time -> notify "You are late" + update status to "Ongoing"
    5. Scenario B (On Time/Early): If login_time <= first_session.start_time -> notify "Time remaining for next session"
    
    Args:
        therapist_id: ID of the therapist who just logged in
        
    Returns:
        Dictionary containing notification payload and session info per specification
    """
    try:
        logger.info(f"Starting session check on login for therapist {therapist_id}")
        
        supabase = get_supabase_client()
        # Use local time instead of UTC for proper comparison with session times
        current_datetime = datetime.now()  # Local time instead of UTC
        current_date = current_datetime.date()
        
        logger.info(f"Current LOCAL datetime: {current_datetime}, current date: {current_date}")
        logger.info(f"Current time formatted: {current_datetime.strftime('%H:%M:%S')}")
        
        # Step 1: Fetch Today's Schedule - sorted by start time
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time, status,
            children!child_id (first_name, last_name)
        ''').eq('session_date', current_date.isoformat()).eq('therapist_id', therapist_id).order('start_time').execute()
        
        handle_supabase_error(result)
        
        logger.info(f"Found {len(result.data) if result.data else 0} sessions for therapist {therapist_id} today")
        
        if not result.data:
            logger.info(f"No sessions scheduled for therapist {therapist_id} today")
            return {
                "success": True,
                "message": "No sessions scheduled for today",
                "notification_payload": None,
                "sessions_updated": 0
            }
        
        # Step 2: Identify First Session - the very first session of the day
        first_session = result.data[0]
        logger.info(f"First session of the day: {first_session}")
        
        # Parse session data
        session_start_time = _parse_time_string(first_session['start_time'])
        session_start_datetime = _combine_datetime(current_date, session_start_time)
        
        logger.info(f"Current time: {current_datetime}")
        logger.info(f"Session start time string: {first_session['start_time']}")
        logger.info(f"Parsed session start time: {session_start_time}")
        logger.info(f"Combined session start datetime: {session_start_datetime}")
        
        student_name = "Unknown Student"
        if first_session.get('children'):
            child = first_session['children']
            student_name = f"{child['first_name']} {child['last_name']}"
        
        logger.info(f"Student name: {student_name}")
        
        # Step 3: Compare Timestamps - login_time vs first_session.start_time
        notification_payload = None
        sessions_updated = 0
        
        if current_datetime > session_start_datetime:
            # Scenario A: User is Late (login_time > first_session.start_time)
            logger.info("User is late for session - updating status to ongoing")
            
            # Action 1: Update session status to "Ongoing"
            if first_session['status'] == SESSION_STATUS["SCHEDULED"]:
                await update_session_status(first_session['id'], SESSION_STATUS["ONGOING"], therapist_id)
                sessions_updated = 1
                logger.info(f"Updated session {first_session['id']} status to ongoing")
            
            # Action 2: Send notification payload - "You are late to the session"
            minutes_late = int((current_datetime - session_start_datetime).total_seconds() / 60)
            notification_payload = {
                "notificationId": f"late-{first_session['id']}-{int(current_datetime.timestamp())}",
                "type": "LATE_ALERT",
                "message": f"You are late to the session with {student_name}. Session has been marked as ongoing.",
                "sessionId": str(first_session['id']),
                "timestamp": current_datetime.isoformat(),
                "student_name": student_name,
                "minutes_late": minutes_late,
                "notification_type": "late"
            }
            
        else:
            # Scenario B: User is On Time/Early (login_time <= first_session.start_time)
            logger.info("User is on time/early for session")
            
            # Action: Send notification payload - "Time remaining for next session"
            time_until_session = (session_start_datetime - current_datetime).total_seconds() / 60
            hours = int(time_until_session // 60)
            minutes = int(time_until_session % 60)
            
            logger.info(f"Time calculation: {time_until_session:.1f} total minutes = {hours} hours, {minutes} minutes")
            logger.info(f"Session start datetime: {session_start_datetime}")
            logger.info(f"Current datetime: {current_datetime}")
            logger.info(f"Time difference in seconds: {(session_start_datetime - current_datetime).total_seconds()}")
            
            # Simplified message without specific time details
            notification_payload = {
                "notificationId": f"upcoming-{first_session['id']}-{int(current_datetime.timestamp())}",
                "type": "UPCOMING_SESSION",
                "message": f"Your next session with {student_name} is scheduled for {session_start_time.strftime('%H:%M')}",
                "sessionId": str(first_session['id']),
                "timestamp": current_datetime.isoformat(),
                "student_name": student_name,
                "session_start_time": session_start_datetime.isoformat(),
                "minutes_remaining": int(time_until_session),
                "notification_type": "upcoming"
            }
        
        logger.info(f"Notification payload created: {notification_payload}")
        
        return {
            "success": True,
            "message": "Login session check completed",
            "notification_payload": notification_payload,
            "sessions_updated": sessions_updated,
            "total_sessions_today": len(result.data),
            "first_session_time": session_start_datetime.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking sessions on login for therapist {therapist_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to check sessions: {str(e)}",
            "notification_payload": None,
            "sessions_updated": 0
        }


async def schedule_session_notifications_for_day(therapist_id: int) -> Dict[str, Any]:
    """
    Schedule continuous 5-minute pre-session notifications for remaining sessions today
    
    This implements the continuous monitoring specification:
    1. Identify Next Upcoming Session: Find session with earliest start_time > current_time
    2. Schedule Pre-Session Reminder: Set notification for exactly 5 minutes before start_time
    3. Continuous Loop: After notification sent, repeat for next session until day complete
    
    Args:
        therapist_id: ID of the therapist
        
    Returns:
        Dictionary with scheduling results
    """
    try:
        supabase = get_supabase_client()
        current_datetime = get_current_utc_datetime()
        current_date = get_current_utc_date()
        
        # Get remaining sessions for today (after current time)
        result = supabase.table('sessions').select('''
            id, therapist_id, child_id, session_date, start_time, end_time, status,
            children!child_id (first_name, last_name)
        ''').eq('session_date', current_date.isoformat()).eq('therapist_id', therapist_id).order('start_time').execute()
        
        handle_supabase_error(result)
        
        if not result.data:
            return {
                "success": True,
                "message": "No sessions to schedule notifications for",
                "scheduled_count": 0
            }
        
        scheduled_count = 0
        next_upcoming_session = None
        
        # Find the next upcoming session (first session with start_time > current_time)
        for session in result.data:
            session_start_time = _parse_time_string(session['start_time'])
            session_start_datetime = _combine_datetime(current_date, session_start_time)
            
            # Check if this session is in the future and scheduled
            if (session_start_datetime > current_datetime and 
                session['status'] == SESSION_STATUS["SCHEDULED"]):
                
                next_upcoming_session = session
                break
        
        if next_upcoming_session:
            session_start_time = _parse_time_string(next_upcoming_session['start_time'])
            session_start_datetime = _combine_datetime(current_date, session_start_time)
            
            student_name = "Unknown Student"
            if next_upcoming_session.get('children'):
                child = next_upcoming_session['children']
                student_name = f"{child['first_name']} {child['last_name']}"
            
            # Calculate time until session
            time_until_session = (session_start_datetime - current_datetime).total_seconds() / 60
            
            # Schedule 5-minute reminder if session is more than 5 minutes away
            if time_until_session > 5:
                notification_time = session_start_datetime - timedelta(minutes=5)
                
                # Store notification schedule globally for the monitoring system
                global SCHEDULED_NOTIFICATIONS
                notification_id = f"5min-{next_upcoming_session['id']}-{int(notification_time.timestamp())}"
                
                SCHEDULED_NOTIFICATIONS[notification_id] = {
                    "notification_id": notification_id,
                    "type": "SESSION_REMINDER",
                    "message": f"Your session with {student_name} is starting in 5 minutes.",
                    "session_id": str(next_upcoming_session['id']),
                    "therapist_id": therapist_id,
                    "student_name": student_name,
                    "session_start_time": session_start_datetime.isoformat(),
                    "notification_time": notification_time.isoformat(),
                    "timestamp": notification_time.isoformat()
                }
                
                scheduled_count = 1
                logger.info(f"Scheduled 5-minute notification for session {next_upcoming_session['id']} at {notification_time}")
                
        return {
            "success": True,
            "message": f"Scheduled notifications for next upcoming session",
            "scheduled_count": scheduled_count,
            "next_session_id": next_upcoming_session['id'] if next_upcoming_session else None,
            "next_notification_time": (session_start_datetime - timedelta(minutes=5)).isoformat() if next_upcoming_session and time_until_session > 5 else None
        }
        
    except Exception as e:
        logger.error(f"Error scheduling session notifications for therapist {therapist_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to schedule notifications: {str(e)}",
            "scheduled_count": 0
        }

# =================================
# Smart Scheduler Initialization
# =================================

# Initialize smart scheduler instance (removed - using frontend scheduling)


# ==================== MONITORING SERVICE WRAPPER FUNCTIONS ====================
# Wrapper functions for compatibility with monitoring API endpoints (removed - using frontend scheduling)

# =================================
# CONTINUOUS MONITORING FUNCTIONS
# =================================
# Simple stub implementations - frontend handles actual scheduling

async def get_upcoming_session_notifications() -> List[Dict[str, Any]]:
    """
    Get upcoming session notifications (stub - frontend handles scheduling)
    """
    return []

async def create_session_notifications(session_id: int) -> bool:
    """
    Create session notifications (stub - frontend handles scheduling)
    """
    return True

async def get_continuous_notifications() -> List[Dict[str, Any]]:
    """
    Get continuous notifications (stub - frontend handles scheduling)
    """
    return []

async def handle_dynamic_schedule_changes(therapist_id: int) -> Dict[str, Any]:
    """
    Handle dynamic schedule changes (stub - frontend handles scheduling)
    """
    return {"success": True, "message": "Schedule changes handled"}

# =================================
# MONITORING SERVICE FUNCTIONS
# =================================
# Simple stub implementations for monitoring API compatibility

def get_monitoring_service_status() -> Dict[str, Any]:
    """
    Get monitoring service status (stub - frontend handles scheduling)
    """
    return {
        "service_running": False,
        "message": "Frontend handles scheduling",
        "last_check": utc_now_iso()
    }

async def trigger_manual_status_update() -> List[SessionStatusResponse]:
    """
    Trigger manual status update (calls auto_update_session_statuses)
    """
    return await auto_update_session_statuses()

async def trigger_manual_notification_check() -> List[Dict[str, Any]]:
    """
    Trigger manual notification check (stub - frontend handles scheduling)
    """
    return []

# =================================
# SMART NOTIFICATION SYSTEM FUNCTIONS
# =================================
# Simple stub implementations for smart notification system compatibility

async def start_smart_notification_system() -> Dict[str, Any]:
    """
    Start smart notification system (stub - frontend handles scheduling)
    """
    return {
        "success": True,
        "message": "Smart notification system started (frontend handles scheduling)",
        "system_status": "active"
    }

async def stop_smart_notification_system() -> Dict[str, Any]:
    """
    Stop smart notification system (stub - frontend handles scheduling)
    """
    return {
        "success": True,
        "message": "Smart notification system stopped (frontend handles scheduling)",
        "system_status": "inactive"
    }

async def get_smart_notification_system_status() -> Dict[str, Any]:
    """
    Get smart notification system status (stub - frontend handles scheduling)
    """
    return {
        "system_running": True,
        "message": "Frontend handles scheduling",
        "scheduled_notifications": 0,
        "last_activity": utc_now_iso()
    }

async def refresh_smart_notification_system() -> Dict[str, Any]:
    """
    Refresh smart notification system (stub - frontend handles scheduling)
    """
    return {
        "success": True,
        "message": "Smart notification system refreshed (frontend handles scheduling)",
        "refreshed_count": 0
    }