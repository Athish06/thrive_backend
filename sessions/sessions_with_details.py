"""
Enhanced session retrieval with complete details
"""
from typing import List, Optional
from datetime import date
from db import get_supabase_client
import logging

logger = logging.getLogger(__name__)

async def get_sessions_with_details(therapist_id: int, session_date: Optional[str] = None) -> List[dict]:
    """
    Retrieve sessions with complete details including student name and activity information
    
    Args:
        therapist_id: ID of the therapist
        session_date: Optional date filter in YYYY-MM-DD format
    
    Returns:
        List of sessions with student names and activity details
    """
    try:
        supabase = get_supabase_client()
        
        # Build query with joins
        query = supabase.table('sessions').select('''
            id,
            child_id,
            therapist_id,
            session_date,
            start_time,
            end_time,
            status,
            therapist_notes,
            created_at,
            updated_at,
            children!child_id (
                id,
                first_name,
                last_name
            )
        ''').eq('therapist_id', therapist_id)
        
        # Add date filter if provided
        if session_date:
            query = query.eq('session_date', session_date)
        
        # Execute query
        result = query.order('session_date', desc=False).order('start_time', desc=False).execute()
        
        if not result.data:
            logger.info(f"No sessions found for therapist {therapist_id} on date {session_date}")
            return []
        
        sessions_with_details = []
        
        for session in result.data:
            # Get student name from joined children table
            student_name = "Unknown Student"
            if session.get('children'):
                child = session['children']
                student_name = f"{child.get('first_name', '')} {child.get('last_name', '')}".strip()
            
            # Get activity details for this session
            activity_name = None
            try:
                # Query child_goals to find activities for this child
                goals_result = supabase.table('child_goals').select('''
                    id,
                    activity_id,
                    activities!activity_id (
                        id,
                        activity_name,
                        activity_type
                    )
                ''').eq('child_id', session['child_id']).limit(1).execute()
                
                if goals_result.data and len(goals_result.data) > 0:
                    goal = goals_result.data[0]
                    if goal.get('activities'):
                        activity = goal['activities']
                        activity_name = activity.get('activity_name', 'Therapy Session')
                        activity_type = activity.get('activity_type', '')
                        if activity_type:
                            activity_name = f"{activity_name} ({activity_type})"
            except Exception as e:
                logger.warning(f"Could not fetch activity for session {session['id']}: {e}")
            
            # Build session detail object
            session_detail = {
                'id': session['id'],
                'child_id': session['child_id'],
                'therapist_id': session['therapist_id'],
                'session_date': session['session_date'],
                'session_time': session.get('start_time'),
                'start_time': session.get('start_time'),
                'end_time': session.get('end_time'),
                'status': session.get('status'),
                'therapist_notes': session.get('therapist_notes'),
                'created_at': session.get('created_at'),
                'updated_at': session.get('updated_at'),
                'child_name': student_name,
                'session_type': activity_name or 'Therapy Session'
            }
            
            sessions_with_details.append(session_detail)
        
        logger.info(f"Retrieved {len(sessions_with_details)} sessions with details for therapist {therapist_id}")
        return sessions_with_details
        
    except Exception as e:
        logger.error(f"Error getting sessions with details: {str(e)}")
        raise Exception(f"Database error: {str(e)}")
