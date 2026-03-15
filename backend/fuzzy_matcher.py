from typing import Optional

import pandas as pd
from rapidfuzz import fuzz, process
from pathlib import Path

# Load the Kaggle A-Z Medicine Dataset of India
DATA_PATH = Path(__file__).parent / "data" / "A_Z_medicines_dataset_of_India.csv"
medicines_df = pd.read_csv(DATA_PATH)

# Load the 1mg Dataset
OMG_DATA_PATH = Path(__file__).parent / "data" / "1mgData.csv"
try:
    onemg_df = pd.read_csv(OMG_DATA_PATH)
except FileNotFoundError:
    onemg_df = pd.DataFrame()

# Clean up: remove discontinued medicines, keep only useful columns
medicines_df = medicines_df[medicines_df["Is_discontinued"] == False].copy()

# Create a clean 'brand_name' by extracting name without dosage form type suffix
# e.g., "Augmentin 625 Duo Tablet" → used as-is for matching
medicines_df["brand_name"] = medicines_df["name"].str.strip()

# Build composition column (combine both)
medicines_df["generic_name"] = medicines_df.apply(
    lambda row: (
        str(row["short_composition1"]).strip()
        + ((" + " + str(row["short_composition2"]).strip()) if pd.notna(row["short_composition2"]) else "")
    ),
    axis=1,
)

# Pre-compute list of brand names for fuzzy matching
BRAND_NAMES = medicines_df["brand_name"].tolist()

# For performance: pre-build a lowercase lookup dict for exact matching
EXACT_LOOKUP = {}
for _, row in medicines_df.iterrows():
    EXACT_LOOKUP[row["brand_name"].lower()] = row

# Pre-build lookup for the 1mg dataset
ONEMG_EXACT_LOOKUP = {}
if not onemg_df.empty:
    for _, row in onemg_df.iterrows():
        # Clean 1mg price (remove the '₹' symbol so it matches Kaggle schema)
        clean_price = str(row.get("price", "")).replace("₹", "").strip()
        
        # Build a compatible dict immediately 
        ONEMG_EXACT_LOOKUP[str(row.get("Name", "")).strip().lower()] = {
            "brand_name": str(row.get("Name", "")).strip(),
            "generic_name": "", # Not clearly defined in 1mg data, will fallback to AI estimation
            "type": str(row.get("pack_size", "")),
            "manufacturer": "",
            "price": clean_price,
            "uses": "",
            "side_effects": "",
            "food_instruction": "",
            "warnings": ""
        }

# Pre-compute 1mg brand names for fuzzy matching
ONEMG_BRAND_NAMES = list(ONEMG_EXACT_LOOKUP.keys()) if ONEMG_EXACT_LOOKUP else []


def fuzzy_match_medicine(name: str, threshold: int = 65) -> Optional[dict]:
    """
    Fuzzy match a medicine name against the Kaggle database (254K entries).
    
    Uses a tiered approach for performance:
    1. Exact match (instant)
    2. Prefix search (fast)
    3. Fuzzy match on filtered subset (accurate)
    
    Args:
        name: Medicine name to search (possibly misspelled by OCR)
        threshold: Minimum similarity score (0-100)
    
    Returns:
        dict with medicine info if match found, None otherwise
    """
    if not name or not name.strip():
        return None
    
    clean_name = name.strip()
    
    # Tier 1: Exact match (case-insensitive) — O(1)
    lower_name = clean_name.lower()
    if lower_name in EXACT_LOOKUP:
        return _row_to_dict(EXACT_LOOKUP[lower_name])
    
    # Tier 2: Search exact match in the 1mg dataset
    if lower_name in ONEMG_EXACT_LOOKUP:
        return ONEMG_EXACT_LOOKUP[lower_name]
        
    # Tier 3: Try matching with common suffixes added/removed
    # Doctors often write "Dolo 650" but DB has "Dolo 650 Tablet"
    for suffix in ["Tablet", "Capsule", "Syrup", "Injection", "Drops", "Cream", "Gel", "Ointment", "Inhaler"]:
        with_suffix = f"{clean_name} {suffix}".lower()
        if with_suffix in EXACT_LOOKUP:
            return _row_to_dict(EXACT_LOOKUP[with_suffix])
        if with_suffix in ONEMG_EXACT_LOOKUP:
            return ONEMG_EXACT_LOOKUP[with_suffix]
    
    # Tier 3: Filter candidates by first 2-3 chars then fuzzy match
    # This avoids fuzzy matching against all 254K entries
    prefix = clean_name[:3].lower()
    candidates = [n for n in BRAND_NAMES if n[:3].lower() == prefix]
    
    if not candidates:
        # Broader prefix match
        prefix = clean_name[:2].lower()
        candidates = [n for n in BRAND_NAMES if n[:2].lower() == prefix]
    
    if not candidates:
        # Fall back to full fuzzy search but with limit
        candidates = BRAND_NAMES
    
    # Cap candidates to avoid slow searches
    if len(candidates) > 5000:
        candidates = candidates[:5000]
    
    result = process.extractOne(
        clean_name,
        candidates,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    
    if result:
        match_name, score, _ = result
        row = medicines_df[medicines_df["brand_name"] == match_name].iloc[0]
        match_dict = _row_to_dict(row)
        match_dict["match_score"] = score
        match_dict["original_query"] = clean_name
        return match_dict
    
    # Tier 5: Fuzzy match against 1mg dataset
    if ONEMG_BRAND_NAMES:
        onemg_result = process.extractOne(
            clean_name.lower(),
            ONEMG_BRAND_NAMES,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )
        if onemg_result:
            match_key, score, _ = onemg_result
            match_dict = ONEMG_EXACT_LOOKUP[match_key].copy()
            match_dict["match_score"] = score
            match_dict["original_query"] = clean_name
            return match_dict
    
    return None


def search_by_generic(generic_name: str) -> list:
    """
    Search medicines by generic/salt name.
    """
    matches = medicines_df[
        medicines_df["generic_name"].str.lower().str.contains(
            generic_name.lower(), na=False
        )
    ].head(20)  # Limit results
    return [_row_to_dict(row) for _, row in matches.iterrows()]


def _row_to_dict(row) -> dict:
    """Convert a DataFrame row to a clean dictionary."""
    return {
        "brand_name": str(row.get("brand_name", "")),
        "generic_name": str(row.get("generic_name", "")),
        "type": str(row.get("pack_size_label", "")),
        "manufacturer": str(row.get("manufacturer_name", "")),
        "price": str(row.get("price(₹)", "")),
        "uses": "",          # Not in Kaggle data — Gemini will fill this
        "side_effects": "",  # Not in Kaggle data — Gemini will fill this
        "food_instruction": "",
        "warnings": "",
    }
