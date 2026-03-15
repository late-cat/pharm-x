import os
import asyncio
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from gemini_service import configure, extract_prescription, get_medicine_info_from_ai
from fuzzy_matcher import fuzzy_match_medicine
from dosage_rules import interpret_dosage, get_medicine_type

app = FastAPI(title="Pharm-X", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Configure Gemini on startup
@app.on_event("startup")
async def startup():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("⚠️  WARNING: GEMINI_API_KEY not set! Set it in .env or environment.")
        print("   Export it: export GEMINI_API_KEY=your_key_here")
    else:
        configure(api_key)
        print("✅ Gemini API configured successfully")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(), status_code=200)


@app.post("/api/analyze")
async def analyze_prescription(file: UploadFile = File(...)):
    """
    Main endpoint: Upload prescription image → get analyzed results.
    
    Pipeline:
    1. Gemini reads the image and extracts medicine data
    2. Fuzzy match each medicine against local database
    3. Interpret dosage codes into patient-friendly instructions
    4. Merge all data and return
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {', '.join(allowed_types)}"
        )
    
    # Read image bytes
    image_bytes = await file.read()
    
    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image too large. Max 10MB.")
    
    # Step 1: Gemini extracts prescription data
    gemini_result = await extract_prescription(image_bytes, file.content_type)
    
    if "error" in gemini_result and not gemini_result.get("medicines"):
        raise HTTPException(status_code=500, detail=gemini_result["error"])
    
    # Step 2 & 3: Enrich each medicine with database info + dosage interpretation
    enriched_medicines = []
    schedule_data = {
        "Morning": [],
        "Afternoon": [],
        "Evening": [],
        "Night": [],
        "Night (before sleep)": [],
        "As needed": [],
        "As directed by doctor": [],
    }
    
    for med in gemini_result.get("medicines", []):
        clear_name = med.get("clear_name")
        guesses = med.get("guesses", [])
        raw_ocr = med.get("raw_ocr", "Unknown")
        
        medicine_type = med.get("type", "")
        dosage_code = med.get("dosage", "As directed")
        duration = med.get("duration", "As directed")
        special_instructions = med.get("special_instructions", "")
        
        # Gemini-provided info (uses, side effects, food instruction)
        ai_uses = med.get("uses", "")
        ai_side_effects = med.get("side_effects", "")
        ai_food_instruction = med.get("food_instruction", "")
        
        db_match = None
        best_name = ""
        match_reason = ""
        needs_review = False
        
        if clear_name:
            best_name = clear_name
            db_match = fuzzy_match_medicine(clear_name)
        elif guesses:
            # Pass 1: Exact matches for AI guesses
            for guess in guesses:
                guess_name = guess.get("name", "")
                match = fuzzy_match_medicine(guess_name, threshold=100)
                if match:
                    db_match = match
                    best_name = guess_name
                    match_reason = guess.get("reason", "")
                    break
            
            # Pass 2: Fuzzy matches for AI guesses
            if not db_match:
                for guess in guesses:
                    guess_name = guess.get("name", "")
                    match = fuzzy_match_medicine(guess_name, threshold=75)
                    if match:
                        db_match = match
                        best_name = guess_name
                        match_reason = guess.get("reason", "")
                        break
            
            # Pass 3: Fallback to best guess if no DB match found
            if not db_match:
                best_guess = guesses[0]
                best_name = best_guess.get("name", "")
                match_reason = best_guess.get("reason", "")
                needs_review = True
        else:
            best_name = raw_ocr
            needs_review = True
        
        # Interpret dosage
        dosage_info = interpret_dosage(dosage_code)
        
        # Get full medicine type
        full_type = get_medicine_type(medicine_type) if medicine_type else (db_match.get("type", "") if db_match else "")
        
        enriched_medicines.append({
            "_med_ref": med,
            "db_match": db_match,
            "dosage_info": dosage_info,
            "full_type": full_type,
            "ai_uses": ai_uses,
            "ai_side_effects": ai_side_effects,
            "ai_food_instruction": ai_food_instruction,
            "special_instructions": special_instructions,
            "medicine_name": best_name,
            "dosage_code": dosage_code,
            "duration": duration,
            "needs_review": needs_review,
            "match_reason": match_reason,
            "raw_ocr": raw_ocr
        })
    
    # Parallelize AI fallback calls for medicines missing DB prices
    ai_tasks = []
    fallback_indices = []
    for i, item in enumerate(enriched_medicines):
        if not item["db_match"] or not item["db_match"].get("price"):
            ai_tasks.append(get_medicine_info_from_ai(item["medicine_name"]))
            fallback_indices.append(i)
    
    ai_results = await asyncio.gather(*ai_tasks) if ai_tasks else []
    
    # Map AI results back to their medicines
    ai_fallbacks = {}
    for idx, ai_result in zip(fallback_indices, ai_results):
        ai_fallbacks[idx] = ai_result
    
    # Build final enriched medicine list
    final_medicines = []
    for i, item in enumerate(enriched_medicines):
        db_match = item["db_match"]
        ai_fallback = ai_fallbacks.get(i, {})
        full_type = item["full_type"]
        
        enriched = {
            "name": db_match.get("brand_name", item["medicine_name"]) if db_match else item["medicine_name"],
            "generic_name": db_match.get("generic_name", "") if db_match else ai_fallback.get("generic_name", ""),
            "type": full_type,
            "manufacturer": db_match.get("manufacturer", "") if db_match else "",
            "price": db_match.get("price", "") if db_match else "",
            "estimated_price": ai_fallback.get("estimated_price", ""),
            "available_on": ai_fallback.get("available_on", ""),
            "uses": item["ai_uses"] or ai_fallback.get("uses", "Consult your doctor"),
            "side_effects": item["ai_side_effects"] or ai_fallback.get("side_effects", ""),
            "dosage_code": item["dosage_code"],
            "dosage_readable": item["dosage_info"]["times"],
            "schedule": item["dosage_info"]["schedule"],
            "duration": item["duration"],
            "food_instruction": item["ai_food_instruction"] or item["special_instructions"] or ai_fallback.get("food_instruction", "As directed"),
            "warnings": ai_fallback.get("warnings", ""),
            "special_instructions": item["special_instructions"],
            "match_score": db_match.get("match_score") if db_match else None,
            "match_reason": item["match_reason"],
            "needs_review": item["needs_review"],
            "raw_ocr": item["raw_ocr"],
        }
        
        final_medicines.append(enriched)
        
        # Build schedule
        for time_slot in enriched["schedule"]:
            slot_key = time_slot
            if slot_key not in schedule_data:
                schedule_data[slot_key] = []
            schedule_data[slot_key].append({
                "name": enriched["name"],
                "type": full_type,
                "food_instruction": enriched["food_instruction"],
            })
    
    # Clean up empty schedule slots
    schedule_data = {k: v for k, v in schedule_data.items() if v}
    
    # Build response
    response = {
        "success": True,
        "prescription_info": {
            "doctor_name": gemini_result.get("doctor_name", ""),
            "patient_name": gemini_result.get("patient_name", ""),
            "date": gemini_result.get("date", ""),
            "diagnosis": gemini_result.get("diagnosis", ""),
        },
        "medicines": final_medicines,
        "daily_schedule": schedule_data,
        "total_medicines": len(final_medicines),
    }
    
    return JSONResponse(content=response)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Prescription Reader API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
