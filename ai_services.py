import os
import json
import base64
import httpx
import re
import uuid
import asyncio
import time
from typing import Dict, Any, Optional, Tuple, List
from fastapi import HTTPException
import logging

# ==================== CONFIGURATION & SETUP ====================

logger = logging.getLogger(__name__)

# Gemini API Configuration
# Available models (try these if gemini-2.0-flash doesn't work):
# - gemini-2.0-flash
# - gemini-1.5-pro
# - gemini-pro
# - gemini-pro-vision
# - gemini-1.0-pro
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"
API_TIMEOUT = 30.0

# Session memory configuration
SESSION_TTL_SECONDS = 60 * 60  # 1 hour
MAX_SESSION_HISTORY = 10

# File type configurations
SUPPORTED_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

# OCR processing configurations
OCR_GENERATION_CONFIG = {
    "temperature": 0.1,
    "topK": 32,
    "topP": 1,
    "maxOutputTokens": 4096,
}

# ==================== HELPER FUNCTIONS ====================
# Utility functions for file processing and text extraction

def _get_api_key() -> str:
    """
    Retrieve and validate AI API key from environment
    - Checks for required AI_API environment variable
    - Raises ValueError if key not found
    """
    api_key = os.getenv("AI_API")
    if not api_key:
        raise ValueError("AI_API key not found in environment variables")
    return api_key

