# Manual Upload File Format Guide

This document describes the recommended format for manually uploading meet data to ensure accurate athlete, gym, meet, score, and placement matching.

## File Format Options

### Option 1: CSV Format (Recommended)
Easiest to create from spreadsheets. One row per athlete with all their scores.

### Option 2: JSON Format
More structured, better for programmatic creation.

---

## CSV Format Specification

### Required Columns

| Column Name | Description | Example | Notes |
|------------|-------------|---------|-------|
| `meet_id` | Unique meet identifier | `MSO-35397` or `2026-IN-STATE` | **Must match existing meet in database** |
| `athlete_name` | Full athlete name | `Jane Smith` or `Smith, Jane` | Will be normalized (handles "Last, First" format) |
| `gym` | Gym name | `The Flip Zone` or `TFZ` | Will be normalized to canonical name (e.g., "TFZ" → "The Flip Zone") |
| `level` | Competition level | `6` or `Level 6` or `Xcel Gold` | Will be normalized |
| `division` | Division (optional) | `Sr 1` or `Jr 3` | Optional but recommended |

### Score Columns (at least one required)

| Column Name | Description | Example | Notes |
|------------|-------------|---------|-------|
| `aa_score` | All-Around score | `38.625` | Optional but recommended |
| `aa_place` | All-Around placement | `1` or `3T` | Optional, handles ties (3T → 3) |
| `vault` or `vt` | Vault score | `9.550` | Optional |
| `vault_place` or `vt_place` | Vault placement | `2` | Optional |
| `bars` or `ub` | Bars score | `9.750` | Optional |
| `bars_place` or `ub_place` | Bars placement | `1` | Optional |
| `beam` or `bb` | Beam score | `9.600` | Optional |
| `beam_place` or `bb_place` | Beam placement | `1` | Optional |
| `floor` or `fx` | Floor score | `9.725` | Optional |
| `floor_place` or `fx_place` | Floor placement | `1` | Optional |

### Optional Columns

| Column Name | Description | Example |
|------------|-------------|---------|
| `session` | Session identifier | `A01` or `Session 1` |
| `source` | Data source | `manual` or `website` |

### CSV Example

```csv
meet_id,athlete_name,gym,level,division,aa_score,aa_place,vault,vault_place,bars,bars_place,beam,beam_place,floor,floor_place
MSO-35397,Jane Smith,The Flip Zone,6,Sr 1,38.625,1,9.550,2,9.750,1,9.600,1,9.725,1
MSO-35397,Mary Johnson,TFZ,6,Sr 1,37.900,2,9.400,3,9.500,2,9.200,3,8.800,2
MSO-35397,Smith, Jane,Integrity Athletics,7,Jr 3,36.500,5,9.000,,9.200,,9.100,,9.200,
```

**Notes:**
- Empty cells are allowed (athlete may not have competed in all events)
- Column names are case-insensitive
- Multiple event name formats accepted (e.g., `vault` or `vt`, `bars` or `ub`)

---

## JSON Format Specification

### Structure: Array of Athlete Records

Each record represents one athlete's performance at a meet.

### Required Fields

```json
{
  "meet_id": "MSO-35397",           // Required: Must match existing meet
  "athlete_name": "Jane Smith",     // Required: Will be normalized
  "gym": "The Flip Zone",           // Required: Will be normalized to canonical
  "level": "6",                      // Required: Will be normalized
  "division": "Sr 1"                 // Optional but recommended
}
```

### Score Fields (at least one required)

```json
{
  "aa_score": 38.625,                // Optional: All-Around score
  "aa_place": 1,                     // Optional: All-Around placement
  "vault": 9.550,                    // Optional: Vault score
  "vault_place": 2,                  // Optional: Vault placement
  "bars": 9.750,                     // Optional: Bars score
  "bars_place": 1,                   // Optional: Bars placement
  "beam": 9.600,                     // Optional: Beam score
  "beam_place": 1,                   // Optional: Beam placement
  "floor": 9.725,                    // Optional: Floor score
  "floor_place": 1                   // Optional: Floor placement
}
```

### Optional Fields

```json
{
  "session": "A01",                  // Optional: Session identifier
  "source": "manual"                 // Optional: Data source identifier
}
```

### JSON Example

