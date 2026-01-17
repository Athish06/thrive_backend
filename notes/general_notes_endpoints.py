# ==================== GENERAL NOTES API ENDPOINTS ====================
# Add these endpoints to app.py after the session notes endpoints

@app.post("/api/general-notes")
async def create_general_note_endpoint(
    note_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a general note for a specific date
    - Therapist-only endpoint
    - Notes stored in notes table (not tied to sessions)
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Only therapists can create general notes")
        
        # Get therapist profile
        therapist_profile = get_therapist_profile(current_user["id"])
        if not therapist_profile:
            raise HTTPException(status_code=404, detail="Therapist profile not found")
        
        therapist_id = therapist_profile["therapists_id"]
        
        # Create note
        note = await create_general_note(
            therapist_id=therapist_id,
            date=note_data.get("date"),
            note_title=note_data.get("note_title"),
            note_content=note_data.get("note_content")
        )
        
        if note:
            return {"success": True, "note": note}
        
        raise HTTPException(status_code=500, detail="Failed to create note")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating general note: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/general-notes/{date}")
async def get_general_notes_by_date_endpoint(
    date: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all general notes for a specific date
    - Therapist-only endpoint
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Only therapists can view general notes")
        
        therapist_profile = get_therapist_profile(current_user["id"])
        if not therapist_profile:
            raise HTTPException(status_code=404, detail="Therapist profile not found")
        
        therapist_id = therapist_profile["therapists_id"]
        
        notes = await get_general_notes_by_date(therapist_id, date)
        return {"success": True, "notes": notes}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching general notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/general-notes/{note_id}")
async def update_general_note_endpoint(
    note_id: int,
    note_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a general note
    - Therapist-only endpoint
    - Can only update own notes
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Only therapists can update general notes")
        
        therapist_profile = get_therapist_profile(current_user["id"])
        if not therapist_profile:
            raise HTTPException(status_code=404, detail="Therapist profile not found")
        
        therapist_id = therapist_profile["therapists_id"]
        
        note = await update_general_note(
            note_id=note_id,
            therapist_id=therapist_id,
            note_title=note_data.get("note_title"),
            note_content=note_data.get("note_content")
        )
        
        if note:
            return {"success": True, "note": note}
        
        raise HTTPException(status_code=404, detail="Note not found or access denied")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating general note: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/general-notes/{note_id}")
async def delete_general_note_endpoint(
    note_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a general note
    - Therapist-only endpoint
    - Can only delete own notes
    """
    try:
        if current_user["role"] != "therapist":
            raise HTTPException(status_code=403, detail="Only therapists can delete general notes")
        
        therapist_profile = get_therapist_profile(current_user["id"])
        if not therapist_profile:
            raise HTTPException(status_code=404, detail="Therapist profile not found")
        
        therapist_id = therapist_profile["therapists_id"]
        
        success = await delete_general_note(note_id, therapist_id)
        
        if success:
            return {"success": True, "message": "Note deleted successfully"}
        
        raise HTTPException(status_code=404, detail="Note not found or access denied")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting general note: {e}")
        raise HTTPException(status_code=500, detail=str(e))