def _determine_mime_type(file_path: str) -> str:
    """
    Determine MIME type based on file extension
    - Maps file extensions to appropriate MIME types
    - Returns default octet-stream for unknown types
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    return SUPPORTED_MIME_TYPES.get(ext, 'application/octet-stream')

def _encode_file_to_base64(file_path: str) -> str:
    """
    Encode file content to base64 string
    - Reads file in binary mode and encodes to base64
    - Returns base64 encoded string suitable for API transmission
    """
    try:
        with open(file_path, "rb") as file:
            file_content = file.read()
            return base64.b64encode(file_content).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to encode file: {str(e)}")

def _clean_json_response(response_text: str) -> str:
    """
    Clean and extract JSON from API response text
    - Removes markdown code blocks if present
    - Finds first valid JSON object in response
    - Returns cleaned JSON string ready for parsing
    """
    clean_text = response_text.strip()
    
    # Remove markdown code blocks
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    clean_text = clean_text.strip()
    
    # Find the first valid JSON object
    json_start = clean_text.find('{')
    if json_start != -1:
        brace_count = 0
        json_end = -1
        for i, char in enumerate(clean_text[json_start:], json_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_end != -1:
            return clean_text[json_start:json_end]
    
    return clean_text

def _extract_dates_from_text(text: str) -> Optional[str]:
    """
    Extract date information from text using regex patterns
    - Supports multiple date formats (MM/DD/YYYY, Month DD, YYYY, etc.)
    - Returns first valid date found or None
    """
    date_patterns = [
        r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',
        r'\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{2,4})\b',
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',
        r'[A-Za-z]+ \d{1,2}, \d{4}'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if hasattr(match, 'groups') and match.groups() else match.group()
    
    return None

def _extract_names_from_text(text: str) -> Optional[str]:
    """
    Extract patient names from text using regex patterns
    - Looks for common name patterns (patient:, name:, etc.)
    - Returns properly formatted name or None
    """
    name_patterns = [
        r'patient\s*name\s*:?\s*([a-zA-Z\s]+)',
        r'(?:patient|name):\s*([A-Za-z\s]+)',
        r'patient\s+name:\s*([A-Za-z\s]+)',
        r'child\s*name\s*:?\s*([a-zA-Z\s]+)'
    ]
    
    text_lower = text.lower()
    for pattern in name_patterns:
        match = re.search(pattern, text_lower)
        if match and len(match.group(1).strip()) > 2:
            return match.group(1).strip().title()
    
    return None

def _extract_medical_keywords(text: str) -> List[str]:
    """
    Extract medical conditions from text using keyword matching
    - Searches for common medical conditions and terms
    - Returns list of found medical conditions
    """
    medical_keywords = [
        'autism', 'adhd', 'speech delay', 'developmental delay', 
        'cerebral palsy', 'down syndrome', 'epilepsy', 'seizure',
        'hearing loss', 'vision problems', 'learning disability'
    ]
    
    found_conditions = []
    text_lower = text.lower()
    
    for keyword in medical_keywords:
        if keyword in text_lower:
            found_conditions.append(keyword.title())
    
    return found_conditions

def _extract_medication_info(text: str) -> List[str]:
    """
    Extract medication information from text
    - Identifies lines containing medication references
    - Returns list of medication-related text lines
    """
    medication_keywords = ['medication', 'medicine', 'drug', 'tablet', 'capsule', 'syrup', 'prescription']
    medications = []
    
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if any(med_word in line_lower for med_word in medication_keywords):
            line_clean = line.strip()
            if len(line_clean) > 5:
                medications.append(line_clean)
    
    return medications

def _determine_document_type(text: str) -> str:
    """
    Determine document type based on content analysis
    - Analyzes text content for type indicators
    - Returns standardized document type string
    """
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['medical report', 'medical record', 'patient report']):
        return "medical_report"
    elif any(word in text_lower for word in ['birth certificate', 'birth record']):
        return "birth_certificate"
    elif any(word in text_lower for word in ['discharge summary', 'discharge report']):
        return "discharge_summary"
    elif any(word in text_lower for word in ['assessment', 'evaluation', 'therapy']):
        return "assessment_report"
    elif any(word in text_lower for word in ['lab', 'test', 'result']):
        return "lab_report"
    else:
        return "unknown"

def _create_fallback_response(text: str, error_msg: str) -> Dict[str, Any]:
    """
    Create fallback response structure when JSON parsing fails
    - Uses text analysis to extract basic information
    - Returns standardized response format with extracted data
    """
    # Extract basic information using helper functions
    patient_name = _extract_names_from_text(text)
    date = _extract_dates_from_text(text)
    medical_conditions = _extract_medical_keywords(text)
    medications = _extract_medication_info(text)
    document_type = _determine_document_type(text)
    
    return {
        "step1_basic_info": {
            "patient_name": patient_name,
            "first_name": None,
            "last_name": None,
            "date_of_birth": date,
            "age": None
        },
        "step2_profile_info": {
            "primary_complaint": "",
            "referred_by": "",
            "diagnosis": "",
            "family_info": {
                "father": {"name": "", "age": None, "education": "", "occupation": ""},
                "mother": {"name": "", "age": None, "education": "", "occupation": ""},
                "family_history": {"late_talkers": "", "genetic_disorders": "", "family_type": ""}
            },
            "language_profile": {"primary_language": "", "other_languages": ""},
            "educational_details": {"school_name": "", "school_type": "", "current_grade": "", "school_concerns": ""}
        },
        "step3_medical_info": {
            "prenatal_birth_history": {
                "mothers_age_at_delivery": None,
                "pregnancy_illnesses_medication": "",
                "length_of_pregnancy_weeks": None,
                "delivery_type": "",
                "difficulties_at_birth": "",
                "birth_cry": "",
                "birth_weight_kg": None
            },
            "medical_history": {
                "allergies": {"has": False, "details": ""},
                "convulsions": {"has": False, "details": ""},
                "head_injury": {"has": False, "details": ""},
                "visual_problems": {"has": False, "details": ""},
                "hearing_problems": {"has": False, "details": ""},
                "other_health_issues": ", ".join(medical_conditions),
                "current_medication": ", ".join(medications),
                "vaccination_details": "",
                "specific_diet": ""
            },
            "developmental_milestones": {
                "turning_over_months": None,
                "sitting_months": None,
                "crawling_months": None,
                "walking_months": None,
                "babbling_months": None,
                "first_word_months": None,
                "use_of_words_months": None,
                "combining_words_months": None,
                "toilet_training_status": ""
            },
            "feeding_skills": {
                "drinking_from_cup": None,
                "eating_solid_food": None,
                "using_spoon": None,
                "food_texture_sensitivity": "",
                "drooling": "",
                "feeding_difficulties": ""
            },
            "behavioral_issues": {
                "aggression": "",
                "temper_tantrums": "",
                "abnormal_fears": "",
                "sleeping_pattern": ""
            }
        },
        "document_info": {
            "type": document_type,
            "confidence": "low",
            "extracted_text_preview": text[:200]
        },
        "parsing_error": error_msg,
        "raw_response": text[:500]
    }

# ==================== GEMINI API INTERACTION ====================
# Functions for interacting with Gemini API

def _build_ocr_prompt() -> str:
    """
    Build comprehensive OCR prompt for medical document analysis
    - Returns standardized prompt for consistent API responses
    - Focuses on structured medical information extraction
    """
    return """Please perform OCR on this medical document and extract comprehensive information for a child's assessment form with three steps.

IMPORTANT: Return ONLY a valid JSON object with no additional text, explanations, or markdown formatting.