```json
[
  {
    "meet_id": "MSO-35397",
    "athlete_name": "Jane Smith",
    "gym": "The Flip Zone",
    "level": "6",
    "division": "Sr 1",
    "aa_score": 38.625,
    "aa_place": 1,
    "vault": 9.550,
    "vault_place": 2,
    "bars": 9.750,
    "bars_place": 1,
    "beam": 9.600,
    "beam_place": 1,
    "floor": 9.725,
    "floor_place": 1
  },
  {
    "meet_id": "MSO-35397",
    "athlete_name": "Mary Johnson",
    "gym": "TFZ",
    "level": "6",
    "division": "Sr 1",
    "aa_score": 37.900,
    "aa_place": 2,
    "vault": 9.400,
    "vault_place": 3,
    "bars": 9.500,
    "bars_place": 2,
    "beam": 9.200,
    "beam_place": 3,
    "floor": 8.800,
    "floor_place": 2
  }
]
```

---

## Critical Matching Rules

### 1. Meet Matching
- **`meet_id` must exactly match** an existing meet in the database
- Format examples: `MSO-35397`, `2026-IN-STATE`, `MANUAL-2026-01`
- Check existing meets before uploading to ensure correct `meet_id`

### 2. Athlete Matching
- Athletes are matched by **name + gym combination**
- Same name at different gyms = different athletes ✅
- Same name at same gym = same athlete ✅
- Name variations are handled:
  - `Jane Smith` = `Smith, Jane` = `JANE SMITH`
  - `Jane A. Smith` is kept as-is (middle initial preserved)

### 3. Gym Matching
- Gyms are normalized to canonical names
- Known mappings:
  - `TFZ` → `The Flip Zone`
  - `flip zone` → `The Flip Zone`
  - `Integrity Athletics` → `Integrity Athletics`
- New gyms are created automatically if not found

### 4. Score Deduplication
- Duplicate scores are prevented using `record_hash`
- Hash is based on: `meet_id + athlete_name + event + score`
- Same athlete, same meet, same event, same score = duplicate (skipped)

### 5. Level Normalization
- Accepts: `6`, `Level 6`, `level 6`, `Xcel Gold`, `xcel gold`
- Normalized to: `6`, `xcel_gold`, etc.

---

## Best Practices

### ✅ DO:
1. **Verify meet_id exists** before uploading
2. **Use consistent gym names** (prefer canonical names like "The Flip Zone" over "TFZ")
3. **Include division** when available (helps with placement accuracy)
4. **Include placement data** when available (more valuable than scores alone)
5. **Use full athlete names** (first + last name)
6. **Include AA scores** when available (most important metric)

### ❌ DON'T:
1. Don't use abbreviations for gym names unless they're in the canonical mapping
2. Don't mix meet_ids in a single file (one meet per file recommended)
3. Don't include athletes who didn't compete (empty scores)
4. Don't use nicknames unless that's how the athlete is registered
5. Don't skip required fields (`meet_id`, `athlete_name`, `gym`, `level`)

---

## Data Validation

Before uploading, verify:

1. ✅ All `meet_id` values match existing meets
2. ✅ All athletes have at least one score (AA or individual event)
3. ✅ All scores are numeric (no text like "DNS" or "NS")
4. ✅ All placements are integers (or "3T" format for ties)
5. ✅ Gym names are consistent (check canonical mappings)
6. ✅ Level format is consistent

---

## Example: Minimal Valid Record

**Minimum required data:**
```csv
meet_id,athlete_name,gym,level,aa_score
MSO-35397,Jane Smith,The Flip Zone,6,38.625
```

**Recommended complete record:**
```csv
meet_id,athlete_name,gym,level,division,aa_score,aa_place,vault,vault_place,bars,bars_place,beam,beam_place,floor,floor_place
MSO-35397,Jane Smith,The Flip Zone,6,Sr 1,38.625,1,9.550,2,9.750,1,9.600,1,9.725,1
```

---

## Troubleshooting

### "Meet not found" error
- Check that `meet_id` exactly matches database
- Meet must exist before scores can be uploaded
- Create meet first if needed

### "Duplicate score" warning
- This is normal - duplicate scores are skipped
- Check if you're uploading the same data twice

### Athlete appears twice
- Check gym name consistency
- Same name + different gym = different athletes (correct)
- Same name + same gym = should be same athlete (check for typos)

### Gym name variations
- Add new mappings to `core/gym_normalizer.py` if needed
- Or use the canonical name directly in your file

---

## File Naming Convention

Recommended: `manual_upload_<meet_id>_<date>.csv` or `.json`

Example: `manual_upload_MSO-35397_2026-03-14.csv`
