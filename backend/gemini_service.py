import google.generativeai as genai
import json
import os
import re
from pathlib import Path

# Will be configured when the app starts
model = None


def configure(api_key: str):
    """Initialize the Gemini API client with the given API key."""
    global model
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')


EXTRACTION_PROMPT = """You are a senior pharmacist AI. Analyze this prescription image and extract ALL medicines listed.
Do not just blindly read raw shapes; use your clinical knowledge, the patient's diagnosis (if visible), and the context of other medicines to deduce the real medicine being prescribed.

For EACH medicine found, provide:
1. "type": The medicine type (Tab/Cap/Syp/Inj/Drops/Cream/Ointment/Inhaler etc.)
2. "raw_ocr": What do the raw letters look like exactly, including unreadable parts? (e.g., "P---mol 650", "Azith--- 500")
3. "clear_name": If the medicine name is 100% perfectly readable and unambiguous, put the exact brand name + strength here (e.g., "Azithral 500"). If it is messy, scribbled, cut off, or unclear in ANY way, you MUST leave this as null.
4. "guesses": IF and ONLY IF "clear_name" is null, provide an array of 2-4 possible interpretations of the medicine name based on the raw OCR shapes AND the clinical context. 
    - Each guess must be an object with: "name" (brand + strength), "confidence" (high/medium/low), and "reason" (why it makes sense clinically and visually). 
    - Put your most confident guess first.
    - If "clear_name" is populated, leave this array EMPTY [].
5. "dosage": The dosage frequency exactly as written (e.g., "1-0-1", "BD", "OD", "SOS", "1-1-1")
6. "duration": How long to take (e.g., "5 days", "7 days", "15 days") — if mentioned
7. "special_instructions": Any additional instructions written for that medicine (e.g., "after food", "before sleep", "with warm water")
8. "uses": Brief one-line description of what this medicine is used for (e.g., "Fever and pain relief")
9. "side_effects": Common side effects (e.g., "Nausea, stomach upset")
10. "food_instruction": Whether to take before food, after food, or with food

IMPORTANT RULES:
- Include the strength/dosage form if visible (e.g., 500mg, 650mg, 10mg) in the clear_name or guesses.
- Preserve the type prefix (Tab, Cap, Syp, etc.) separately.
- If duration or dosage frequency is not mentioned, set it to "As directed".
- IMPORTANT: Return strictly valid JSON. Do NOT include unescaped newlines or quotes inside string values. Replace any newlines inside strings with a single space.
Return ONLY valid JSON in this exact format, no markdown formatting:
{
    "medicines": [
        {
            "type": "Tab",
            "raw_ocr": "Azithral 500",
            "clear_name": "Azithral 500",
            "guesses": [],
            "dosage": "1-0-1",
            "duration": "5 days",
            "special_instructions": "after food",
            "uses": "Bacterial infection",
            "side_effects": "Stomach upset",
            "food_instruction": "After food"
        },
        {
            "type": "Tab",
            "raw_ocr": "P...mol 650",
            "clear_name": null,
            "guesses": [
                {"name": "Paracetamol 650", "confidence": "high", "reason": "Matches 'P' and 'mol', standard fever medication alongside antibiotics"},
                {"name": "Pacimol 650", "confidence": "low", "reason": "Alternative brand name for paracetamol"}
            ],
            "dosage": "1-1-1",
            "duration": "3 days",
            "special_instructions": "SOS",
            "uses": "Fever and pain relief",
            "side_effects": "Nausea, liver risk on overdose",
            "food_instruction": "After food"
        }
    ],
    "doctor_name": "Name if visible, else empty string",
    "patient_name": "Name if visible, else empty string",
    "date": "Date if visible, else empty string",
    "diagnosis": "Diagnosis if visible, else empty string"
}
"""


async def extract_prescription(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Send prescription image to Gemini and extract structured data.
    
    Args:
        image_bytes: Raw image bytes
        mime_type: MIME type of the image
    
    Returns:
        dict with extracted prescription data
    """
    if model is None:
        raise RuntimeError("Gemini API not configured. Call configure() first.")
    
    image_part = {
        "mime_type": mime_type,
        "data": image_bytes
    }
    
    try:
        response = await model.generate_content_async(
            [EXTRACTION_PROMPT, image_part],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for accuracy
                max_output_tokens=8192,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        # Handle blocked/empty responses
        if not response.candidates or not response.text:
            return {
                "error": "AI response was blocked or empty",
                "medicines": []
            }
        
        # Parse the JSON response
        text = response.text.strip()
        
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            
        print("--- RAW AI RESPONSE ---")
        try:
            print("FINISH REASON:", response.candidates[0].finish_reason)
        except Exception:
            pass
        print(text)
        print("-----------------------")
        
        # strict=False allows unescaped control characters like newlines within strings
        result = json.loads(text, strict=False)
        return result
        
    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse AI response: {str(e)}",
            "raw_response": response.text if response else "",
            "medicines": []
        }
    except Exception as e:
        return {
            "error": f"Gemini API error: {str(e)}",
            "medicines": []
        }


async def get_medicine_info_from_ai(medicine_name: str) -> dict:
    """
    Fallback: Ask Gemini about a medicine when it's not in our database.
    
    Args:
        medicine_name: Name of the medicine
    
    Returns:
        dict with medicine information
    """
    if model is None:
        return {"error": "Gemini API not configured"}
    
    prompt = f"""Provide brief information, estimated price, and availability for the medicine "{medicine_name}" in India in JSON format:
{{
    "brand_name": "{medicine_name}",
    "generic_name": "generic/salt name",
    "type": "Tablet/Capsule/Syrup etc.",
    "uses": "brief one-line use",
    "side_effects": "common side effects",
    "food_instruction": "Before food/After food/With food",
    "warnings": "important warning",
    "estimated_price": "estimated price in INR",
    "available_on": "e.g. 1mg, Apollo Pharmacy, PharmEasy"
}}
Return ONLY valid JSON, no markdown formatting."""
    
    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=8192,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        
        return json.loads(text)
        
    except Exception as e:
        return {
            "brand_name": medicine_name,
            "generic_name": "Unknown",
            "uses": "Consult your doctor",
            "side_effects": "Consult your doctor",
            "food_instruction": "As directed",
            "warnings": "Follow doctor's instructions",
            "estimated_price": "",
            "available_on": ""
        }