Extract and structure the data exactly as follows:
{
    "step1_basic_info": {
        "patient_name": "full patient name if found or null",
        "first_name": "first name extracted or null",
        "last_name": "last name extracted or null", 
        "date_of_birth": "DOB in YYYY-MM-DD format if found or null",
        "age": "age in years if mentioned or null"
    },
    "step2_profile_info": {
        "primary_complaint": "main complaint/reason for visit or empty string",
        "referred_by": "referring doctor/institution or empty string",
        "diagnosis": "primary diagnosis or condition mentioned or empty string",
        "family_info": {
            "father": {
                "name": "father's name if mentioned or empty string",
                "age": "father's age if mentioned or null",
                "education": "father's education if mentioned or empty string",
                "occupation": "father's occupation if mentioned or empty string"
            },
            "mother": {
                "name": "mother's name if mentioned or empty string", 
                "age": "mother's age if mentioned or null",
                "education": "mother's education if mentioned or empty string",
                "occupation": "mother's occupation if mentioned or empty string"
            },
            "family_history": {
                "late_talkers": "family history of speech delays or empty string",
                "genetic_disorders": "family genetic conditions or empty string",
                "family_type": "nuclear/joint/single parent etc or empty string"
            }
        },
        "language_profile": {
            "primary_language": "primary language at home or empty string",
            "other_languages": "other languages exposed to or empty string"
        },
        "educational_details": {
            "school_name": "school name and location or empty string",
            "school_type": "type of school or empty string",
            "current_grade": "current grade/class or empty string",
            "school_concerns": "concerns from school or empty string"
        }
    },
    "step3_medical_info": {
        "prenatal_birth_history": {
            "mothers_age_at_delivery": "number or null",
            "pregnancy_illnesses_medication": "pregnancy complications/medications or empty string",
            "length_of_pregnancy_weeks": "pregnancy duration in weeks or null",
            "delivery_type": "normal/cesarean/forceps/vacuum extraction or empty string",
            "difficulties_at_birth": "birth complications or empty string", 
            "birth_cry": "immediate/delayed/absent or empty string",
            "birth_weight_kg": "birth weight in kg or null"
        },
        "medical_history": {
            "allergies": {"has": "boolean", "details": "allergy details or empty string"},
            "convulsions": {"has": "boolean", "details": "seizure details or empty string"},
            "head_injury": {"has": "boolean", "details": "head injury details or empty string"},
            "visual_problems": {"has": "boolean", "details": "vision problem details or empty string"},
            "hearing_problems": {"has": "boolean", "details": "hearing problem details or empty string"},
            "other_health_issues": "other medical conditions or empty string",
            "current_medication": "current medications or empty string",
            "vaccination_details": "vaccination history or empty string",
            "specific_diet": "dietary restrictions or empty string"
        },
        "developmental_milestones": {
            "turning_over_months": "age when turned over or null",
            "sitting_months": "age when sat independently or null", 
            "crawling_months": "age when crawled or null",
            "walking_months": "age when walked independently or null",
            "babbling_months": "age when started babbling or null",
            "first_word_months": "age of first word or null",
            "use_of_words_months": "age when using meaningful words or null",
            "combining_words_months": "age when combining words or null",
            "toilet_training_status": "toilet training status or empty string"
        },
        "feeding_skills": {
            "drinking_from_cup": "boolean or null",
            "eating_solid_food": "boolean or null", 
            "using_spoon": "boolean or null",
            "food_texture_sensitivity": "texture sensitivity details or empty string",
            "drooling": "drooling issues or empty string",
            "feeding_difficulties": "sucking/swallowing/chewing issues or empty string"
        },
        "behavioral_issues": {
            "aggression": "aggression issues or empty string",
            "temper_tantrums": "tantrum behavior or empty string", 
            "abnormal_fears": "specific fears or empty string",
            "sleeping_pattern": "sleep issues or empty string"
        }
    },
    "document_info": {
        "type": "medical_report/birth_certificate/discharge_summary/assessment_report/other",
        "confidence": "high/medium/low",
        "extracted_text_preview": "first 200 characters of extracted text"
    }
}

Focus on extracting comprehensive information that covers basic demographics, family/educational background, and detailed medical history. If information is not available, use null for numbers/booleans and empty string for text fields. Do not include any text before or after the JSON object."""

async def _make_gemini_api_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make HTTP request to Gemini API with error handling
    - Handles timeout and network errors
    - Returns parsed API response
    """
    api_key = _get_api_key()
    url = f"{GEMINI_BASE_URL}?key={api_key}"
    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")

            # Try to get available models if the model is not found
            if response.status_code == 404 and "not found" in response.text.lower():
                logger.info("Model not found, attempting to list available models...")
                try:
                    list_url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
                    list_response = await client.get(list_url)
                    if list_response.status_code == 200:
                        models_data = list_response.json()
                        available_models = [model.get('name', '') for model in models_data.get('models', [])]
                        logger.info(f"Available models: {available_models}")
                    else:
                        logger.error(f"Failed to list models: {list_response.status_code}")
                except Exception as list_error:
                    logger.error(f"Error listing models: {list_error}")

            raise HTTPException(
                status_code=500,
                detail=f"Gemini API request failed: {response.status_code}"
            )

        return response.json()

    except httpx.TimeoutException:
        logger.error("Gemini API request timed out")
        raise HTTPException(status_code=500, detail="OCR request timed out")
    except httpx.RequestError as e:
        logger.error(f"Network error during Gemini API call: {e}")
        raise HTTPException(status_code=500, detail="Network error during OCR processing")

def _build_api_payload(base64_content: str, mime_type: str) -> Dict[str, Any]:
    """
    Build API payload for Gemini OCR request
    - Combines prompt, file data, and configuration
    - Returns complete API request payload
    """
    return {
        "contents": [
            {
                "parts": [
                    {"text": _build_ocr_prompt()},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64_content
                        }
                    }
                ]
            }
        ],
        "generationConfig": OCR_GENERATION_CONFIG
    }

