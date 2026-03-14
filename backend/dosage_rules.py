# Dosage interpretation rules
# Converts medical abbreviations to patient-friendly instructions

DOSAGE_RULES = {
    # Frequency codes (1-0-1 format)
    "1-1-1": {"times": "Three times a day", "schedule": ["Morning", "Afternoon", "Night"]},
    "1-0-1": {"times": "Twice a day", "schedule": ["Morning", "Night"]},
    "1-0-0": {"times": "Once a day", "schedule": ["Morning"]},
    "0-1-0": {"times": "Once a day", "schedule": ["Afternoon"]},
    "0-0-1": {"times": "Once a day", "schedule": ["Night"]},
    "1-1-0": {"times": "Twice a day", "schedule": ["Morning", "Afternoon"]},
    "0-1-1": {"times": "Twice a day", "schedule": ["Afternoon", "Night"]},
    "1-0-0-1": {"times": "Twice a day", "schedule": ["Morning", "Night"]},
    "1-1-1-1": {"times": "Four times a day", "schedule": ["Morning", "Afternoon", "Evening", "Night"]},

    # Half-dose patterns
    "½-0-½": {"times": "Twice a day (half tablet each)", "schedule": ["Morning", "Night"]},
    "½-0-0": {"times": "Once a day (half tablet)", "schedule": ["Morning"]},
    "0-0-½": {"times": "Once a day (half tablet)", "schedule": ["Night"]},
}

# Medical abbreviations
ABBREVIATION_RULES = {
    "OD": {"times": "Once daily", "schedule": ["Morning"]},
    "BD": {"times": "Twice daily", "schedule": ["Morning", "Night"]},
    "TDS": {"times": "Three times a day", "schedule": ["Morning", "Afternoon", "Night"]},
    "TID": {"times": "Three times a day", "schedule": ["Morning", "Afternoon", "Night"]},
    "QID": {"times": "Four times a day", "schedule": ["Morning", "Afternoon", "Evening", "Night"]},
    "QDS": {"times": "Four times a day", "schedule": ["Morning", "Afternoon", "Evening", "Night"]},
    "SOS": {"times": "When needed (as required)", "schedule": ["As needed"]},
    "PRN": {"times": "When needed (as required)", "schedule": ["As needed"]},
    "HS": {"times": "At bedtime", "schedule": ["Night (before sleep)"]},
    "AC": {"times": "Before food", "schedule": []},
    "PC": {"times": "After food", "schedule": []},
    "STAT": {"times": "Immediately (one time)", "schedule": ["Immediately"]},
    "Q8H": {"times": "Every 8 hours", "schedule": ["Morning", "Afternoon", "Night"]},
    "Q6H": {"times": "Every 6 hours", "schedule": ["Morning", "Noon", "Evening", "Night"]},
    "Q12H": {"times": "Every 12 hours", "schedule": ["Morning", "Night"]},
    "Q4H": {"times": "Every 4 hours", "schedule": ["6 times a day"]},
    "EOD": {"times": "Every other day (alternate days)", "schedule": ["Alternate days"]},
    "WEEKLY": {"times": "Once a week", "schedule": ["Weekly"]},
    "BIWEEKLY": {"times": "Twice a week", "schedule": ["Twice a week"]},
}

# Medicine type mappings
MEDICINE_TYPES = {
    "TAB": "Tablet",
    "TAB.": "Tablet",
    "TABLET": "Tablet",
    "CAP": "Capsule",
    "CAP.": "Capsule",
    "CAPSULE": "Capsule",
    "SYP": "Syrup",
    "SYP.": "Syrup",
    "SYRUP": "Syrup",
    "INJ": "Injection",
    "INJ.": "Injection",
    "INJECTION": "Injection",
    "DROPS": "Drops",
    "DROP": "Drops",
    "CREAM": "Cream",
    "OINT": "Ointment",
    "OINTMENT": "Ointment",
    "GEL": "Gel",
    "SUSP": "Suspension",
    "SUSPENSION": "Suspension",
    "INHALER": "Inhaler",
    "SPRAY": "Spray",
    "LOTION": "Lotion",
    "POWDER": "Powder",
    "SACHET": "Sachet",
    "RESPULES": "Respules (Nebulizer)",
    "GARGLE": "Gargle",
}


def interpret_dosage(frequency_code: str) -> dict:
    """
    Interpret a dosage frequency code into patient-friendly instructions.
    
    Args:
        frequency_code: e.g., "1-0-1", "BD", "OD", "SOS"
    
    Returns:
        dict with 'times' (human-readable) and 'schedule' (list of time slots)
    """
    code = frequency_code.strip().upper()
    
    # Check exact match in dosage rules (1-0-1 format)
    if code in DOSAGE_RULES:
        return DOSAGE_RULES[code]
    
    # Check abbreviation rules
    if code in ABBREVIATION_RULES:
        return ABBREVIATION_RULES[code]
    
    # Try to match partial abbreviations
    for abbr, rule in ABBREVIATION_RULES.items():
        if abbr in code:
            return rule
    
    # Default: return the code as-is
    return {
        "times": frequency_code,
        "schedule": ["As directed by doctor"]
    }


def get_medicine_type(type_code: str) -> str:
    """
    Convert medicine type abbreviation to full form.
    
    Args:
        type_code: e.g., "Tab", "Cap", "Syp"
    
    Returns:
        Full form string e.g., "Tablet", "Capsule", "Syrup"
    """
    code = type_code.strip().upper().rstrip(".")
    
    # Check direct match
    if code in MEDICINE_TYPES:
        return MEDICINE_TYPES[code]
    
    # Check with period
    if code + "." in MEDICINE_TYPES:
        return MEDICINE_TYPES[code + "."]
    
    return type_code.strip()
