"""
Gym Name Normalization and Canonical Mapping

Prevents duplicate gym records by normalizing variations to canonical names.
Maintains a mapping of known variations to their canonical gym names.
"""

# Known gym name variations mapped to canonical names
# Format: variation (lowercase) -> canonical_name
GYM_NAME_MAP = {
    # The Flip Zone variations
    "the flip zone": "The Flip Zone",
    "flip zone": "The Flip Zone",  # Without "The" - covers "Flip Zone", "flip zone", etc.
    "tfz": "The Flip Zone",
    "tfz in": "The Flip Zone",
    "the flip zone in": "The Flip Zone",
    "flip zone (in)": "The Flip Zone",
    "flip zone in": "The Flip Zone",

    # JPAC variations
    "jpac": "JPAC - Jaycie Phelps Athletic Center",
    "jpac in": "JPAC - Jaycie Phelps Athletic Center",
    "Jaycie Phelps Athletic Center": "JPAC - Jaycie Phelps Athletic Center",
    "jaycie phelps athletic center": "JPAC - Jaycie Phelps Athletic Center",
    "jaycie phelps athletic center in": "JPAC - Jaycie Phelps Athletic Center",
    "jaycie phelps athletic center (in)": "JPAC - Jaycie Phelps Athletic Center",
    "jaycie phelps athletic center in": "JPAC - Jaycie Phelps Athletic Center",
    # Add more known variations as they're discovered
    # Example:
    # "integrity athletics": "Integrity Athletics",
    # "integrity": "Integrity Athletics",
}


def normalize_gym_name(raw: str) -> str:
    """
    Normalize gym name to canonical form.
    
    Steps:
    1. Strip whitespace
    2. Title case
    3. Check against known variations map
    4. Return canonical name
    
    Args:
        raw: Raw gym name from source
        
    Returns:
        Canonical gym name
    """
    if not raw:
        return "Unknown Gym"
    
    # Basic normalization
    normalized = " ".join(str(raw).strip().split()).title()
    
    # Check against known variations
    lookup_key = normalized.lower()
    canonical = GYM_NAME_MAP.get(lookup_key, normalized)
    
    return canonical


def add_gym_variation(variation: str, canonical: str) -> None:
    """
    Add a new gym name variation to the mapping.
    Useful for runtime updates when new variations are discovered.
    
    Args:
        variation: The variation name (will be lowercased)
        canonical: The canonical name to map to
    """
    GYM_NAME_MAP[variation.lower()] = canonical
