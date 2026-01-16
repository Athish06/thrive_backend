from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr
from users.users import create_user
from authentication.authh import authenticate_user_detailed, create_access_token, get_current_user, update_last_login
from users.profiles import get_therapist_profile, get_parent_profile, update_therapist_profile, update_parent_profile
from users.settings import get_therapist_settings, update_therapist_profile_settings, update_therapist_account_settings, get_therapist_profile_settings, get_therapist_account_settings
from students.students import (
    get_all_students,
    get_student_by_id,
    get_students_by_therapist,
    get_temp_students_by_therapist,
    enroll_student,
    update_student_assessment as update_student_assessment_record
)
from notes.notes import get_notes_by_date_and_therapist, create_session_note, get_notes_with_dates_for_therapist, SessionNoteCreate, SessionNoteResponse
from sessions.sessions import (
    create_session, get_sessions_by_therapist, get_todays_sessions_by_therapist, get_session_by_id, update_session, delete_session,
    add_activity_to_session, get_session_activities, get_available_child_goals, get_master_activities, get_assessment_tool_activities,
    remove_activity_from_session, assign_ai_activity_to_child, mark_activity_completed, update_session_activity, SessionCreate, SessionUpdate, SessionResponse,
    SessionActivityCreate, SessionActivityUpdate, SessionActivityResponse, ChildGoalResponse, ActivityResponse, SessionComplete
)
from sessions.session_status import (
    update_session_status, start_session, complete_session, cancel_session,
    get_sessions_needing_status_update, auto_update_session_statuses,
    get_upcoming_session_notifications, create_session_notifications, get_todays_sessions_status,
    start_smart_notification_system, stop_smart_notification_system, 
    get_smart_notification_system_status, refresh_smart_notification_system,
    check_sessions_on_login, schedule_session_notifications_for_day,
    get_continuous_notifications, handle_dynamic_schedule_changes,
    get_monitoring_service_status, trigger_manual_status_update, trigger_manual_notification_check,
    SessionStatusUpdate, SessionNotification, SessionStatusResponse
)
from sessions.rescheduleSessions import (
    check_session_ready_for_start,
    cascade_reschedule_sessions,
    CascadeRescheduleRequest,
)
from ai_services import (
    extract_text_from_file,
    suggest_therapeutic_activities,
    create_activity_chat_session,
    generate_activity_chat_messages
)
# import psycopg2  # Commented out - using Supabase now
from typing import Optional, List, Dict, Any, Literal
from datetime import timedelta, date, datetime
import logging
import os
import shutil
from uuid import uuid4
from fastapi.staticfiles import StaticFiles
from utils.date_utils import utc_now_iso
from db import get_supabase_client
import threading 
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ThrivePath API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure local files directory exists and mount it for static serving
FILES_DIR = os.path.join(os.path.dirname(__file__), "files")
os.makedirs(FILES_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=FILES_DIR), name="files")