# ==================== MAIN OCR SERVICE CLASS ====================
# Core service class for OCR operations

class GeminiOCRService:
    """
    Service class for performing OCR using Google Gemini API
    - Handles medical document text extraction
    - Provides structured data extraction from documents
    - Includes fallback mechanisms for error handling
    """
    
    def __init__(self):
        """Initialize the OCR service with API configuration"""
        self.api_key = _get_api_key()
        self.base_url = GEMINI_BASE_URL
    
    def encode_file_to_base64(self, file_path: str) -> Tuple[str, str]:
        """
        Encode file to base64 and determine MIME type
        
        Args:
            file_path: Path to the file to encode
        
        Returns:
            Tuple containing (base64_content, mime_type)
        
        Usage:
            - Used internally to prepare files for API transmission
            - Determines appropriate MIME type based on file extension
            - Handles file reading and encoding errors
        """
        base64_content = _encode_file_to_base64(file_path)
        mime_type = _determine_mime_type(file_path)
        return base64_content, mime_type

    async def extract_text_with_ocr(self, file_path: str) -> Dict[str, Any]:
        """
        Use Gemini API to perform OCR on uploaded file and extract structured data
        
        Args:
            file_path: Path to the document file to process
        
        Returns:
            Dictionary containing structured medical information extracted from document
        
        Raises:
            HTTPException: If API request fails or file processing errors occur
        
        Usage:
            - Main entry point for OCR processing
            - Handles medical document analysis and data extraction
            - Provides fallback parsing when JSON extraction fails
            - Returns standardized medical assessment data structure
        """
        try:
            # Prepare file data
            base64_content, mime_type = self.encode_file_to_base64(file_path)
            
            # Build and send API request
            payload = _build_api_payload(base64_content, mime_type)
            response_data = await _make_gemini_api_request(payload)
            
            # Validate API response structure
            if "candidates" not in response_data or not response_data["candidates"]:
                logger.error("No candidates in Gemini response")
                logger.error(f"Full response: {response_data}")
                raise HTTPException(status_code=500, detail="No response from Gemini API")
            
            # Extract generated text
            generated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            logger.info(f"Raw Gemini response length: {len(generated_text)} characters")
            logger.info(f"Response preview: {generated_text[:200]}...")
            
            # Parse JSON response
            try:
                clean_text = _clean_json_response(generated_text)
                ocr_result = json.loads(clean_text)
                logger.info("Successfully parsed JSON response from Gemini API")
                return ocr_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw response text: {generated_text[:500]}...")
                
                # Return fallback response with extracted information
                error_msg = f"Failed to parse as JSON: {str(e)}"
                return _create_fallback_response(generated_text, error_msg)
                
        except HTTPException:
            # Re-raise HTTP exceptions without modification
            raise
        except Exception as e:
            logger.error(f"Unexpected error during OCR: {e}")
            raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

    def _extract_info_from_text(self, text: str) -> Dict[str, Any]:
        """
        DEPRECATED: Extract basic information from text response when JSON parsing fails
        
        This method is kept for backward compatibility but has been replaced by
        the more comprehensive _create_fallback_response helper function.
        
        Args:
            text: Raw text to analyze
        
        Returns:
            Dictionary with basic extracted information
        
        Note:
            This method is deprecated and will be removed in future versions.
            Use _create_fallback_response instead for better structured data extraction.
        """
        return {
            "document_type": _determine_document_type(text),
            "patient_name": _extract_names_from_text(text),
            "date": _extract_dates_from_text(text),
            "medical_conditions": _extract_medical_keywords(text),
            "medications": _extract_medication_info(text),
            "other_important_info": text.split('\n')[:3]
        }

# ==================== PUBLIC API FUNCTIONS ====================
# Global service instance and public interface functions

# Create a global instance
gemini_ocr_service = GeminiOCRService()

async def extract_text_from_file(file_path: str) -> Dict[str, Any]:
    """
    Public function to extract text from a file using OCR
    
    Args:
        file_path: Path to the file to process
    
    Returns:
        Dictionary containing structured medical information extracted from the file
    
    Usage:
        - Primary entry point for external OCR requests
        - Provides simple interface for file processing
        - Returns comprehensive medical assessment data structure
        - Handles all error cases with appropriate HTTP exceptions
    
    Example:
        result = await extract_text_from_file("/path/to/medical_document.pdf")
        patient_name = result["step1_basic_info"]["patient_name"]
        medical_history = result["step3_medical_info"]["medical_history"]
    """
    return await gemini_ocr_service.extract_text_with_ocr(file_path)

