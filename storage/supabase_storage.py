"""
Supabase Storage file management for learner documents
Handles upload, view, delete operations with OCR integration
"""
import os
import logging
import mimetypes
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import UploadFile, HTTPException
from db import get_supabase_client
from ai_services import extract_text_from_file
import tempfile

logger = logging.getLogger(__name__)

# Supabase Storage bucket name (using existing Files bucket)
LEARNER_FILES_BUCKET = "Files"

async def upload_file_to_supabase(
    file: UploadFile,
    learner_id: Optional[int] = None,
    process_ocr: bool = True
) -> Dict[str, Any]:
    """
    Upload file directly to Supabase Storage and process OCR
    
    Args:
        file: Uploaded file object
        learner_id: Optional learner ID for organizing files
        process_ocr: Whether to process OCR on the file
    
    Returns:
        Dictionary with file URL, OCR results, and metadata
    """
    try:
        # Validate file type
        allowed_ext = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
        _, ext = os.path.splitext(file.filename or "")
        ext = ext.lower()
        
        if ext not in allowed_ext:
            raise HTTPException(
                status_code=400,
                detail=f"File type {ext} not allowed. Allowed types: {', '.join(allowed_ext)}"
            )
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid4().hex[:8]
        
        if learner_id:
            storage_path = f"learner_{learner_id}/{timestamp}_{unique_id}_{file.filename}"
        else:
            storage_path = f"temp/{timestamp}_{unique_id}_{file.filename}"
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = "application/octet-stream"
        
        # Upload to Supabase Storage
        supabase = get_supabase_client()
        
        try:
            # Upload file
            result = supabase.storage.from_(LEARNER_FILES_BUCKET).upload(
                path=storage_path,
                file=file_content,
                file_options={"content-type": content_type}
            )
            
            logger.info(f"File uploaded to Supabase: {storage_path}")
            
        except Exception as upload_error:
            logger.error(f"Supabase upload error: {upload_error}")
            raise HTTPException(status_code=500, detail=f"Failed to upload file to storage: {str(upload_error)}")
        
        # Get public URL
        try:
            public_url_response = supabase.storage.from_(LEARNER_FILES_BUCKET).get_public_url(storage_path)
            file_url = public_url_response
        except Exception as url_error:
            logger.error(f"Error getting public URL: {url_error}")
            file_url = f"supabase://{LEARNER_FILES_BUCKET}/{storage_path}"
        
        response_data = {
            "file_url": file_url,
            "storage_path": storage_path,
            "file_name": file.filename,
            "file_size": file_size,
            "content_type": content_type,
            "uploaded_at": datetime.now().isoformat()
        }
        
        # Process OCR if requested
        if process_ocr:
            try:
                logger.info(f"Starting OCR processing for file: {file.filename}")
                
                # Create temporary file for OCR processing
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                    temp_file.write(file_content)
                    temp_path = temp_file.name
                
                try:
                    # Process OCR
                    ocr_result = await extract_text_from_file(temp_path)
                    response_data["ocr_result"] = ocr_result
                    logger.info("OCR processing completed successfully")
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        
            except Exception as ocr_error:
                logger.error(f"OCR processing failed: {ocr_error}")
                response_data["ocr_result"] = {
                    "error": "OCR processing failed",
                    "message": str(ocr_error),
                    "extracted_text": None
                }
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


async def get_file_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """
    Get a signed URL for viewing/downloading a file from Supabase Storage
    
    Args:
        storage_path: Path to file in Supabase Storage
        expires_in: URL expiration time in seconds (default 1 hour)
    
    Returns:
        Signed URL string
    """
    try:
        supabase = get_supabase_client()
        
        # Create signed URL
        signed_url_response = supabase.storage.from_(LEARNER_FILES_BUCKET).create_signed_url(
            path=storage_path,
            expires_in=expires_in
        )
        
        if isinstance(signed_url_response, dict) and 'signedURL' in signed_url_response:
            return signed_url_response['signedURL']
        elif isinstance(signed_url_response, dict) and 'signed_url' in signed_url_response:
            return signed_url_response['signed_url']
        else:
            # Fallback to public URL
            return supabase.storage.from_(LEARNER_FILES_BUCKET).get_public_url(storage_path)
            
    except Exception as e:
        logger.error(f"Error creating signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate file URL: {str(e)}")


async def delete_file_from_supabase(storage_path: str) -> bool:
    """
    Delete a file from Supabase Storage
    
    Args:
        storage_path: Path to file in Supabase Storage
    
    Returns:
        True if deleted successfully
    """
    try:
        supabase = get_supabase_client()
        
        # Delete file
        result = supabase.storage.from_(LEARNER_FILES_BUCKET).remove([storage_path])
        
        logger.info(f"File deleted from Supabase: {storage_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")
