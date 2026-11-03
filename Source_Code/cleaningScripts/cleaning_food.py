import time
import json
import requests
import pandas as pd
import csv
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================================================
# 1. CONFIGURATION
# =========================================================

api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY is not set")

url = "https://api.nal.usda.gov/fdc/v1/foods/search"

output_filename = "all_foods_with_nutrients.csv"
cleaned_filename = "clean_usda_foods.csv"
checkpoint_filename = "usda_checkpoint.jsonl"

METADATA_COLUMNS = {
    "fdc_id",
    "data_type",
    "description",
    "food_category_id",
    "publication_date",
}

all_records = []
all_nutrient_names = set()

page_number = 1
page_size = 200

# Session that retries timeouts, dropped connections, and 429/5xx responses
# with exponential backoff. POST must be allowed explicitly; it is not
# retried by default.
session = requests.Session()
retry = Retry(
    total=6,
    connect=6,
    read=6,
    backoff_factor=2,  # waits roughly 2s, 4s, 8s, ...
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)
session.mount("https://", HTTPAdapter(max_retries=retry))

# =========================================================
# 2. RESUME FROM CHECKPOINT (if a previous run was interrupted)
# =========================================================

if os.path.exists(checkpoint_filename):
    with open(checkpoint_filename, "r", encoding="utf-8") as cp:
        for line in cp:
            line = line.strip()
            if not line:
                continue
            saved = json.loads(line)
            all_records.extend(saved["records"])
            page_number = saved["page"] + 1
    for record in all_records:
        all_nutrient_names.update(
            key for key in record if key not in METADATA_COLUMNS
        )
    print(
        f"Resuming from checkpoint: {len(all_records)} foods already saved, "
        f"continuing at page {page_number}."
    )

# =========================================================
# 3. FETCH USDA FOOD DATA
# =========================================================

while True:
    payload = {
        "query": "",
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
        "pageSize": page_size,
        "pageNumber": page_number,
    }

    response = session.post(
        url,
        params={"api_key": api_key},
        json=payload,
        timeout=(10, 60),  # (connect/handshake, read)
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"USDA API error {response.status_code}: {response.text}"
        )

    data = response.json()
    foods = data.get("foods", [])

    if not foods:
        break

    page_records = []

    for food in foods:
        record = {
            "fdc_id": str(food.get("fdcId", "")),
            "data_type": food.get("dataType", ""),
            "description": food.get("description", ""),
            "food_category_id": str(
                food.get("foodCategoryId")
                or food.get("foodCategory", "")
            ),
            "publication_date": food.get("publicationDate", ""),
        }

        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrientName") or nutrient.get("name")
            unit = nutrient.get("unitName")

            # Do not use "or" here because a valid value could be zero.
            value = nutrient.get("value")
            if value is None:
                value = nutrient.get("amount")

            if not name:
                continue

            column_name = f"{name} ({unit})" if unit else name
            record[column_name] = value
            all_nutrient_names.add(column_name)

        page_records.append(record)

    all_records.extend(page_records)

    # Save this page right away so a later failure doesn't lose it.
    with open(checkpoint_filename, "a", encoding="utf-8") as cp:
        cp.write(
            json.dumps({"page": page_number, "records": page_records}) + "\n"
        )

    print(
        f"Page {page_number}: Processed {len(foods)} foods "
        f"(Total: {len(all_records)})"
    )

    total_pages = data.get("totalPages", 1)

    if page_number >= total_pages or len(foods) < page_size:
        break

    page_number += 1
    time.sleep(0.5)

# =========================================================
# 4. SAVE RAW USDA DATA
# =========================================================

fieldnames = [
    "fdc_id",
    "data_type",
    "description",
    "food_category_id",
    "publication_date",
] + sorted(all_nutrient_names)

with open(output_filename, "w", newline="", encoding="utf-8") as csv_file:
    writer = csv.DictWriter(
        csv_file,
        fieldnames=fieldnames,
        quoting=csv.QUOTE_ALL,
    )
    writer.writeheader()

    for record in all_records:
        # Missing nutrients remain blank, not zero.
        writer.writerow({
            column: record.get(column, "")
            for column in fieldnames
        })

print(
    f"\nSaved {len(all_records)} foods with "
    f"{len(fieldnames)} columns to '{output_filename}'."
)

# Fetch finished and raw CSV is written, so the checkpoint is no longer needed.
if os.path.exists(checkpoint_filename):
    os.remove(checkpoint_filename)

# =========================================================
# 5. LOAD RAW CSV AND RENAME NUTRIENTS
# =========================================================

df = pd.read_csv(output_filename)

column_mapping = {
    "fdc_id": "fdc_id",
    "data_type": "data_type",
    "description": "description",
    "food_category_id": "food_category_id",
    "publication_date": "publication_date",
    "Energy (KCAL)": "calories_kcal",
    "Protein (G)": "protein_g",
    "Total lipid (fat) (G)": "fat_g",
    "Carbohydrate, by difference (G)": "carbs_g",
    "Fiber, total dietary (G)": "fiber_g",
    "Total Sugars (G)": "sugars_g",
    "Sodium, Na (MG)": "sodium_mg",
    "Potassium, K (MG)": "potassium_mg",
    "Calcium, Ca (MG)": "calcium_mg",
    "Iron, Fe (MG)": "iron_mg",
}

# Check for expected nutrient columns before selecting them.
required_nutrient_columns = [
    "Energy (KCAL)",
    "Protein (G)",
    "Total lipid (fat) (G)",
    "Carbohydrate, by difference (G)",
]

missing_required = [
    column
    for column in required_nutrient_columns
    if column not in df.columns
]

if missing_required:
    raise ValueError(
        "Expected USDA nutrient columns were not found: "
        f"{missing_required}\n"
        "Inspect the raw CSV headers and update column_mapping."
    )

available_columns = [
    column for column in column_mapping
    if column in df.columns
]

clean_df = df[available_columns].rename(columns=column_mapping)

# =========================================================
# 6. CLEAN DATA TYPES AND MISSING VALUES
# =========================================================

nutrient_columns = [
    column for column in clean_df.columns
    if column not in METADATA_COLUMNS
]

# Convert nutrient values to numbers without replacing missing
# values with zero. Invalid or missing values become NaN.
clean_df[nutrient_columns] = clean_df[nutrient_columns].apply(
    pd.to_numeric,
    errors="coerce",
)

clean_df["description"] = (
    clean_df["description"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.title()
)

# =========================================================
# 7. VALIDATE AND SAVE CLEANED DATA
# =========================================================

# Check for duplicate food IDs.
duplicate_count = clean_df["fdc_id"].duplicated().sum()

if duplicate_count:
    print(f"Warning: Found {duplicate_count} duplicate FDC IDs.")

clean_df.to_csv(cleaned_filename, index=False)

print(f"Cleaned dataset shape: {clean_df.shape}")
print(f"Saved cleaned data to '{cleaned_filename}'")

# Report missing nutrient values so they can be investigated.
print("\nMissing nutrient counts:")
print(clean_df[nutrient_columns].isna().sum())

# Inspect the butter record if it exists.
butter = clean_df[clean_df["fdc_id"].astype(str) == "789828"]

if not butter.empty:
    print("\nButter nutrient record:")
    print(
        butter[
            ["fdc_id", "description", "calories_kcal", "fat_g"]
        ].to_string(index=False)
    )