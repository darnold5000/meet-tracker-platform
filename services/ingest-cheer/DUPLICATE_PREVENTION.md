# Duplicate Prevention Strategy

This document explains how the system prevents duplicate gymnast and gym records.

## Problem Summary

Previously, we encountered two types of duplicates:
1. **Duplicate Gymnast Records**: Same gymnast created multiple times when gym name varied
2. **Duplicate Gym Records**: Same gym created multiple times due to name variations (e.g., "Tfz" vs "The Flip Zone")

## Solutions Implemented

### 1. Gym Duplicate Prevention

**Location**: `core/gym_normalizer.py` and `ingest.py::_get_or_create_gym()`

**How it works**:
- All gym names are normalized using `core.gym_normalizer.normalize_gym_name()`
- Known variations are mapped to canonical names (e.g., "Tfz" → "The Flip Zone")
- Database lookups always use `canonical_name` field
- New gyms are only created if no matching `canonical_name` exists

**Example**:
```python
# These all map to "The Flip Zone":
"Tfz" → "The Flip Zone"
"Tfz In" → "The Flip Zone"
"The Flip Zone In" → "The Flip Zone"
"Flip Zone In" → "The Flip Zone"
"Flip Zone" → "The Flip Zone"
```

**Adding new variations**: Edit `core/gym_normalizer.py::GYM_NAME_MAP`

### 2. Athlete Duplicate Prevention

**Location**: `ingest.py::_get_or_create_athlete()`

**How it works**:
- Athletes are **always** identified by `canonical_name + gym_id` combination
- Same name at different gyms = different athletes (correct)
- Same name at same gym = same athlete (prevents duplicates)
- Level can change over time (athlete moves up levels) but athlete record stays the same

**Key points**:
- Checks `AthleteAlias` table first (scoped to gym_id)
- Then checks `Athlete` table by canonical_name + gym_id
- Never creates duplicate athlete for same name + gym combination
- Level updates are allowed (athlete may compete at different levels)

**Example**:
```python
# These create DIFFERENT athletes (correct):
"Jane Smith" at gym_id=1 → Athlete A
"Jane Smith" at gym_id=2 → Athlete B

# These create SAME athlete (prevents duplicate):
"Jane Smith" at gym_id=1, level=6 → Athlete A
"Jane Smith" at gym_id=1, level=7 → Athlete A (level updated)
```

### 3. Score Duplicate Prevention

**Location**: `ingest.py::save_scores()`

**How it works**:
- Uses `record_hash` based on: `meet_id + athlete_name + event + score`
- Skips insertion if hash already exists
- Prevents duplicate score records

## Target Meets

Currently scraping **12 meets** (excluding Tulip City which is not available via API):

1. MSO-35397 - 2025 North Pole Classic USAG
2. MSO-35120 - 2026 California Grand Invitational
3. MSO-35799 - 2026 Jaycie Phelps Midwest Showdown
4. MSO-35846 - 2026 Jaycie Phelps Midwest Showdown NGA
5. MSO-35550 - 2026 Circle of Stars
6. MSO-35547 - 2026 Walk of Fame Classic
7. MSO-36189 - 2026 Flip For Your Cause [USAG]
8. MSO-36190 - 2026 Flip For Your Cause [NGA]
9. MSO-36315 - 2026 Shamrock Shenanigans At Midwest
10. MSO-BUG-BITE-2025 - 2025 Bug Bite Invitational
11. MSO-DERBY-2026 - 2026 Derby Classic
12. MSO-SWING-2026 - 2026 Swing Into Spring Invitational

**Excluded**: MSO-TULIP-2026 (Tulip City Classic) - not available via API

## Verification

To verify duplicate prevention is working:

```python
# Check for duplicate gyms
SELECT canonical_name, COUNT(*) 
FROM gyms 
GROUP BY canonical_name 
HAVING COUNT(*) > 1;

# Check for duplicate athletes (same name + gym)
SELECT canonical_name, gym_id, COUNT(*) 
FROM athletes 
GROUP BY canonical_name, gym_id 
HAVING COUNT(*) > 1;

# Check for duplicate scores
SELECT meet_id, athlete_id, event, score, COUNT(*) 
FROM scores 
GROUP BY meet_id, athlete_id, event, score 
HAVING COUNT(*) > 1;
```

All of these should return zero rows if duplicate prevention is working correctly.