# ==================== PYDANTIC MODELS ====================

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: str
    name: Optional[str] = None  # Added to include full name from profile

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class UserRegistration(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    password: str
    role: str
    phone: Optional[str] = None
    address: Optional[str] = None
    emergencyContact: Optional[str] = None

class TherapistProfile(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    bio: Optional[str] = None
    is_active: bool
    created_at: str

class ParentProfile(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    is_active: bool
    created_at: str

class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None  # For therapists
    address: Optional[str] = None  # For parents
    emergency_contact: Optional[str] = None  # For parents

class StudentResponse(BaseModel):
    id: int
    name: str
    firstName: str
    lastName: str
    age: Optional[int] = None
    dateOfBirth: Optional[str] = None
    enrollmentDate: Optional[str] = None
    diagnosis: Optional[str] = None
    status: str
    primaryTherapist: Optional[str] = None
    primaryTherapistId: Optional[int] = None
    profileDetails: Optional[dict] = None
    medicalDiagnosis: Optional[dict] = None
    assessmentDetails: Optional[dict] = None
    driveUrl: Optional[str] = None
    priorDiagnosis: Optional[bool] = False
    photo: Optional[str] = None
    progressPercentage: Optional[int] = 75
    nextSession: Optional[str] = None
    goals: Optional[List[str]] = []

class StudentEnrollment(BaseModel):
    firstName: str
    lastName: str
    dateOfBirth: str
    diagnosis: Optional[str] = None
    medicalDiagnosis: Optional[dict] = None
    driveUrl: Optional[str] = None
    priorDiagnosis: Optional[bool] = False
    age: Optional[int] = None
    goals: Optional[List[str]] = []
    therapistId: int
    profileInfo: Optional[dict] = None
    assessmentDetails: Optional[dict] = None
    # File upload information
    uploadedFilePath: Optional[str] = None
    uploadedFileName: Optional[str] = None

class StudentAssessmentUpdate(BaseModel):
    assessmentDetails: Optional[Dict[str, Any]] = None

class DeleteFileRequest(BaseModel):
    filePath: str

class UploadToSupabaseRequest(BaseModel):
    file_path: str
    original_name: str
    student_id: int

class TherapistSettings(BaseModel):
    profile_section: Optional[Dict[str, Any]] = {}
    account_section: Optional[Dict[str, Any]] = {}

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]

class ActivitySuggestionRequest(BaseModel):
    learner_profile: Dict[str, Any]
    user_query: str

class ActivitySuggestionResponse(BaseModel):
    id: str
    title: str
    description: str
    category: str
    difficulty: str
    duration: int
    materials: List[str]
    goals: List[str]
    instructions: List[str]
    adaptations: Optional[List[str]] = []
    safety_notes: Optional[List[str]] = []

class ActivityAssignmentRequest(BaseModel):
    activity: Dict[str, Any]  # AI-suggested activity data
    child_id: int

class ActivityAssignmentResponse(BaseModel):
    success: bool
    message: str
    child_goal_id: Optional[int] = None
    activity_id: Optional[int] = None


class ActivityChatSessionRequest(BaseModel):
    learner_profile: Dict[str, Any]


class ActivityChatSessionResponse(BaseModel):
    session_id: str


class AssistantMessageModel(BaseModel):
    role: Literal['assistant'] = 'assistant'
    kind: Literal['text', 'activities']
    content: Optional[str] = None
    activities: Optional[List[Dict[str, Any]]] = None


class ActivityFocusContext(BaseModel):
    label: str
    activities: List[Dict[str, Any]]
    instruction: Optional[str] = None
    source: Optional[str] = None


class ActivityChatMessageRequest(BaseModel):
    message: str
    ai_preferences: Optional[str] = None  # Custom AI behavior instructions
    session_notes: Optional[List[Dict[str, Any]]] = None  # Selected session notes with context
    focus_context: Optional[ActivityFocusContext] = None  # Therapist-selected activities to emphasise
    notes_instruction: Optional[str] = None  # Therapist guidance on how to use attached notes


class ActivityChatMessageResponse(BaseModel):
    session_id: str
    messages: List[AssistantMessageModel]


class AIPreferencesRequest(BaseModel):
    ai_instructions: str  # Custom instructions for AI behavior


class AIPreferencesResponse(BaseModel):
    child_id: int
    ai_instructions: str
    updated_at: str


class SessionNotesQueryParams(BaseModel):
    child_id: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SessionNoteItem(BaseModel):
    session_id: int
    session_date: str
    start_time: str
    end_time: str
    therapist_notes: Optional[str] = None
    status: str


class RescheduledSessionItem(BaseModel):
    session_id: int
    student_name: Optional[str] = None
    previous_date: str
    new_date: str


class CascadeRescheduleResponse(BaseModel):
    total_updated: int
    sessions: List[RescheduledSessionItem]
    include_weekends: bool



# ==================== SYSTEM UTILITIES ====================
# Basic system health and connectivity endpoints

@app.get("/")
async def root():
    """Root endpoint - Basic API status check"""
    return {"message": "ThrivePath API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    """Health check endpoint - Service availability monitoring"""
    return {"status": "healthy", "service": "ThrivePath API"}

@app.get("/api/test-db")
async def test_database_connection():
    """Test Supabase database connection - Database connectivity verification"""
    try:
        from db import test_connection
        success, message = test_connection()
        if success:
            return {"status": "success", "message": message, "database": "Supabase PostgreSQL"}
        else:
            raise HTTPException(status_code=500, detail=f"Database connection failed: {message}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database test failed: {str(e)}")

@app.get("/api/test-supabase")
async def test_supabase_client():
    """Test Supabase client connection - Supabase client SDK verification"""
    try:
        from db import test_supabase_client, init_supabase_client
        
        # Try to initialize client first
        client = init_supabase_client()
        if not client:
            return {
                "status": "warning", 
                "message": "Supabase client not available - please add SUPABASE_ANON_KEY to .env file",
                "client": "Not initialized"
            }
        
        success, message = test_supabase_client()
        if success:
            return {"status": "success", "message": message, "client": "Supabase Python Client"}
        else:
            return {"status": "error", "message": message, "client": "Supabase Python Client"}
    except Exception as e:
        return {"status": "error", "message": f"Supabase client test failed: {str(e)}"}

# ==================== AUTHENTICATION & AUTHORIZATION ====================
# User authentication, registration, and token management

@app.post("/api/login", response_model=LoginResponse)
async def login_user(user_credentials: UserLogin):
    """
    User authentication endpoint
    - Validates email/password credentials
    - Returns JWT access token for authenticated sessions
    - Updates last login timestamp
    """
    try:
        # Authenticate user with detailed error messages
        user, error_message = authenticate_user_detailed(user_credentials.email, user_credentials.password)
        
        if not user:
            if error_message == "User not found":
                raise HTTPException(
                    status_code=404,
                    detail="User not found. Please check your email or register for a new account."
                )
            elif error_message == "Invalid password":
                raise HTTPException(
                    status_code=401,
                    detail="Invalid email or password. Please check your credentials."
                )
            elif error_message == "Account is inactive":
                raise HTTPException(
                    status_code=403,
                    detail="Your account is inactive. Please contact support."
                )
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication failed"
                )
        
        # Update last login
        update_last_login(user["id"])
        
        # Create access token
        access_token = create_access_token(
            data={
                "sub": str(user["id"]),  # Convert to string for JWT
                "email": user["email"], 
                "role": user["role"]
            }
        )
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                is_verified=user["is_verified"],
                created_at=str(user.get("created_at", ""))
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        logger.error(f"User data: {user}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/register", response_model=UserResponse)
async def register_user(user_data: UserRegistration):
    """
    User registration endpoint
    - Creates new user accounts for therapists and parents
    - Validates role-based registration data
    - Creates associated profile records
    """
    try:
        # Validate role
        if user_data.role not in ["therapist", "parent"]:
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'therapist' or 'parent'")
        
        # Create user in database with profile data
        new_user = create_user(
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
            first_name=user_data.firstName,
            last_name=user_data.lastName,
            phone=user_data.phone,
            address=user_data.address,
            emergency_contact=user_data.emergencyContact
        )
        
        return UserResponse(
            id=new_user["id"],
            email=new_user["email"],
            role=new_user["role"],
            is_active=new_user["is_active"],
            is_verified=new_user["is_verified"],
            created_at=str(new_user.get("created_at", ""))
        )
        
    # COMMENTED OUT: psycopg2 specific error handling - replaced with general exception handling
    # except psycopg2.IntegrityError as e:
    #     if "unique constraint" in str(e).lower():
    #         raise HTTPException(status_code=400, detail="Email already exists")
    #     raise HTTPException(status_code=400, detail="Database error occurred")
    except ValueError as e:
        # This handles email already exists and other validation errors from Supabase
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate" in error_msg:
            raise HTTPException(status_code=400, detail="Email already exists")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user information
    - Returns user data with profile name if available
    - Used for user context and navigation personalization
    """
    # Get profile data to include name
    profile_name = None
    try:
        if current_user["role"] == "therapist":
            profile = get_therapist_profile(current_user["id"])
            if profile:
                profile_name = f"{profile['first_name']} {profile['last_name']}"
        elif current_user["role"] == "parent":
            profile = get_parent_profile(current_user["id"])
            if profile:
                profile_name = f"{profile['first_name']} {profile['last_name']}"
    except Exception as e:
        # If profile fetch fails, continue without name
        print(f"Warning: Could not fetch profile for user {current_user['id']}: {e}")
    
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        is_verified=current_user["is_verified"],
        created_at=str(current_user.get("created_at", "")),
        name=profile_name or current_user["email"]  # Fallback to email if no profile name
    )

@app.get("/api/test-auth")
async def test_auth(current_user: dict = Depends(get_current_user)):
    """
    Authentication test endpoint
    - Verifies JWT token validation is working
    - Used for debugging authentication issues
    """
    return {
        "message": "Authentication successful",
        "user": current_user
    }

# ==================== USER PROFILE MANAGEMENT ====================
# User profile retrieval and updates for therapists and parents

@app.get("/api/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile information
    - Returns role-specific profile data (therapist or parent)
    - Used for profile displays and account management
    """
    try:
        if current_user["role"] == "therapist":
            profile = get_therapist_profile(current_user["id"])
            if not profile:
                raise HTTPException(status_code=404, detail="Therapist profile not found")
            return TherapistProfile(**{
                **profile,
                "created_at": str(profile.get("created_at", ""))
            })
        elif current_user["role"] == "parent":
            profile = get_parent_profile(current_user["id"])
            if not profile:
                raise HTTPException(status_code=404, detail="Parent profile not found")
            return ParentProfile(**{
                **profile,
                "created_at": str(profile.get("created_at", ""))
            })
        else:
            raise HTTPException(status_code=400, detail="Invalid user role")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get profile")

@app.put("/api/profile")
async def update_user_profile(
    profile_data: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update current user's profile information
    - Accepts partial updates for profile fields
    - Role-specific field validation and updates
    """
    try:
        update_data = profile_data.dict(exclude_unset=True)
        
        if current_user["role"] == "therapist":
            updated_profile = update_therapist_profile(current_user["id"], **update_data)
            if not updated_profile:
                raise HTTPException(status_code=404, detail="Therapist profile not found")
            return TherapistProfile(**{
                **updated_profile,
                "created_at": str(updated_profile.get("created_at", ""))
            })
        elif current_user["role"] == "parent":
            updated_profile = update_parent_profile(current_user["id"], **update_data)
            if not updated_profile:
                raise HTTPException(status_code=404, detail="Parent profile not found")
            return ParentProfile(**{
                **updated_profile,
                "created_at": str(updated_profile.get("created_at", ""))
            })
        else:
            raise HTTPException(status_code=400, detail="Invalid user role")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update profile")

# ==================== THERAPIST SETTINGS MANAGEMENT ====================
# Therapist settings retrieval and updates for profile and account sections

@app.get("/api/settings")
async def get_user_settings(current_user: dict = Depends(get_current_user)):
    """
    Get current user's settings information
    - Returns role-specific settings data (therapist only for now)
    - Used for settings displays and account management
    """
    try:
        if current_user["role"] == "therapist":
            settings = get_therapist_settings(current_user["id"])
            if not settings:
                raise HTTPException(status_code=404, detail="Therapist settings not found")
            return TherapistSettings(**settings)
        else:
            raise HTTPException(status_code=400, detail="Settings only available for therapists")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get settings")

@app.put("/api/settings/profile")
async def update_user_profile_settings(
    settings_data: SettingsUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update current user's profile section settings
    - Only updates the profile_section JSONB field
    - Used when saving from the Profile tab
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Access denied. Only therapists can update settings.")
        
        updated_settings = update_therapist_profile_settings(current_user["id"], settings_data.settings)
        if not updated_settings:
            raise HTTPException(status_code=404, detail="Therapist settings not found")
        
        return TherapistSettings(**updated_settings)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update profile settings")

@app.put("/api/settings/account")
async def update_user_account_settings(
    settings_data: SettingsUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update current user's account section settings
    - Only updates the account_section JSONB field
    - Used when saving from the Account tab
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Access denied. Only therapists can update settings.")
        
        updated_settings = update_therapist_account_settings(current_user["id"], settings_data.settings)
        if not updated_settings:
            raise HTTPException(status_code=404, detail="Therapist settings not found")
        
        return TherapistSettings(**updated_settings)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update account settings")

# ==================== FILE OPERATIONS ====================
# Document upload, OCR processing, and file management

@app.post("/api/upload-document")
async def upload_document(file: UploadFile = File(...), process_ocr: bool = True):
    """
    Upload PDF/DOC/DOCX files with optional OCR processing
    - Stores files locally under backend/files directory
    - Supports automatic text extraction from uploaded documents
    - Returns public URL path for frontend storage
    """
    try:
        allowed_ext = {".pdf", ".doc", ".docx"}
        _, ext = os.path.splitext(file.filename or "")
        ext = ext.lower()
        if ext not in allowed_ext:
            raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX files are allowed")

        unique_name = f"{uuid4().hex}{ext}"
        dest_path = os.path.join(FILES_DIR, unique_name)

        # Save the file
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return a path that the frontend can store; served via /files mount
        public_url = f"/files/{unique_name}"
        
        response_data = {
            "filePath": public_url,
            "fileName": file.filename,
            "fileSize": file.size if hasattr(file, 'size') else None
        }
        
        # Process OCR if requested
        if process_ocr:
            try:
                logger.info(f"Starting OCR processing for file: {unique_name}")
                ocr_result = await extract_text_from_file(dest_path)
                response_data["ocrResult"] = ocr_result
                logger.info("OCR processing completed successfully")
            except Exception as ocr_error:
                logger.error(f"OCR processing failed: {ocr_error}")
                # Don't fail the entire upload if OCR fails
                response_data["ocrResult"] = {
                    "error": "OCR processing failed",
                    "message": str(ocr_error),
                    "extracted_text": None
                }
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

@app.delete("/api/delete-file")
async def delete_file(request: DeleteFileRequest):
    """
    Delete uploaded files from local storage
    - Removes files from backend/files directory
    - Used for cleanup when documents are no longer needed
    """
    try:
        file_path = request.filePath
        if not file_path or not file_path.startswith('/files/'):
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Extract filename from the file path
        filename = file_path.replace('/files/', '')
        full_path = os.path.join(FILES_DIR, filename)
        
        # Check if file exists and delete it
        if os.path.exists(full_path):
            os.remove(full_path)
            logger.info(f"File deleted successfully: {filename}")
            return {"message": "File deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="File not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File deletion failed: {e}")
        raise HTTPException(status_code=500, detail="File deletion failed")

@app.post("/api/process-ocr")
async def process_ocr(file_path: str):
    """
    Process OCR on previously uploaded files
    - Extracts text content from existing files using AI services
    - Used for delayed or re-processing of document content
    """
    try:
        # Extract filename from the file path
        if not file_path.startswith('/files/'):
            raise HTTPException(status_code=400, detail="Invalid file path format")
        
        filename = file_path.replace('/files/', '')
        full_path = os.path.join(FILES_DIR, filename)
        
        # Check if file exists
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Process OCR
        logger.info(f"Processing OCR for existing file: {filename}")
        ocr_result = await extract_text_from_file(full_path)
        logger.info("OCR processing completed successfully")
        
        return {
            "filePath": file_path,
            "ocrResult": ocr_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

@app.post("/api/upload-to-supabase")
async def upload_to_supabase(request: UploadToSupabaseRequest, current_user: dict = Depends(get_current_user)):
    """
    Upload a local file to Supabase bucket 'Files', store its public URL in files table with student_id, and delete the local file.
    """
    try:
        from supabase import create_client
        import mimetypes
        supabase = get_supabase_client()
        BUCKET_NAME = "Files"
        file_path = request.file_path
        original_name = request.original_name
        
        logger.info(f"Starting upload to Supabase for file: {original_name}")
        
        # Validate file path
        if not file_path.startswith('/files/'):
            raise HTTPException(status_code=400, detail="Invalid file path format")
        filename = file_path.replace('/files/', '')
        full_path = os.path.join(FILES_DIR, filename)
        
        logger.info(f"Looking for file at: {full_path}")
        
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Upload to Supabase bucket
        logger.info(f"Uploading to Supabase bucket: {BUCKET_NAME}")
        with open(full_path, "rb") as f:
            file_bytes = f.read()
        
        content_type, _ = mimetypes.guess_type(original_name)
        logger.info(f"Content type: {content_type}")
        
        upload_resp = supabase.storage.from_(BUCKET_NAME).upload(filename, file_bytes, {"content-type": content_type or "application/octet-stream"})
        
        # Check for upload errors
        if hasattr(upload_resp, 'status_code') and upload_resp.status_code != 200:
            logger.error(f"Supabase upload failed with status: {upload_resp.status_code}")
            try:
                error_data = upload_resp.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown upload error')
            except:
                error_msg = f"Upload failed with status {upload_resp.status_code}"
            raise HTTPException(status_code=500, detail=f"Supabase upload error: {error_msg}")
        
        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        logger.info(f"Public URL: {public_url}")
        
        # Insert into files table with student_id
        file_record = {
            "student_id": request.student_id,
            "file_url": public_url,
            "uploaded_at": utc_now_iso()
        }
        
        logger.info(f"Inserting into files table: {file_record}")
        insert_resp = supabase.table('files').insert(file_record).execute()
        
        # Check for database insert errors
        if hasattr(insert_resp, 'status_code') and insert_resp.status_code != 200:
            logger.error(f"Database insert failed with status: {insert_resp.status_code}")
            try:
                error_data = insert_resp.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown database error')
            except:
                error_msg = f"Database insert failed with status {insert_resp.status_code}"
            raise HTTPException(status_code=500, detail=f"Supabase DB error: {error_msg}")
        
        file_id = insert_resp.data[0]['id']
        logger.info(f"File inserted with ID: {file_id}")
        
        # Delete local file
        os.remove(full_path)
        logger.info("Local file deleted successfully")
        
        return {"message": "File uploaded to Supabase and local file deleted", "file_url": public_url, "file_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload to Supabase failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload to Supabase failed: {str(e)}")



# ==================== STUDENT MANAGEMENT ====================
# Student enrollment, retrieval, and assignment management

@app.get("/api/students", response_model=List[StudentResponse])
async def get_all_students_route(current_user: dict = Depends(get_current_user)):
    """
    Get all students in the system
    - Accessible by all authenticated users
    - Used for system-wide student overview and reporting
    """
    try:
        students = get_all_students()
        return [StudentResponse(**student) for student in students]
        
    except Exception as e:
        logger.error(f"Error fetching all students: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch students")

@app.get("/api/students/{student_id}", response_model=StudentResponse)
async def get_student_route(
    student_id: int, 
    current_user: dict = Depends(get_current_user)
):
    """
    Get specific student by ID
    - Restricted to therapists only for privacy
    - Used for detailed student information and case management
    """
    try:
        # Check if user is therapist
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403, 
                detail="Access denied. Only therapists can view student details."
            )
        
        student = get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        
        return StudentResponse(**student)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch student")

@app.get("/api/my-students", response_model=List[StudentResponse])
async def get_my_students_route(current_user: dict = Depends(get_current_user)):
    """
    Get students assigned to current therapist
    - Therapist-specific student caseload management
    - Used for dashboard and assignment-specific workflows
    """
    try:
        # Check if user is therapist
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403, 
                detail="Access denied. Only therapists can view assigned students."
            )
        
        students = get_students_by_therapist(current_user["id"])
        return [StudentResponse(**student) for student in students]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching students for therapist {current_user['id']}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch assigned students")

@app.get("/api/temp-students", response_model=List[StudentResponse])
async def get_temp_students_route(current_user: dict = Depends(get_current_user)):
    """
    Get temporary students with prior diagnosis
    - Special category for students with existing diagnosis
    - Used for streamlined enrollment and assessment workflows
    """
    try:
        # Check if user is therapist
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403, 
                detail="Access denied. Only therapists can view assigned students."
            )
        
        students = get_temp_students_by_therapist(current_user["id"])
        return [StudentResponse(**student) for student in students]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching temporary students for therapist {current_user['id']}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch temporary students")

@app.post("/api/enroll-student", response_model=StudentResponse)
async def enroll_student_route(
    student_data: StudentEnrollment,
    current_user: dict = Depends(get_current_user)
):
    """
    Enroll new student in the system
    - Creates student record with therapist assignment
    - Handles profile information and diagnostic data
    - If file is uploaded, uploads it to Supabase and links to student
    """
    try:
        # Convert Pydantic model to dict
        student_dict = student_data.dict()
        
        # Remove file information from student data (not needed for enrollment)
        file_path = student_dict.pop('uploadedFilePath', None)
        file_name = student_dict.pop('uploadedFileName', None)

        # Normalize assessment payload and determine enrollment status
        assessment_details = student_dict.get('assessmentDetails') or {}
        clean_assessment_details = {}
        has_clinical_snapshot_scores = False
        has_non_snapshot_scores = False

        if isinstance(assessment_details, dict):
            for tool_id, detail in assessment_details.items():
                if not isinstance(detail, dict):
                    continue
                items = detail.get('items') if isinstance(detail.get('items'), dict) else None
                if not items:
                    continue

                valid_scores = [score for score in items.values() if isinstance(score, (int, float))]
                if not valid_scores:
                    continue

                clean_assessment_details[tool_id] = {
                    'items': items,
                    'average': detail.get('average')
                }

                if tool_id == 'clinical-snapshots':
                    has_clinical_snapshot_scores = True
                else:
                    has_non_snapshot_scores = True

        prior_diagnosis = bool(student_dict.get('priorDiagnosis'))
        if prior_diagnosis:
            student_dict['status'] = 'active' if (has_clinical_snapshot_scores or has_non_snapshot_scores) else 'assessment_due'
        else:
            student_dict['status'] = 'active' if has_non_snapshot_scores else 'assessment_due'

        student_dict['assessmentDetails'] = clean_assessment_details or None
        
        # Enroll the student
        student = enroll_student(student_dict)
        
        # If file was uploaded, upload it to Supabase
        if file_path and file_name and student.get('id'):
            try:
                logger.info(f"Uploading file to Supabase for student {student['id']}")
                
                # Call the upload-to-supabase endpoint internally
                upload_request = UploadToSupabaseRequest(
                    file_path=file_path,
                    original_name=file_name,
                    student_id=student['id']
                )
                
                # We need to call the upload function directly
                from supabase import create_client
                import mimetypes
                supabase = get_supabase_client()
                BUCKET_NAME = "Files"
                
                filename = file_path.replace('/files/', '')
                full_path = os.path.join(FILES_DIR, filename)
                
                if os.path.exists(full_path):
                    # Upload to Supabase bucket
                    with open(full_path, "rb") as f:
                        file_bytes = f.read()
                    
                    content_type, _ = mimetypes.guess_type(file_name)
                    
                    upload_resp = supabase.storage.from_(BUCKET_NAME).upload(filename, file_bytes, {"content-type": content_type or "application/octet-stream"})
                    
                    if hasattr(upload_resp, 'status_code') and upload_resp.status_code != 200:
                        logger.error(f"Supabase upload failed: {upload_resp.status_code}")
                    else:
                        # Get public URL
                        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
                        
                        # Insert into files table with student_id
                        file_record = {
                            "student_id": student['id'],
                            "file_url": public_url,
                            "uploaded_at": utc_now_iso()
                        }
                        
                        insert_resp = supabase.table('files').insert(file_record).execute()
                        
                        if hasattr(insert_resp, 'status_code') and insert_resp.status_code != 200:
                            logger.error(f"Database insert failed: {insert_resp.status_code}")
                        else:
                            # Delete local file
                            os.remove(full_path)
                            logger.info(f"File uploaded to Supabase and linked to student {student['id']}")
                else:
                    logger.warning(f"File not found for upload: {full_path}")
                    
            except Exception as file_error:
                logger.error(f"Failed to upload file for student {student['id']}: {file_error}")
                # Don't fail enrollment if file upload fails
        
        return StudentResponse(**student)
        
    except Exception as e:
        logger.error(f"Error enrolling student: {e}")
        raise HTTPException(status_code=500, detail="Failed to enroll student")

@app.post("/api/students/{student_id}/assessment", response_model=StudentResponse)
async def update_student_assessment_route(
    student_id: int,
    assessment_update: StudentAssessmentUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Persist assessment results and promote learners when requirements are met."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can update assessments."
            )

        updated_student = update_student_assessment_record(
            student_id,
            current_user["id"],
            assessment_update.assessmentDetails
        )

        if not updated_student:
            raise HTTPException(status_code=404, detail="Student not found")

        return StudentResponse(**updated_student)

    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating assessment for student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update assessment details")

@app.put("/api/students/{student_id}/assessment-details")
async def update_assessment_details_route(
    student_id: int,
    assessment_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update assessment_details for a child and promote from temporary enrollment.
    Used when completing assessment sessions in ActiveSessions.
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Only therapists can update assessments")

        supabase = get_supabase_client()
        
        # Get current assessment_details
        child_result = supabase.table('children').select('assessment_details, status').eq('id', student_id).single().execute()
        if not child_result.data:
            raise HTTPException(status_code=404, detail="Student not found")
        
        current_details = child_result.data.get('assessment_details') or {}
        new_details = assessment_data.get('assessment_details', {})
        
        # Merge new assessment data with existing
        merged_details = {**current_details, **new_details}
        
        # Update children table
        update_data = {
            'assessment_details': merged_details,
        }
        
        # If child is temporary, promote to active
        if child_result.data.get('status') == 'assessment_due':
            update_data['status'] = 'active'
        
        result = supabase.table('children').update(update_data).eq('id', student_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update assessment details")
        
        return {
            "success": True,
            "message": "Assessment details updated successfully",
            "status": update_data.get('status', child_result.data.get('status'))
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating assessment details for student {student_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SESSION NOTES MANAGEMENT ====================
# Therapy session note creation, retrieval, and date tracking

@app.get("/api/notes/{session_date}", response_model=List[SessionNoteResponse])
async def get_notes_by_date(session_date: date, current_user: dict = Depends(get_current_user)):
    """
    Get all session notes for current therapist on specific date
    - Date-based note retrieval for calendar integration
    - Used for daily note review and session documentation
    """
    try:
        therapist_id = current_user['id']
        notes = await get_notes_by_date_and_therapist(therapist_id, session_date)
        return notes
    except Exception as e:
        logger.error(f"Error fetching notes for date {session_date}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch notes")

@app.post("/api/notes", response_model=SessionNoteResponse)
async def create_note(note_data: SessionNoteCreate, current_user: dict = Depends(get_current_user)):
    """
    Create new session note
    - Documentation of therapy sessions and progress
    - Linked to specific dates and students
    """
    try:
        therapist_id = current_user['id']
        note = await create_session_note(therapist_id, note_data)
        return note
    except Exception as e:
        logger.error(f"Error creating note: {e}")
        raise HTTPException(status_code=500, detail="Failed to create note")

@app.get("/api/notes/dates/all", response_model=List[str])
async def get_notes_dates(current_user: dict = Depends(get_current_user)):
    """
    Get all dates with notes for current therapist
    - Used for calendar highlighting and note availability indicators
    - Enables quick navigation to days with existing documentation
    """
    try:
        therapist_id = current_user['id']
        dates = await get_notes_with_dates_for_therapist(therapist_id)
        # Convert dates to strings for JSON serialization
        return [d.isoformat() for d in dates]
    except Exception as e:
        logger.error(f"Error fetching notes dates: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch notes dates")

# ==================== SESSION MANAGEMENT ====================
# Therapy session scheduling, CRUD operations, and session tracking

@app.post("/api/sessions", response_model=SessionResponse)
async def create_session_endpoint(session_data: SessionCreate, current_user: dict = Depends(get_current_user)):
    """
    Create new therapy session
    - Schedule sessions with students and therapists
    - Includes time slots, duration, and session type specification
    """
    try:
        therapist_id = current_user['id']
        session = await create_session(therapist_id, session_data)
        return session
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")

@app.get("/api/sessions", response_model=List[SessionResponse])
async def get_sessions(limit: int = 50, offset: int = 0, current_user: dict = Depends(get_current_user)):
    """
    Get all sessions for current therapist with pagination
    - Historical and upcoming session management
    - Supports pagination for large session datasets
    """
    try:
        therapist_id = current_user['id']
        sessions = await get_sessions_by_therapist(therapist_id, limit, offset)
        return sessions
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sessions")

@app.get("/api/sessions/today", response_model=List[SessionResponse])
async def get_todays_sessions(current_user: dict = Depends(get_current_user)):
    """
    Get today's sessions for current therapist
    - Daily schedule and agenda management
    - Used for dashboard "Today's Sessions" displays
    """
    try:
        therapist_id = current_user['id']
        sessions = await get_todays_sessions_by_therapist(therapist_id)
        return sessions
    except Exception as e:
        logger.error(f"Error fetching today's sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch today's sessions")

@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get specific session by ID
    - Detailed session information for editing and review
    - Restricted to sessions owned by current therapist
    """
    try:
        therapist_id = current_user['id']
        session = await get_session_by_id(session_id, therapist_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch session")

@app.put("/api/sessions/{session_id}", response_model=SessionResponse)
async def update_session_endpoint(session_id: int, session_data: SessionUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update existing session
    - Modify session details, timing, and configuration
    - Restricted to sessions owned by current therapist
    """
    try:
        therapist_id = current_user['id']
        session = await update_session(session_id, therapist_id, session_data)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session")

@app.put("/api/sessions/{session_id}/notification-sent")
async def update_notification_sent_endpoint(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Update the sent_notification flag for a session to true.
    """
    try:
        therapist_id = current_user['id']
        supabase = get_supabase_client()
        
        # Verify therapist has access to the session
        session_check = supabase.table('sessions').select('id').eq('id', session_id).eq('therapist_id', therapist_id).execute()
        if not session_check.data:
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        # Update the sent_notification flag
        update_data = {'sent_notification': True, 'updated_at': utc_now_iso()}
        result = supabase.table('sessions').update(update_data).eq('id', session_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update notification status")

        return {"message": "Notification status updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification status for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update notification status")

@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete session
    - Remove sessions and associated data
    - Restricted to sessions owned by current therapist
    """
    try:
        therapist_id = current_user['id']
        success = await delete_session(session_id, therapist_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")

# ==================== SESSION ACTIVITIES MANAGEMENT ====================
# Activity assignment, goal tracking, and therapy exercise management

@app.post("/api/sessions/{session_id}/activities", response_model=SessionActivityResponse)
async def add_activity_to_session_endpoint(session_id: int, activity_data: SessionActivityCreate, current_user: dict = Depends(get_current_user)):
    """
    Add activity to specific session
    - Assign therapeutic activities and exercises to sessions
    - Links activities from master library to individual sessions
    """
    try:
        therapist_id = current_user['id']
        activity = await add_activity_to_session(session_id, therapist_id, activity_data)
        return activity
    except Exception as e:
        logger.error(f"Error adding activity to session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to add activity to session")

@app.get("/api/sessions/{session_id}/activities", response_model=List[SessionActivityResponse])
async def get_session_activities_endpoint(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get all activities for specific session
    - Retrieve session-specific activity assignments
    - Used for session planning and execution
    """
    try:
        therapist_id = current_user['id']
        activities = await get_session_activities(session_id, therapist_id)
        return activities
    except Exception as e:
        logger.error(f"Error fetching activities for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch session activities")

@app.get("/api/students/{student_id}/activities", response_model=List[ChildGoalResponse])
async def get_student_activities_endpoint(student_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get available goals/activities for specific student
    - Student-specific therapeutic goals and objectives
    - Used for personalized session planning
    """
    try:
        activities = await get_available_child_goals(student_id)
        return activities
    except Exception as e:
        logger.error(f"Error fetching goals for student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch student goals")

@app.get("/api/activities", response_model=List[ActivityResponse])
async def get_master_activities_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get master activities library
    - Complete catalog of available therapeutic activities
    - Used for activity selection and session planning
    """
    try:
        activities = await get_master_activities()
        return activities
    except Exception as e:
        logger.error(f"Error fetching master activities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch master activities")

@app.get("/api/assessment-tools")
async def get_assessment_tools_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get assessment tool activities grouped by tool
    - ISAA, INDT-ADHD, and Clinical Snapshots with their sub-activities
    - Used for assessment session planning and execution
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can access assessment tools."
            )
        
        assessment_tools = await get_assessment_tool_activities()
        
        return assessment_tools
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching assessment tools: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch assessment tools")

@app.post("/api/activities/suggest", response_model=List[ActivitySuggestionResponse])
async def suggest_activities_endpoint(
    request: ActivitySuggestionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate AI-powered activity suggestions for a learner
    - Uses Gemini AI to create personalized therapeutic activities
    - Based on learner's medical diagnosis and assessment details
    - Returns structured activity recommendations with therapeutic goals
    """
    try:
        # Check if user is therapist
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can generate activity suggestions."
            )

        activities = await suggest_therapeutic_activities(
            request.learner_profile,
            request.user_query
        )
        return activities
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating activity suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate activity suggestions")


@app.post("/api/activities/chat/session", response_model=ActivityChatSessionResponse)
async def create_activity_chat_session_endpoint(
    request: ActivityChatSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Initialize a new AI activity chat session with cached learner context."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can initiate activity chat sessions."
            )

        session_payload = await create_activity_chat_session(request.learner_profile)
        return ActivityChatSessionResponse(**session_payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating activity chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create AI session")


@app.post("/api/activities/chat/session/{session_id}/message", response_model=ActivityChatMessageResponse)
async def send_activity_chat_message_endpoint(
    session_id: str,
    request: ActivityChatMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Forward therapist prompts to AI session and return assistant messages."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can chat with the AI activity assistant."
            )

        assistant_messages = await generate_activity_chat_messages(
            session_id,
            request.message,
            ai_preferences=request.ai_preferences,
            session_notes=request.session_notes,
            focus_context=request.focus_context,
            notes_instruction=request.notes_instruction
        )
        return ActivityChatMessageResponse(session_id=session_id, messages=assistant_messages)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing AI chat message: {e}")
        raise HTTPException(status_code=500, detail="Failed to process AI chat message")

@app.post("/api/activities/assign", response_model=ActivityAssignmentResponse)
async def assign_activity_endpoint(
    request: ActivityAssignmentRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Assign an AI-suggested activity to a child
    - Creates activity in master library if it doesn't exist
    - Creates child_goal record linking child to activity
    - Enables activity tracking and session planning
    """
    try:
        # Check if user is therapist
        if current_user["role"] != "therapist":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only therapists can assign activities."
            )

        result = await assign_ai_activity_to_child(
            request.activity,
            request.child_id,
            current_user["id"]
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning activity: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign activity")


@app.post("/api/learners/{child_id}/ai-preferences", response_model=AIPreferencesResponse)
async def save_ai_preferences(
    child_id: int,
    request: AIPreferencesRequest,
    current_user: dict = Depends(get_current_user)
):
    """Save or update AI customization preferences for a specific learner."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Access denied")
        
        supabase = get_supabase_client()
        now = utc_now_iso()
        
        # Update the ai_preference JSON column in children table
        update_payload = {
            "ai_preference": {
                "ai_instructions": request.ai_instructions,
                "updated_at": now
            },
        }

        result = supabase.table("children").update(update_payload).eq("id", child_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Child not found")
        
        return AIPreferencesResponse(
            child_id=child_id,
            ai_instructions=request.ai_instructions,
            updated_at=now
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving AI preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to save AI preferences")


@app.get("/api/learners/{child_id}/ai-preferences", response_model=AIPreferencesResponse)
async def get_ai_preferences(
    child_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve AI customization preferences for a specific learner."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Access denied")
        
        supabase = get_supabase_client()
        result = supabase.table("children").select("ai_preference").eq("id", child_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Child not found")
        
        child_data = result.data[0]
        ai_pref = child_data.get("ai_preference") or {}
        ai_instructions = ai_pref.get("ai_instructions", "") if isinstance(ai_pref, dict) else ""
        
        return AIPreferencesResponse(
            child_id=child_id,
            ai_instructions=ai_instructions,
            updated_at=child_data.get("updated_at", "")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching AI preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch AI preferences")


@app.post("/api/sessions/notes", response_model=List[SessionNoteItem])
async def get_session_notes_by_child(
    payload: SessionNotesQueryParams,
    current_user: dict = Depends(get_current_user)
):
    """Fetch session notes (therapist_notes field from sessions table) for a child within a date range."""
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Access denied")
        child_id = payload.child_id
        if child_id is None:
            raise HTTPException(status_code=400, detail="child_id is required")
        if child_id <= 0:
            raise HTTPException(status_code=400, detail="child_id must be positive")
         
        start_date = payload.start_date
        end_date = payload.end_date

        supabase = get_supabase_client()
        query = supabase.table("sessions").select("id, session_date, start_time, end_time, therapist_notes, status").eq("child_id", child_id)

        def normalize(date_str: Optional[str], field_name: str) -> Optional[str]:
            if date_str is None:
                return None
            try:
                value = date_str.strip()
                if not value:
                    return None
                parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
                return parsed_date.isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {field_name} format. Use YYYY-MM-DD.")

        normalized_start = normalize(start_date, "start_date")
        normalized_end = normalize(end_date, "end_date")

        if normalized_start:
            query = query.gte("session_date", normalized_start)
        if normalized_end:
            query = query.lte("session_date", normalized_end)
        
        result = query.order("session_date", desc=True).execute()
        
        # Filter only sessions with notes
        notes_data = [
            SessionNoteItem(
                session_id=row["id"],
                session_date=row["session_date"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                therapist_notes=row.get("therapist_notes"),
                status=row["status"]
            )
            for row in result.data
            if row.get("therapist_notes")  # Only include sessions with notes
        ]
        print(notes_data)
        return notes_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session notes: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch session notes")

@app.delete("/api/sessions/{session_id}/activities/{activity_id}")
async def remove_activity_from_session_endpoint(session_id: int, activity_id: int, current_user: dict = Depends(get_current_user)):
    """
    Remove activity from session
    - Unassign activities from specific sessions
    - Used for session plan modifications
    """
    try:
        therapist_id = current_user['id']
        success = await remove_activity_from_session(activity_id, session_id, therapist_id)
        if not success:
            raise HTTPException(status_code=404, detail="Activity not found in session")
        return {"message": "Activity removed from session successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing activity {activity_id} from session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove activity from session")


@app.put("/api/sessions/{session_id}/activities/{activity_id}", response_model=SessionActivityResponse)
async def update_session_activity_endpoint(
    session_id: int,
    activity_id: int,
    activity_update: SessionActivityUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update session activity with actual duration and performance notes
    - Records actual time spent on activity during session
    - Captures performance observations and notes
    - Used during active session to track completion
    """
    try:
        therapist_id = current_user['id']
        updated_activity = await update_session_activity(activity_id, session_id, therapist_id, activity_update)
        return updated_activity
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating activity {activity_id} in session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session activity")


@app.post("/api/students/{child_id}/activities/{activity_id}/complete")
async def mark_activity_completed_endpoint(child_id: int, activity_id: int, current_user: dict = Depends(get_current_user)):
    """
    Mark a child goal activity as completed
    - Updates current_status to 'completed' in child_goals table
    - Sets date_mastered to current date
    - Used during active sessions to track activity completion
    """
    try:
        from sessions.sessions import mark_activity_completed
        
        result = await mark_activity_completed(child_id, activity_id)
        
        if not result['success']:
            raise HTTPException(status_code=400, detail=result['message'])
        
        return {
            "message": result['message'],
            "child_goal_id": result['child_goal_id'],
            "previous_status": result['previous_status'],
            "new_status": result['new_status']
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking activity {activity_id} as completed for child {child_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark activity as completed")


# ==================== SESSION STATUS MANAGEMENT ====================
# Routes for session status updates and notifications

@app.put("/api/sessions/{session_id}/status", response_model=SessionStatusResponse)
async def update_session_status_endpoint(session_id: int, status_update: SessionStatusUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update session status (scheduled/ongoing/completed/cancelled)
    - Manual status updates by therapists
    - Validates status transitions
    - Logs all status changes
    """
    try:
        therapist_id = current_user['id']
        result = await update_session_status(session_id, status_update.new_status, therapist_id)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found or invalid status transition")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating session {session_id} status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session status")

@app.post("/api/sessions/{session_id}/start", response_model=SessionStatusResponse)
async def start_session_endpoint(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Start a scheduled session (change status to ongoing)
    - Used when therapist begins a session
    - Updates status from 'scheduled' to 'ongoing'
    """
    try:
        therapist_id = current_user['id']
        validation = await check_session_ready_for_start(session_id, therapist_id)

        if validation.get('exists') is False:
            raise HTTPException(status_code=404, detail="Session not found")

        if validation.get('requires_reschedule'):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SESSION_NEEDS_RESCHEDULE",
                    "message": validation.get('reason') or "Session requires rescheduling before it can be started.",
                    "session": validation.get('session'),
                    "upcoming": validation.get('upcoming'),
                }
            )

        result = await start_session(session_id, therapist_id)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found or cannot be started")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start session")


@app.post(
    "/api/sessions/{session_id}/reschedule/cascade",
    response_model=CascadeRescheduleResponse,
)
async def cascade_reschedule_endpoint(
    session_id: int,
    payload: CascadeRescheduleRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Shift the selected session and all upcoming scheduled sessions by one day.
    - Applies therapist working hours and personal time validation
    - Optional weekend inclusion controlled by request payload
    """

    try:
        therapist_id = current_user["id"]
        result = await cascade_reschedule_sessions(
            session_id=session_id,
            therapist_id=therapist_id,
            include_weekends=payload.include_weekends,
        )
        session_items = [RescheduledSessionItem(**item) for item in result.get("sessions", [])]
        return CascadeRescheduleResponse(
            total_updated=result.get("total_updated", 0),
            sessions=session_items,
            include_weekends=result.get("include_weekends", False),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Error cascading reschedule for session %s by therapist %s: %s",
            session_id,
            current_user.get("id"),
            e,
        )
        raise HTTPException(status_code=500, detail="Failed to cascade reschedule sessions")


@app.post("/api/sessions/{session_id}/complete", response_model=SessionStatusResponse)
async def complete_session_endpoint(session_data: SessionComplete, session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Complete an ongoing session (change status to completed)
    - Used when session ends
    - Updates status from 'ongoing' to 'completed'
    - Accepts therapist notes to be saved with the session
    """
    try:
        therapist_id = current_user['id']
        result = await complete_session(session_id, therapist_id, session_data.therapist_notes)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found or cannot be completed")
        return result
    except Exception as e:
        logger.error(f"Error completing session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete session")

@app.post("/api/sessions/{session_id}/cancel", response_model=SessionStatusResponse)
async def cancel_session_endpoint(session_id: int, current_user: dict = Depends(get_current_user)):
    """
    Cancel a session (change status to cancelled)
    - Used when session needs to be cancelled
    - Updates status to 'cancelled'
    """
    try:
        therapist_id = current_user['id']
        result = await cancel_session(session_id, therapist_id)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found or cannot be cancelled")
        return result
    except Exception as e:
        logger.error(f"Error cancelling session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel session")

@app.get("/api/sessions/status/overview")
async def get_todays_sessions_status_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get status overview of all today's sessions
    - Dashboard view of daily session progress
    - Shows current status of all sessions
    """
    try:
        sessions_status = await get_todays_sessions_status()
        return {"sessions": sessions_status, "total_count": len(sessions_status)}
    except Exception as e:
        logger.error(f"Error getting today's sessions status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sessions status")

@app.get("/api/sessions/status/pending-updates")
async def get_sessions_needing_updates_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get sessions that need automatic status updates
    - Shows sessions that should be started or completed
    - Used for monitoring and manual intervention
    """
    try:
        sessions_needing_update = await get_sessions_needing_status_update()
        return {"sessions": sessions_needing_update, "count": len(sessions_needing_update)}
    except Exception as e:
        logger.error(f"Error getting sessions needing updates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sessions needing updates")

@app.post("/api/sessions/status/auto-update")
async def auto_update_sessions_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Trigger automatic session status updates
    - Manually trigger auto-update process
    - Updates sessions based on current time
    """
    try:
        updated_sessions = await auto_update_session_statuses()
        return {"updated_sessions": updated_sessions, "count": len(updated_sessions)}
    except Exception as e:
        logger.error(f"Error in auto-update sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to auto-update sessions")

# ==================== LOGIN-BASED SESSION MANAGEMENT ====================
# Routes for handling session status and notifications on user login

@app.post("/api/sessions/check-on-login")
async def check_sessions_on_login_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Check session status immediately after therapist login
    
    This endpoint:
    1. Checks if any sessions should be ongoing and updates status
    2. Provides immediate notification if user is late for a session
    3. Calculates time remaining for next session
    4. Schedules notifications for upcoming sessions
    
    Returns:
        Dictionary with session status updates and immediate notifications
    """
    try:
        # Get therapist_id from current user - using 'id' field from user object
        therapist_id = current_user.get('id')
        if not therapist_id:
            logger.error(f"No user ID found in current_user: {current_user}")
            raise HTTPException(status_code=400, detail="Invalid user information")
        
        # Verify user is a therapist
        user_role = current_user.get('role')
        if user_role != 'therapist':
            logger.warning(f"Non-therapist user {therapist_id} attempted to check sessions")
            raise HTTPException(status_code=403, detail="Access denied: Only therapists can check sessions")
        
        logger.info(f"Checking sessions on login for therapist {therapist_id}")
        
        # Check sessions and get immediate notifications
        session_check_result = await check_sessions_on_login(therapist_id)
        
        # Schedule notifications for remaining sessions
        scheduling_result = await schedule_session_notifications_for_day(therapist_id)
        
        return {
            "session_check": session_check_result,
            "notification_scheduling": scheduling_result,
            "login_time": utc_now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking sessions on login: {e}")
        raise HTTPException(status_code=500, detail="Failed to check sessions on login")

# ==================== SESSION NOTIFICATIONS ====================
# Routes for session notification management


# ==================== MONITORING SERVICE CONTROL ====================
# Routes for controlling the background monitoring service

@app.get("/api/monitoring/status")
async def get_monitoring_status_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get status of the session monitoring service
    - Shows service health and last check times
    - Used for monitoring dashboard
    """
    try:
        status = get_monitoring_service_status()
        return status
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get monitoring status")

@app.post("/api/monitoring/trigger/status-update")
async def trigger_status_update_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger session status updates
    - Force immediate status update check
    - Used for testing and manual intervention
    """
    try:
        updated_sessions = await trigger_manual_status_update()
        return {"updated_sessions": updated_sessions, "count": len(updated_sessions)}
    except Exception as e:
        logger.error(f"Error triggering manual status update: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger status update")

@app.post("/api/monitoring/trigger/notifications")
async def trigger_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger notification check
    - Force immediate notification generation
    - Used for testing and manual intervention
    """
    try:
        notifications = await trigger_manual_notification_check()
        return {"notifications": notifications, "count": len(notifications)}
    except Exception as e:
        logger.error(f"Error triggering manual notification check: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger notification check")

# ==================== CONTINUOUS NOTIFICATION MONITORING ====================
# Routes for real-time session notification monitoring per specification

@app.get("/api/sessions/notifications/continuous")
async def get_continuous_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get notifications that should be sent now based on scheduled times
    
    This implements the continuous monitoring specification:
    - Returns notifications where current_time >= notification_time
    - Automatically schedules next session notifications after sending
    
    Returns:
        List of notification payloads ready to be sent
    """
    try:
        notifications = await get_continuous_notifications()
        return {
            "notifications": notifications,
            "count": len(notifications),
            "timestamp": utc_now_iso()
        }
    except Exception as e:
        logger.error(f"Error getting continuous notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to get continuous notifications")

@app.post("/api/sessions/schedule-changes/{therapist_id}")
async def handle_schedule_changes_endpoint(therapist_id: int, current_user: dict = Depends(get_current_user)):
    """
    Handle dynamic schedule changes without WebSockets
    
    This implements section 3.3 of the specification:
    - Discards previously scheduled notifications
    - Re-fetches updated schedule from today-sessions route
    - Re-runs continuous monitoring logic
    
    Args:
        therapist_id: ID of therapist whose schedule changed
        
    Returns:
        Dictionary with re-scheduling results
    """
    try:
        result = await handle_dynamic_schedule_changes(therapist_id)
        return result
    except Exception as e:
        logger.error(f"Error handling schedule changes for therapist {therapist_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to handle schedule changes")

# ==================== SMART NOTIFICATION SYSTEM ====================
# Routes for smart notification scheduling system

@app.post("/api/smart-notifications/start")
async def start_smart_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Start the smart notification scheduling system
    
    Returns:
        Dictionary with operation result and system status
    """
    try:
        result = await start_smart_notification_system()
        return result
    except Exception as e:
        logger.error(f"Error starting smart notification system: {e}")
        raise HTTPException(status_code=500, detail="Failed to start smart notification system")

@app.post("/api/smart-notifications/stop")
async def stop_smart_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Stop the smart notification scheduling system
    
    Returns:
        Dictionary with operation result and system status
    """
    try:
        result = await stop_smart_notification_system()
        return result
    except Exception as e:
        logger.error(f"Error stopping smart notification system: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop smart notification system")

@app.get("/api/smart-notifications/status")
async def get_smart_notifications_status_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get the status of the smart notification scheduling system
    
    Returns:
        Dictionary with system status and statistics
    """
    try:
        result = await get_smart_notification_system_status()
        return result
    except Exception as e:
        logger.error(f"Error getting smart notification system status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system status")

@app.post("/api/smart-notifications/refresh")
async def refresh_smart_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Manually refresh the smart notification scheduling system
    
    Returns:
        Dictionary with refresh operation result
    """
    try:
        result = await refresh_smart_notification_system()
        return result
    except Exception as e:
        logger.error(f"Error refreshing smart notification system: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh smart notification system")

# ==================== APPLICATION STARTUP ====================

@app.on_event("startup")
async def startup_event():
    """
    Application startup event handler
    
    Initializes smart notification system and other services
    """
    try:
        logger.info("Starting ThrivePath API application...")
        
        # Start smart notification system
        logger.info("Initializing smart notification system...")
        result = await start_smart_notification_system()
        
        if result.get("success"):
            logger.info("Smart notification system started successfully")
        else:
            logger.warning(f"Smart notification system startup issue: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        # Don't fail the entire app startup for notification system issues
        logger.warning("Continuing application startup despite notification system error")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown event handler
    
    Cleanly stops smart notification system and other services
    """
    try:
        logger.info("Shutting down ThrivePath API application...")
        
        # Stop smart notification system
        logger.info("Stopping smart notification system...")
        result = await stop_smart_notification_system()
        
        if result.get("success"):
            logger.info("Smart notification system stopped successfully")
        else:
            logger.warning(f"Smart notification system shutdown issue: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}")

if __name__ == "__main__":
    import uvicorn
    print("Starting ThrivePath API server...")
    uvicorn.run(
        "app:app",  
        host="0.0.0.0", 
        port=8000, 
        reload=True,  
        log_level="info"
    )