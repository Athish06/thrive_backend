import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from db import get_supabase_client, format_supabase_response, handle_supabase_error

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================
# Utility functions for data processing and transformation

def _calculate_age_from_birth_date(birth_date_str: Optional[str]) -> Optional[int]:
    """
    Calculate age from birth date string
    - Handles date parsing and age calculation logic
    - Returns None if birth date is not provided or invalid
    - Used across all student retrieval functions
    """
    if not birth_date_str:
        return None
    
    try:
        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
        today = date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid birth date format: {birth_date_str}, error: {e}")
        return None

def _format_therapist_name(therapist_info: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Format therapist information into full name
    - Returns 'First Last' format or None if not available
    - Handles missing or incomplete therapist data
    """
    if not therapist_info:
        return None
    
    first_name = therapist_info.get('first_name', '')
    last_name = therapist_info.get('last_name', '')
    
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return None

def _get_default_goals() -> List[str]:
    """
    Get default therapeutic goals for students
    - Used as fallback when no specific goals are defined
    - Consistent across all student records
    """
    return [
        'Improve communication skills',
        'Develop social interaction',
        'Enhance cognitive abilities'
    ]

def _sanitize_assessment_details(raw_details: Any) -> Tuple[Dict[str, Any], bool, bool]:
    """Validate and normalize assessment entries for storage and rule checks."""
    clean_details: Dict[str, Any] = {}
    has_clinical_snapshot = False
    has_non_snapshot = False

    if not isinstance(raw_details, dict):
        return clean_details, has_clinical_snapshot, has_non_snapshot

    for tool_id, detail in raw_details.items():
        if not isinstance(tool_id, str) or not isinstance(detail, dict):
            continue

        items = detail.get('items')
        if not isinstance(items, dict):
            continue

        valid_items: Dict[str, Any] = {}
        for item_key, score in items.items():
            if isinstance(score, (int, float)):
                valid_items[item_key] = score
            elif isinstance(score, str):
                try:
                    parsed_score = float(score)
                    valid_items[item_key] = int(parsed_score) if parsed_score.is_integer() else parsed_score
                except ValueError:
                    continue

        if not valid_items:
            continue

        clean_entry: Dict[str, Any] = {'items': valid_items}
        average_score = detail.get('average')
        if isinstance(average_score, (int, float)):
            clean_entry['average'] = average_score
        elif isinstance(average_score, str):
            try:
                parsed_average = float(average_score)
                clean_entry['average'] = int(parsed_average) if parsed_average.is_integer() else parsed_average
            except ValueError:
                pass

        clean_details[tool_id] = clean_entry

        if tool_id == 'clinical-snapshots':
            has_clinical_snapshot = True
        else:
            has_non_snapshot = True

    return clean_details, has_clinical_snapshot, has_non_snapshot

def _transform_student_data(student: Dict[str, Any], include_therapist_name: bool = True) -> Dict[str, Any]:
    """
    Transform raw student data from database to frontend format
    
    Args:
        student: Raw student data from Supabase
        include_therapist_name: Whether to include formatted therapist name
    
    Returns:
        Dictionary in frontend-expected format
    
    Usage:
        - Centralizes student data transformation logic
        - Eliminates code duplication across all student functions
        - Ensures consistent data format for frontend consumption
    """
    # Calculate age using helper function
    age = _calculate_age_from_birth_date(student.get('date_of_birth'))
    
    # Extract profile details safely
    profile_details = student.get('profile_details', {})
    
    # Format therapist name if requested and available
    primary_therapist = None
    if include_therapist_name:
        therapist_info = student.get('therapists')
        primary_therapist = _format_therapist_name(therapist_info)
    
    # Get goals with fallback to defaults
    goals = profile_details.get('goals')
    if not goals:
        goals = _get_default_goals()
    
    # Transform to standardized frontend format
    transformed_student = {
        'id': student['id'],
        'name': f"{student['first_name']} {student['last_name']}",
        'firstName': student['first_name'],
        'lastName': student['last_name'],
        'age': age,
        'dateOfBirth': student['date_of_birth'],
        'enrollmentDate': student['enrollment_date'],
        'diagnosis': student.get('diagnosis'),
        'status': student.get('status', 'active'),
        'primaryTherapist': primary_therapist,
        'primaryTherapistId': student.get('primary_therapist_id'),
        'profileDetails': profile_details,
        'medicalDiagnosis': student.get('medical_diagnosis'),
        'assessmentDetails': student.get('assessment_details'),
        'driveUrl': student.get('drive_url'),
        'priorDiagnosis': student.get('prior_diagnosis', False),
        'photo': profile_details.get('photo_url'),
        'progressPercentage': profile_details.get('progress_percentage', 75),
        'nextSession': profile_details.get('next_session'),
        'goals': goals
    }
    
    return transformed_student

def _get_student_base_query() -> str:
    """
    Get the base SQL query for student data retrieval
    - Ensures consistent field selection across all student queries
    - Includes necessary joins and relationships
    """
    return """
        id,
        first_name,
        last_name,
        date_of_birth,
        enrollment_date,
        diagnosis,
        status,
        primary_therapist_id,
        profile_details,
        medical_diagnosis,
        assessment_details,
        drive_url,
        prior_diagnosis,
        therapists!primary_therapist_id (
            id,
            first_name,
            last_name,
            email
        )
    """

def _handle_student_query_error(operation: str, context: str, error: Exception) -> None:
    """
    Standardized error handling for student database operations
    
    Args:
        operation: The operation being performed (e.g., "fetch", "create")
        context: Additional context (e.g., "student ID 123")
        error: The exception that occurred
    """
    error_message = f"Error {operation} {context}: {error}"
    logger.error(error_message)
    raise Exception(f"Failed to {operation} {context}: {str(error)}")

# ==================== STUDENT RETRIEVAL FUNCTIONS ====================
# Functions for fetching and querying student information

def get_all_students() -> List[Dict[str, Any]]:
    """
    Retrieve all students from the system
    
    Returns:
        List of student dictionaries in frontend format
    
    Usage:
        - Used for system-wide student overview and reporting
        - Powers administrative dashboards and student lists
        - Accessible by authenticated users for general student information
        - Includes therapist assignment information
    """
    try:
        client = get_supabase_client()
        
        # Query using standardized base query
        response = client.table('children').select(_get_student_base_query()).execute()
        
        handle_supabase_error(response)
        students = format_supabase_response(response)
        
        if not students:
            logger.info("No students found in the system")
            return []
        
        # Transform all students using helper function
        transformed_students = [
            _transform_student_data(student, include_therapist_name=True) 
            for student in students
        ]
        
        logger.info(f"Successfully fetched {len(transformed_students)} students")
        return transformed_students
        
    except Exception as e:
        _handle_student_query_error("fetch", "all students", e)

def get_student_by_id(student_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific student by their ID
    
    Args:
        student_id: Unique identifier of the student to retrieve
    
    Returns:
        Student dictionary in frontend format or None if not found
    
    Usage:
        - Used for detailed student information displays
        - Powers individual student profile pages
        - Restricted to therapists for privacy protection
        - Includes complete student and therapist information
    """
    try:
        client = get_supabase_client()
        
        response = client.table('children').select(_get_student_base_query()).eq('id', student_id).execute()
        
        handle_supabase_error(response)
        students = format_supabase_response(response)
        
        if not students:
            logger.info(f"Student {student_id} not found")
            return None
        
        # Transform single student using helper function
        transformed_student = _transform_student_data(students[0], include_therapist_name=True)
        
        logger.info(f"Successfully fetched student {student_id}")
        return transformed_student
        
    except Exception as e:
        _handle_student_query_error("fetch", f"student {student_id}", e)

def get_students_by_therapist(therapist_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all students assigned to a specific therapist
    
    Args:
        therapist_id: ID of the therapist whose students to retrieve
    
    Returns:
        List of student dictionaries assigned to the therapist
    
    Usage:
        - Powers therapist dashboard student caseload displays
        - Used for therapist-specific student management
        - Enables personalized student assignment workflows
        - Restricts data access to assigned students only
    """
    try:
        client = get_supabase_client()
        
        response = client.table('children').select(_get_student_base_query()).eq('primary_therapist_id', therapist_id).execute()
        
        handle_supabase_error(response)
        students = format_supabase_response(response)
        
        if not students:
            logger.info(f"No students found for therapist {therapist_id}")
            return []
        
        # Transform students (no need for therapist name since it's the same therapist)
        transformed_students = [
            _transform_student_data(student, include_therapist_name=False) 
            for student in students
        ]
        
        logger.info(f"Successfully fetched {len(transformed_students)} students for therapist {therapist_id}")
        return transformed_students
        
    except Exception as e:
        _handle_student_query_error("fetch", f"students for therapist {therapist_id}", e)

def get_temp_students_by_therapist(therapist_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve students awaiting assessment completion assigned to a therapist
    
    Args:
        therapist_id: ID of the therapist whose temporary students to retrieve
    
    Returns:
        List of temporary student dictionaries pending assessment scores
    
    Usage:
        - Dedicated lane for enrollments missing assessments or documentation
        - Supports therapist follow-up on outstanding evaluation tasks
        - Keeps in-progress learners separate from fully active caseloads
    """
    try:
        client = get_supabase_client()
        
        response = (
            client
            .table('children')
            .select(_get_student_base_query())
            .eq('primary_therapist_id', therapist_id)
            .eq('status', 'assessment_due')
            .order('enrollment_date', desc=True)
        ).execute()
        
        handle_supabase_error(response)
        students = format_supabase_response(response)
        
        if not students:
            logger.info(f"No temporary students found for therapist {therapist_id}")
            return []
        
        # Transform temporary students
        transformed_students = [
            _transform_student_data(student, include_therapist_name=False) 
            for student in students
        ]
        
        logger.info(f"Successfully fetched {len(transformed_students)} temporary students for therapist {therapist_id}")
        return transformed_students
        
    except Exception as e:
        _handle_student_query_error("fetch", f"temporary students for therapist {therapist_id}", e)

# ==================== STUDENT MANAGEMENT FUNCTIONS ====================
# Functions for creating, updating, and managing student records

def enroll_student(student_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enroll a new student in the system
    
    Args:
        student_data: Dictionary containing student enrollment information
            - firstName, lastName: Student name
            - dateOfBirth: Birth date for age calculation
            - therapistId: Assigned primary therapist
            - diagnosis, medicalDiagnosis: Diagnostic information
            - priorDiagnosis: Whether student has existing diagnosis
            - goals: List of therapeutic goals
            - profileInfo: Additional profile metadata
    
    Returns:
        Dictionary representing the newly enrolled student
    
    Usage:
        - Creates new student records in the system
        - Assigns students to primary therapists
        - Initializes therapeutic goals and progress tracking
        - Supports both new and transfer student enrollments
    """
    try:
        client = get_supabase_client()
        
        # Build comprehensive profile details
        profile_details_payload = {
            'age': student_data.get('age'),
            'goals': student_data.get('goals', _get_default_goals()),
            'progress_percentage': 0,  # Initialize progress at 0%
            'enrollment_notes': f"Enrolled on {datetime.now().date().isoformat()}"
        }
        
        # Include additional profile information if provided
        if student_data.get('profileInfo'):
            profile_details_payload['profile_info'] = student_data.get('profileInfo')
        
        # Insert new student record with comprehensive data
        response = client.table('children').insert({
            'first_name': student_data['firstName'],
            'last_name': student_data['lastName'], 
            'date_of_birth': student_data['dateOfBirth'],
            'enrollment_date': datetime.now().date().isoformat(),
            'diagnosis': student_data.get('diagnosis'),
            'status': student_data.get('status', 'active'),
            'primary_therapist_id': student_data['therapistId'],
            'medical_diagnosis': student_data.get('medicalDiagnosis'),
            'drive_url': student_data.get('driveUrl'),
            'prior_diagnosis': student_data.get('priorDiagnosis', False),
            'assessment_details': student_data.get('assessmentDetails'),
            'profile_details': profile_details_payload
        }).execute()
        
        handle_supabase_error(response)
        students = format_supabase_response(response)
        
        if not students:
            raise Exception("Failed to create student - no data returned from database")
        
        student = students[0]
        
        # Transform the new student data using helper function
        transformed_student = _transform_student_data(student, include_therapist_name=False)
        
        # Override some fields with enrollment-specific data
        transformed_student.update({
            'progressPercentage': 0,
            'goals': student_data.get('goals', _get_default_goals()),
            'enrollmentDate': student['enrollment_date']
        })
        
        logger.info(f"Successfully enrolled student {student['id']} - {student['first_name']} {student['last_name']}")
        return transformed_student
        
    except Exception as e:
        _handle_student_query_error("enroll", "new student", e)

def update_student_assessment(student_id: int, therapist_id: int, assessment_updates: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Update assessment details and promote learner status when rules are satisfied."""
    try:
        client = get_supabase_client()

        response = (
            client
            .table('children')
            .select(_get_student_base_query())
            .eq('id', student_id)
            .execute()
        )

        handle_supabase_error(response)
        students = format_supabase_response(response)

        if not students:
            raise ValueError("Student not found")

        student_record = students[0]

        if student_record.get('primary_therapist_id') != therapist_id:
            raise PermissionError("You do not have permission to update this learner.")

        existing_clean, _, _ = _sanitize_assessment_details(student_record.get('assessment_details'))
        incoming_payload = assessment_updates if isinstance(assessment_updates, dict) else {}
        incoming_clean, _, _ = _sanitize_assessment_details(incoming_payload)

        combined_details = existing_clean.copy()

        for tool_id, detail in incoming_payload.items():
            if detail is None:
                combined_details.pop(tool_id, None)
                continue

            if tool_id in incoming_clean:
                combined_details[tool_id] = incoming_clean[tool_id]
            elif isinstance(detail, dict):
                items = detail.get('items')
                if isinstance(items, dict) and not any(isinstance(score, (int, float, str)) for score in items.values()):
                    combined_details.pop(tool_id, None)

        final_clean, has_clinical_snapshot, has_non_snapshot = _sanitize_assessment_details(combined_details)

        prior_diagnosis = bool(student_record.get('prior_diagnosis'))
        meets_requirement = bool(final_clean) and (
            has_clinical_snapshot if prior_diagnosis else (has_clinical_snapshot or has_non_snapshot)
        )

        new_status = 'active' if meets_requirement else 'assessment_due'

        update_payload = {
            'assessment_details': final_clean or None,
            'status': new_status
        }

        update_response = client.table('children').update(update_payload).eq('id', student_id).execute()
        handle_supabase_error(update_response)

        updated_student = get_student_by_id(student_id)
        if not updated_student:
            raise ValueError("Failed to fetch updated student data")

        logger.info(
            "Updated assessment for student %s by therapist %s; status set to %s",
            student_id,
            therapist_id,
            new_status
        )

        return updated_student

    except (PermissionError, ValueError):
        raise
    except Exception as e:
        _handle_student_query_error("update assessment for", f"student {student_id}", e)

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional student management functions

# TODO: Implement student update functionality
# def update_student(student_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
#     """Update an existing student's information"""
#     pass

# TODO: Implement student status management
# def update_student_status(student_id: int, new_status: str) -> bool:
#     """Update student's enrollment status (active, inactive, graduated, etc.)"""
#     pass

# TODO: Implement student transfer functionality
# def transfer_student(student_id: int, new_therapist_id: int) -> Dict[str, Any]:
#     """Transfer student to a different primary therapist"""
#     pass

# TODO: Implement student search functionality
# def search_students(search_term: str, therapist_id: Optional[int] = None) -> List[Dict[str, Any]]:
#     """Search students by name, diagnosis, or other criteria"""
#     pass

# TODO: Implement student progress tracking
# def update_student_progress(student_id: int, progress_percentage: int, notes: str) -> bool:
#     """Update student's therapy progress and notes"""
#     pass