async def suggest_therapeutic_activities(learner_profile: Dict[str, Any], user_query: str) -> List[Dict[str, Any]]:
    """
    Public function to generate therapeutic activity suggestions

    Args:
        learner_profile: Dictionary containing learner's medical and assessment information
        user_query: User's request for specific types of activities

    Returns:
        List of activity suggestion dictionaries with therapeutic recommendations

    Usage:
        - Primary entry point for AI-powered activity suggestions
        - Provides personalized therapeutic activities based on learner profile
        - Returns structured activity data for frontend consumption
        - Handles all error cases with fallback activities

    Example:
        activities = await suggest_therapeutic_activities(
            learner_profile={"name": "John", "age": 5, "medicalDiagnosis": {...}},
            user_query="activities for sensory processing"
        )
        for activity in activities:
            print(f"Activity: {activity['title']}")
    """
    return await generate_activity_suggestions(learner_profile, user_query)


# ==================== ACTIVITY SUGGESTION FUNCTIONS ====================
# Functions for generating therapeutic activity recommendations

def _safe_dump(data: Any) -> str:
    """Safely convert dictionaries or complex structures to formatted strings."""
    if data is None:
        return "Not provided"
    if isinstance(data, (str, int, float, bool)):
        return str(data)
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError:
        return str(data)


def _prepare_learner_context(learner_profile: Dict[str, Any]) -> str:
    """Create a structured context block combining medical and assessment details."""
    name = learner_profile.get('name', 'Unknown')
    age = learner_profile.get('age', 'Unknown')
    profile_details = learner_profile.get('profileDetails') or {}
    medical_diagnosis = learner_profile.get('medicalDiagnosis') or {}
    assessment_details = (
        learner_profile.get('assessmentDetails')
        or learner_profile.get('assessment_details')
        or {}
    )
    goals = learner_profile.get('goals') or profile_details.get('goals') or []

    strengths = profile_details.get('strengths') or []
    concerns = profile_details.get('concerns') or []

    context_lines = [
        f"Name: {name}",
        f"Age: {age}",
        f"Primary Goals: {', '.join(goals) if goals else 'Not specified'}",
        "",
        "Medical Diagnosis Summary:",
        _safe_dump(medical_diagnosis),
        "",
        "Assessment Findings:",
        _safe_dump(assessment_details),
    ]

    if strengths:
        context_lines.extend([
            "",
            "Identified Strengths:",
            _safe_dump(strengths)
        ])

    if concerns:
        context_lines.extend([
            "",
            "Key Concerns:",
            _safe_dump(concerns)
        ])

    return "\n".join(context_lines)


def _build_activity_suggestion_prompt(learner_profile: Dict[str, Any], user_query: str) -> str:
    """
    Build comprehensive prompt for activity suggestion generation
    - Includes learner profile information
    - Focuses on therapeutic goals and medical needs
    - Returns structured prompt for consistent AI responses
    """
    learner_context = _prepare_learner_context(learner_profile)

    return f"""You are an expert pediatric therapist AI assistant. Review the learner context below and suggest 3-5 evidence-based therapeutic activities that address the child's specific medical and developmental needs.

LEARNER CONTEXT:
{learner_context}

USER REQUEST: {user_query or 'No additional request provided. Choose the most impactful activities.'}

IMPORTANT REQUIREMENTS:
1. Return ONLY a valid JSON array of activity objects.
2. Each activity must align with the learner's diagnosis, assessment findings, and therapy goals.
3. Consider safety, developmental level, sensory processing, and caregiver involvement.
4. Activities should be practical for home or clinical carryover with clear therapeutic intent.
5. If medical data indicates contraindications, avoid unsafe recommendations.

ACTIVITY OBJECT FORMAT:
{{
  "id": "unique_id_string",
  "title": "Clear, engaging activity name",
  "description": "Brief description of the activity and its therapeutic benefits",
  "category": "Sensory|Motor Skills|Cognitive|Communication|Social-Emotional|Creative|Adaptive",
  "difficulty": "easy|medium|hard",
  "duration": 15-45,
  "materials": ["list", "of", "required", "materials"],
  "goals": ["specific", "therapeutic", "goals", "addressed"],
  "instructions": ["step", "by", "step", "instructions"],
  "adaptations": ["modifications", "for", "different", "ability", "levels"],
  "safety_notes": ["important", "safety", "considerations"]
}}

Return the activities as a JSON array. Focus on interventions that directly support the learner's documented needs."""


def _format_history_for_prompt(history: List[Dict[str, str]]) -> str:
    """Convert stored conversation history into prompt-ready transcript."""
    if not history:
        return "No prior conversation."

    lines: List[str] = []
    for entry in history[-MAX_SESSION_HISTORY:]:
        role = entry.get("role", "assistant").upper()
        content = entry.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _summarize_activities_for_history(activities: List[Dict[str, Any]]) -> str:
    """Create a concise summary string for activity suggestions to store in history."""
    titles = [
        activity.get("activity_name")
        or activity.get("title")
        or activity.get("name")
        or "Unnamed Activity"
        for activity in activities
    ]
    if not titles:
        return "Suggested activities were provided."
    return "Suggested activities: " + ", ".join(titles[:5])


