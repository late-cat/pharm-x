import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

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
        medicine_name = med.get("name", "")
        medicine_type = med.get("type", "")
        dosage_code = med.get("dosage", "As directed")
        duration = med.get("duration", "As directed")
        special_instructions = med.get("special_instructions", "")
        
        # Gemini-provided info (uses, side effects, food instruction)
        ai_uses = med.get("uses", "")
        ai_side_effects = med.get("side_effects", "")
        ai_food_instruction = med.get("food_instruction", "")
        
        # Fuzzy match against Kaggle database (for name validation, generic name, price, manufacturer)
        db_match = fuzzy_match_medicine(medicine_name)
        
        # If no DB match or no price in DB, fallback to AI for price estimation + availability
        ai_fallback = {}
        if not db_match or not db_match.get("price"):
            ai_fallback = await get_medicine_info_from_ai(medicine_name)
        
        # Interpret dosage
        dosage_info = interpret_dosage(dosage_code)
        
        # Get full medicine type
        full_type = get_medicine_type(medicine_type) if medicine_type else (db_match.get("type", "") if db_match else "")
        
        # Build enriched medicine card
        # DB provides: validated name, generic_name, manufacturer, price
        # Gemini provides: uses, side_effects, food_instruction, and fallback estimated_price & available_on
        enriched = {
            "name": db_match.get("brand_name", medicine_name) if db_match else medicine_name,
            "generic_name": db_match.get("generic_name", "") if db_match else ai_fallback.get("generic_name", ""),
            "type": full_type,
            "manufacturer": db_match.get("manufacturer", "") if db_match else "",
            "price": db_match.get("price", "") if db_match else "",
            "estimated_price": ai_fallback.get("estimated_price", ""),
            "available_on": ai_fallback.get("available_on", ""),
            "uses": ai_uses or ai_fallback.get("uses", "Consult your doctor"),
            "side_effects": ai_side_effects or ai_fallback.get("side_effects", ""),
            "dosage_code": dosage_code,
            "dosage_readable": dosage_info["times"],
            "schedule": dosage_info["schedule"],
            "duration": duration,
            "food_instruction": ai_food_instruction or special_instructions or ai_fallback.get("food_instruction", "As directed"),
            "warnings": ai_fallback.get("warnings", ""),
            "special_instructions": special_instructions,
            "match_score": db_match.get("match_score") if db_match else None,
        }
        
        enriched_medicines.append(enriched)
        
        # Build schedule
        for time_slot in dosage_info["schedule"]:
            # Normalize schedule key
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
        "medicines": enriched_medicines,
        "daily_schedule": schedule_data,
        "total_medicines": len(enriched_medicines),
    }
    
    return JSONResponse(content=response)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Prescription Reader API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
