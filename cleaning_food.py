import time
import requests
import pandas as pd
import csv

API_KEY = "NfyMaKQi3W7HOQMGcWVwnia0TykDYgzeQzR1Ymge"

url = "https://api.nal.usda.gov/fdc/v1/foods/search"

output_filename = "all_foods_with_nutrients.csv"
all_records = []
all_nutrient_names = set()

page_number = 1
page_size = 200

# Step 1: Fetch items across Foundation, SR Legacy, and Survey datasets
while True:
    payload = {
        "query": "",  # Blank query retrieves all foods in these types
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
        "pageSize": page_size,
        "pageNumber": page_number,
    }

    response = requests.post(
        url, params={"api_key": API_KEY}, json=payload
    )

    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        break

    data = response.json()
    foods = data.get("foods", [])

    if not foods:
        break

    for food in foods:
        # Extract base metadata
        record = {
            "fdc_id": str(food.get("fdcId", "")),
            "data_type": food.get("dataType", ""),
            "description": food.get("description", ""),
            "food_category_id": str(
                food.get("foodCategoryId") or food.get("foodCategory", "")
            ),
            "publication_date": food.get("publicationDate", ""),
        }

        # Extract nutrients directly into the same record dictionary
        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrientName") or nutrient.get("name")
            unit = nutrient.get("unitName")
            val = nutrient.get("value") or nutrient.get("amount")

            col_name = f"{name} ({unit})" if unit else name
            record[col_name] = val
            all_nutrient_names.add(col_name)

        all_records.append(record)

    print(
        f"Page {page_number}: Processed {len(foods)} foods (Total: {len(all_records)})"
    )

    total_pages = data.get("totalPages", 1)
    if page_number >= total_pages or len(foods) < page_size:
        break

    page_number += 1
    time.sleep(0.2)

# Step 2: Define complete CSV headers (Metadata + Sorted Nutrient Columns)
fieldnames = [
    "fdc_id",
    "data_type",
    "description",
    "food_category_id",
    "publication_date",
] + sorted(list(all_nutrient_names))

# Step 3: Write all records to CSV
with open(
    output_filename, mode="w", newline="", encoding="utf-8"
) as csv_file:
    writer = csv.DictWriter(
        csv_file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
    )
    writer.writeheader()

    for record in all_records:
        # Fill missing nutrient keys with empty strings or 0
        formatted_record = {
            col: record.get(col, "") for col in fieldnames
        }
        writer.writerow(formatted_record)

print(
    f"\nDone! Saved {len(all_records)} foods with {len(fieldnames)} total columns to '{output_filename}'."
)

import pandas as pd

# 1. Load raw CSV
df = pd.read_csv("all_foods_with_nutrients.csv")

# 2. Define the exact columns you want to keep and their clean names
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

# Filter for existing columns and rename them
available_cols = [col for col in column_mapping.keys() if col in df.columns]
clean_df = df[available_cols].rename(columns=column_mapping)

# 3. Clean up data types and missing values
nutrient_cols = [
    col
    for col in clean_df.columns
    if col
    not in [
        "fdc_id",
        "data_type",
        "description",
        "food_category_id",
        "publication_date",
    ]
]

# Fill missing nutrient values with 0
clean_df[nutrient_cols] = clean_df[nutrient_cols].fillna(0)

# Standardize description text (uppercase to Title Case, remove extra whitespace)
clean_df["description"] = (
    clean_df["description"].str.strip().str.title()
)

# 4. Save cleaned dataset
clean_df.to_csv("clean_usda_foods.csv", index=False)
print(f"Cleaned dataset shape: {clean_df.shape}")
print(clean_df.head())