def _normalize_activity(activity: Dict[str, Any]) -> Dict[str, Any]:
    """Standardize activity payload fields for consistent frontend rendering."""

    def _clean_list(values: Any) -> List[str]:
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
        if isinstance(values, str) and values.strip():
            return [values.strip()]
        return []

    def _clean_steps(values: Any) -> List[str]:
        if isinstance(values, list):
            cleaned: List[str] = []
            for item in values:
                if isinstance(item, str):
                    step = item.strip()
                    if step:
                        cleaned.append(step)
                else:
                    cleaned.append(str(item))
            return cleaned
        if isinstance(values, str) and values.strip():
            return [values.strip()]
        return []

    name = (
        activity.get("activity_name")
        or activity.get("title")
        or activity.get("name")
        or activity.get("label")
        or "Unnamed Activity"
    )

    duration = (
        activity.get("duration_minutes")
        or activity.get("duration")
        or activity.get("time")
        or activity.get("estimated_time")
        or None
    )

    try:
        duration_value: Optional[int] = int(duration) if duration is not None else None
    except (ValueError, TypeError):
        duration_value = None

    detailed_description = (
        activity.get("detailed_description")
        or activity.get("description")
        or activity.get("summary")
        or ""
    ).strip()

    reason = (
        activity.get("reason_for_recommendation")
        or activity.get("rationale")
        or activity.get("therapeutic_rationale")
        or activity.get("reason")
        or ""
    ).strip()

    normalized = {
        "id": activity.get("id") or str(uuid.uuid4()),
        "activity_name": name,
        "duration_minutes": duration_value,
        "detailed_description": detailed_description,
        "reason_for_recommendation": reason,
        "category": activity.get("category") or "",
        "difficulty": activity.get("difficulty") or "",
        "materials": _clean_list(activity.get("materials")),
        "goals": _clean_list(activity.get("goals")),
        "instructions": _clean_steps(activity.get("instructions")),
        "adaptations": _clean_list(activity.get("adaptations")),
        "safety_notes": _clean_list(activity.get("safety_notes")),
    }

    return normalized


class ActivityChatSessionManager:
    """Manage in-memory AI chat sessions with learner context and history."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def _cleanup_expired_sessions(self) -> None:
        now = time.time()
        expired_ids = [
            session_id
            for session_id, data in self._sessions.items()
            if now - data.get("created_at", now) > SESSION_TTL_SECONDS
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)

    async def create_session(self, learner_profile: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        learner_context = _prepare_learner_context(learner_profile)
        session_payload = {
            "id": session_id,
            "created_at": time.time(),
            "learner_profile": learner_profile,
            "learner_context": learner_context,
            "history": []  # List of {role, content}
        }

        async with self._lock:
            await self._cleanup_expired_sessions()
            self._sessions[session_id] = session_payload

        return session_payload

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            await self._cleanup_expired_sessions()
            session = self._sessions.get(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="AI session not found or expired")

        return session

    async def append_history(self, session_id: str, role: str, content: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="AI session not found or expired")

            session.setdefault("history", []).append({
                "role": role,
                "content": content
            })
            # Trim to max history length
            if len(session["history"]) > MAX_SESSION_HISTORY * 2:
                session["history"] = session["history"][-MAX_SESSION_HISTORY * 2:]


# Global session manager instance
activity_session_manager = ActivityChatSessionManager()

async def generate_activity_suggestions(learner_profile: Dict[str, Any], user_query: str) -> List[Dict[str, Any]]:
    """
    Generate personalized activity suggestions using Gemini AI

    Args:
        learner_profile: Dictionary containing learner's medical and assessment information
        user_query: Therapist's request for activities

    Returns:
        List of activity dictionaries (for backward compatibility)
    """
    try:
        session = await activity_session_manager.create_session(learner_profile)
        _ = await generate_activity_chat_messages(session["id"], user_query)
        # The new chat pipeline handles formatting and response delivery.
        return []

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating activity suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate activity suggestions")


def _build_activity_chat_prompt(
    session_data: Dict[str, Any],
    user_query: str,
    ai_preferences: Optional[str] = None,
    session_notes: Optional[List[Dict[str, Any]]] = None,
    focus_context: Optional[Dict[str, Any]] = None,
    notes_instruction: Optional[str] = None
) -> str:
    history_text = _format_history_for_prompt(session_data.get("history", []))
    learner_context = session_data.get("learner_context", "")
    
    # Add AI preferences section if provided
    preferences_section = ""
    if ai_preferences and ai_preferences.strip():
        preferences_section = f"""
THERAPIST'S CUSTOM AI INSTRUCTIONS:
{ai_preferences.strip()}

IMPORTANT: Follow the therapist's custom instructions above when generating responses and activities.
"""
    
    # Add session notes section if provided
    notes_section = ""
    if session_notes and len(session_notes) > 0:
        notes_list = []
        for note in session_notes:
            session_date = note.get("session_date", "Unknown date")
            session_time = note.get("start_time", "")
            therapist_notes = note.get("therapist_notes", "No notes")
            notes_list.append(f"• {session_date} ({session_time}): {therapist_notes}")
        
        notes_text = "\n".join(notes_list)
        notes_section = f"""
SESSION NOTES CONTEXT (Behavioral observations from actual therapy sessions):
{notes_text}

