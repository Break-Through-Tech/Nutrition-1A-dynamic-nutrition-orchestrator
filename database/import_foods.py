import csv
import os
from pathlib import Path
from datetime import date

import psycopg


# =====================================================
# 1. CONFIGURATION
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "cleanedData" / "clean_usda_foods.csv"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "nutrition_db"),
    "user": os.getenv("DB_USER", "nutrition_user"),
    "password": os.getenv(
        "DB_PASSWORD",
        "nutrition_dev_password"
    ),
}

COLUMNS = [
    "fdc_id",
    "data_type",
    "description",
    "food_category_id",
    "publication_date",
    "calories_kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugars_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
]

NUTRIENT_COLUMNS = COLUMNS[5:]


# =====================================================
# 2. DATA CONVERSION
# =====================================================

def parse_float(value):
    """Convert a CSV value to a float, preserving missing values."""
    if value is None or value.strip() == "":
        return None

    number = float(value)

    if number != number:  # Detect NaN
        return None

    return number


def parse_date(value):
    """Convert a date string to a Python date."""
    if not value or not value.strip():
        return None

    return date.fromisoformat(value)


def parse_row(row):
    """Convert a CSV row into values suitable for PostgreSQL."""
    return (
        int(row["fdc_id"]),
        row["data_type"] or None,
        row["description"],
        row["food_category_id"] or None,
        parse_date(row["publication_date"]),
        *[parse_float(row[column]) for column in NUTRIENT_COLUMNS],
    )


# =====================================================
# 3. IMPORT USDA RECORDS
# =====================================================

def import_foods():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Could not find USDA CSV: {CSV_PATH}"
        )

    insert_columns = ", ".join(COLUMNS)

    update_columns = [
        column for column in COLUMNS if column != "fdc_id"
    ]

    update_clause = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in update_columns
    )

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            # Temporary table prevents duplicate IDs during import.
            cur.execute("""
                CREATE TEMP TABLE foods_import
                (LIKE foods INCLUDING DEFAULTS)
                ON COMMIT DROP;
            """)

            with open(CSV_PATH, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)

                with cur.copy(
                    f"COPY foods_import ({insert_columns}) FROM STDIN"
                ) as copy:

                    count = 0

                    for row in reader:
                        copy.write_row(parse_row(row))
                        count += 1

            # Insert new foods and update existing records.
            cur.execute(f"""
                INSERT INTO foods ({insert_columns})
                SELECT {insert_columns}
                FROM foods_import
                ON CONFLICT (fdc_id)
                DO UPDATE SET {update_clause};
            """)

            print(f"Processed {count} USDA food records.")

            cur.execute("SELECT COUNT(*) FROM foods;")
            total = cur.fetchone()[0]

            print(f"Total records in foods table: {total}")


if __name__ == "__main__":
    import_foods()