IMPORTANT: Use these session notes to understand:
- Student's behavioral patterns during different times of day
- Response to different types of activities
- Progress tracking and challenges faced
- Environmental factors affecting performance
- Customize activity recommendations based on these real-world observations
"""

        if notes_instruction and notes_instruction.strip():
            notes_section += f"""
THERAPIST GUIDANCE ON SESSION NOTES:
{notes_instruction.strip()}

Always integrate the therapist's guidance above when analyzing the attached session notes.
"""

    focus_section = ""
    if focus_context and isinstance(focus_context, dict):
        activities = focus_context.get("activities") or []
        if isinstance(activities, list) and activities:
            label = focus_context.get("label") or "Therapist-selected activities"
            instruction = focus_context.get("instruction")
            source = focus_context.get("source")

            focus_lines: List[str] = []
            for index, activity in enumerate(activities, start=1):
                name = activity.get("activity_name") or activity.get("name") or "Activity"
                domain = activity.get("domain")
                status = activity.get("status")
                duration = activity.get("actual_duration") or activity.get("estimated_duration")
                description = activity.get("description") or activity.get("activity_description")
                difficulty_level = activity.get("difficulty_level")
                performance_notes = activity.get("performance_notes")
                
                detail_parts: List[str] = []
                if domain:
                    detail_parts.append(f"Domain: {domain}")
                if status:
                    detail_parts.append(f"Status: {status}")
                if duration:
                    detail_parts.append(f"Duration: {duration} min")
                if difficulty_level:
                    detail_parts.append(f"Difficulty: Level {difficulty_level}")

                descriptor = " | ".join(detail_parts) if detail_parts else ""
                line = f"{index}. {name}"
                if descriptor:
                    line += f" ({descriptor})"
                if description:
                    line += f"\n   Description: {description}"
                if performance_notes:
                    line += f"\n   Performance notes: {performance_notes}"
                focus_lines.append(line)

            focus_text = "\n".join(focus_lines)
            focus_section = f"""
THERAPIST-SELECTED ACTIVITIES ({label}):
{focus_text}
"""

            if source:
                focus_section += f"\n(Selection source: {source})\n"

            if instruction and instruction.strip():
                focus_section += f"""

THERAPIST'S REQUEST FOR THESE ACTIVITIES:
{instruction.strip()}

IMPORTANT: This is the therapist's specific instruction about what to do with the attached activities. Address this directly in your response.
"""

    return f"""You are an empathetic pediatric therapy assistant supporting licensed therapists. Use the learner context and conversation history to provide thoughtful, clinically-sound guidance.

LEARNER CONTEXT:
{learner_context}
{preferences_section}{notes_section}{focus_section}
CONVERSATION HISTORY:
{history_text}

NEW THERAPIST MESSAGE: {user_query}

RESPONSE INSTRUCTIONS:
- Acknowledge and build upon the conversation history, referencing relevant prior turns when helpful.
- Provide encouraging, professional language appropriate for therapist-to-therapist collaboration.
- When the therapist requests specific therapeutic activities, include detailed activity plans aligned with the learner's medical and assessment information.
- If custom AI instructions are provided, follow them closely while maintaining professional standards.
- If session notes are included, reference behavioral patterns and time-of-day preferences when suggesting activities.
- If therapist-selected activities are provided with instructions, address those instructions directly and specifically.
- For casual or administrative questions, respond conversationally without fabricating medical facts.
- Never invent diagnoses or promise clinical outcomes.
- Keep responses concise yet actionable.

RESPONSE FORMAT (RETURN VALID JSON ONLY):
{{
  "messages": [
    {{
      "type": "text",
      "content": "empathetic conversational reply summarizing insights"
    }},
    {{
      "type": "activities",
      "activities": [
        {{
          "id": "unique_id_string",
                    "activity_name": "Clear, engaging activity name tailored to the learner",
                    "duration_minutes": 10-45,
                    "detailed_description": "Describe the activity flow and therapeutic focus in 3-4 sentences",
                    "reason_for_recommendation": "Explain why this activity supports the learner's goals and diagnosis",
                    "category": "Sensory|Motor Skills|Cognitive|Communication|Social-Emotional|Creative|Adaptive",
                    "difficulty": "easy|medium|hard",
                    "materials": ["list", "of", "materials"],
                    "goals": ["therapeutic", "goals"],
                    "instructions": ["step", "by", "step"],
                    "adaptations": ["optional", "modifications"],
                    "safety_notes": ["important", "considerations"]
        }}
      ]
    }}
  ]
}}

IMPORTANT:
- Always include at least one text message in the "messages" array.
- Only include the "activities" entry when the therapist requests intervention ideas.
- Keep JSON clean with no markdown or commentary.
"""


async def generate_activity_chat_messages(
    session_id: str,
    user_query: str,
    ai_preferences: Optional[str] = None,
    session_notes: Optional[List[Dict[str, Any]]] = None,
    focus_context: Optional[Dict[str, Any]] = None,
    notes_instruction: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Generate assistant messages using stored session context and history."""
    session_data = await activity_session_manager.get_session(session_id)

    await activity_session_manager.append_history(session_id, "user", user_query)

    prompt = _build_activity_chat_prompt(
        session_data,
        user_query,
        ai_preferences,
        session_notes,
        focus_context,
        notes_instruction
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.6,
            "topK": 32,
            "topP": 0.9,
            "maxOutputTokens": 2048,
        }
    }

    response_data = await _make_gemini_api_request(payload)

    if "candidates" not in response_data or not response_data["candidates"]:
        logger.error("No candidates in Gemini response for activity chat")
        raise HTTPException(status_code=500, detail="No response from Gemini API")

    generated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
    logger.info(f"Gemini chat response length: {len(generated_text)}")

    clean_text = _clean_json_response(generated_text)

    try:
        parsed = json.loads(clean_text)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse chat response JSON: {exc}")
        logger.error(f"Raw response: {generated_text[:500]}...")
        raise HTTPException(status_code=500, detail="AI response parsing failed")

    messages = parsed.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=500, detail="AI response missing messages array")

    assistant_messages: List[Dict[str, Any]] = []

    for entry in messages:
        message_type = entry.get("type")

        if message_type == "text":
            content = entry.get("content")
            if not isinstance(content, str) or not content.strip():
                logger.warning("Skipping empty text message from AI response")
                continue

            assistant_messages.append({
                "role": "assistant",
                "kind": "text",
                "content": content.strip()
            })

        elif message_type == "activities":
            activities = entry.get("activities")
            if not isinstance(activities, list) or not activities:
                logger.warning("Skipping invalid activities entry from AI response")
                continue

            normalized = [_normalize_activity(activity) for activity in activities]

            assistant_messages.append({
                "role": "assistant",
                "kind": "activities",
                "activities": normalized
            })
        else:
            logger.warning(f"Unknown message type from AI: {message_type}")

    if not assistant_messages:
        raise HTTPException(status_code=500, detail="AI response did not contain usable messages")

    # Persist assistant messages in session history for future turns
    for message in assistant_messages:
        if message["kind"] == "text":
            await activity_session_manager.append_history(session_id, "assistant", message["content"]) 
        elif message["kind"] == "activities":
            summary = _summarize_activities_for_history(message.get("activities", []))
            await activity_session_manager.append_history(session_id, "assistant", summary)

    return assistant_messages


async def create_activity_chat_session(learner_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize a new AI activity chat session and return session metadata."""
    session = await activity_session_manager.create_session(learner_profile)
    return {
        "session_id": session["id"]
    }

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional AI service functionality

# TODO: Implement document validation service
# async def validate_document_format(file_path: str) -> Dict[str, Any]:
#     """Validate document format and readability before OCR processing"""
#     pass

# TODO: Implement batch processing functionality
# async def process_multiple_documents(file_paths: List[str]) -> List[Dict[str, Any]]:
#     """Process multiple documents in batch for efficiency"""
#     pass

# TODO: Implement confidence scoring for extracted data
# def calculate_extraction_confidence(extracted_data: Dict[str, Any]) -> float:
#     """Calculate confidence score for extracted medical data"""
#     pass

# TODO: Implement data validation against medical standards
# def validate_medical_data(medical_data: Dict[str, Any]) -> Dict[str, bool]:
#     """Validate extracted medical data against standard formats"""
#     pass

# TODO: Implement custom prompt generation based on document type
# def generate_custom_prompt(document_type: str) -> str:
#     """Generate specialized prompts for different document types"""
#     pass

# ==================== UTILITY FUNCTIONS FOR EXTERNAL USE ====================
# Additional utility functions that may be useful for other modules

def get_supported_file_types() -> List[str]:
    """
    Get list of supported file extensions for OCR processing
    
    Returns:
        List of supported file extensions
    
    Usage:
        - Used by file upload validation
        - Helps display supported formats to users
    """
    return list(SUPPORTED_MIME_TYPES.keys())

def validate_file_type(file_path: str) -> bool:
    """
    Validate if file type is supported for OCR processing
    
    Args:
        file_path: Path to file to validate
    
    Returns:
        True if file type is supported, False otherwise
    
    Usage:
        - Pre-validation before OCR processing
        - File upload validation in API endpoints
    """
    _, ext = os.path.splitext(file_path)
    return ext.lower() in SUPPORTED_MIME_TYPES

def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get basic information about a file
    
    Args:
        file_path: Path to file to analyze
    
    Returns:
        Dictionary containing file information
    
    Usage:
        - File validation and logging
        - API response metadata
    """
    try:
        stat = os.stat(file_path)
        _, ext = os.path.splitext(file_path)
        
        return {
            "file_size": stat.st_size,
            "file_extension": ext.lower(),
            "mime_type": _determine_mime_type(file_path),
            "is_supported": validate_file_type(file_path),
            "file_name": os.path.basename(file_path)
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
        return {
            "error": str(e),
            "is_supported": False
        }