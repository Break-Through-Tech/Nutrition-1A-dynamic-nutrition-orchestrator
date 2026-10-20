"""Ingredient-name matching and legacy quantity conversion helpers.

The end-to-end prototype uses this module to suggest USDA food records and
reuse the project's existing household-measure tables. A match is only a
suggestion: preparation state, product type, and quantity conversions still
need review before a nutrition result can be treated as verified.
"""


import re
from pathlib import Path

import pandas as pd


# =========================================================
# 1. CONFIGURATION
# Dataset paths, nutrient fields, match thresholds, and conversion tables live here.
# =========================================================

FOODS_PATH = (
    Path(__file__).resolve().parent.parent
    / "cleanedData"
    / "clean_usda_foods.csv"
)

NUTRIENTS = [
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

MIN_MATCH_SCORE = 0.35
HIGH_CONFIDENCE_SCORE = 0.80
MEDIUM_CONFIDENCE_SCORE = 0.60
AMBIGUOUS_GENERIC_INGREDIENTS = {"oil", "milk", "rice", "cheese", "yogurt"}


# Words that usually do not help identify the ingredient.
STOP_WORDS = {
    "a", "an", "the", "and", "of", "with", "for",
    "to", "in", "on", "from", "about",
}

# Preparation instructions are usually irrelevant to food identity.
PREPARATION_WORDS = {
    "chopped", "diced", "minced", "sliced", "grated",
    "shredded", "cubed", "crushed", "finely", "roughly",
    "thinly", "thickly", "peeled", "halved", "quartered",
}

# Descriptors that can indicate a different form of an ingredient.
FORM_QUALIFIERS = {
    "dried", "dehydrated", "powder", "powdered",
    "white", "yolk", "pickled", "smoked", "salted",
    "unsalted", "frozen", "canned", "concentrated",
    "extract", "juice", "oil", "sauce", "paste", "cooked", "boiled",
    "fried", "roasted", "baked", "prepared", "flavored", "buttermilk",
    "cultured", "chocolate", "almond", "babyfood", "wild", "added",
}

# Common words that indicate a prepared product rather than
# a basic ingredient. Singular and plural forms are included.
PREPARED_PRODUCT_TERMS = {
    "bread", "bagel", "sandwich", "burrito", "quesadilla",
    "taquito", "pizza", "salad", "soup", "dip",
    "casserole", "stuffing", "noodle", "pasta", "cracker",
    "chip", "ring", "burger", "sushi", "benedict",
    "deviled", "omelet", "omelette", "pancake", "waffle",
    "cookie", "cake", "pie", "pastry", "muffin",
    "snack", "gravy", "dressing", "spread", "topping",
    "candy", "dessert", "custard",
}

# Basic unit conversions.
# Volume-to-weight conversions depend on the ingredient.
GRAMS_PER_UNIT = {
    "kg": 1000.0,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
}

GRAMS_PER_CUP = {
    "all purpose flour": 120.0,
    "flour": 120.0,
    "whole wheat flour": 120.0,
    "granulated sugar": 200.0,
    "sugar": 200.0,
    "brown sugar": 220.0,
    "powdered sugar": 120.0,
    "butter": 227.0,
    "unsalted butter": 227.0,
    "salted butter": 227.0,
    "water": 240.0,
    "milk": 244.0,
    "whole milk": 244.0,
    "honey": 340.0,
    "olive oil": 216.0,
    "vegetable oil": 218.0,
    "rolled oats": 90.0,
    "oats": 90.0,
    "rice": 185.0,
    "white rice": 185.0,
    "chopped onion": 160.0,
    "onion": 160.0,
    "chopped tomato": 180.0,
    "tomato": 180.0,
    "shredded cheese": 113.0,
    "cheese": 113.0,
    "peanut butter": 258.0,
}

GRAMS_PER_ITEM = {
    "egg": 50.0,
    "large egg": 50.0,
    "medium egg": 44.0,
    "small egg": 38.0,
    "onion": 150.0,
    "garlic clove": 3.0,
    "clove garlic": 3.0,
    "tomato": 123.0,
    "medium tomato": 123.0,
    "lemon": 58.0,
    "lime": 67.0,
    "apple": 182.0,
    "banana": 118.0,
    "carrot": 61.0,
    "potato": 173.0,
    "slice bread": 30.0,
    "bread slice": 30.0,
}


# =========================================================
# 2. TEXT NORMALIZATION
# These helpers make spelling and preparation wording comparable before scoring.
# =========================================================

def normalize_text(text):
    """Lowercase text and normalize common ingredient wording."""

    if pd.isna(text):
        return ""

    text = str(text).lower().strip()

    # Normalize common wording without equating different foods.
    replacements = {
        "all-purpose": "all purpose",
        "self-rising": "self rising",
        "extra-virgin": "extra virgin",
        "tbsps": "tbsp",
        "tablespoons": "tbsp",
        "tablespoon": "tbsp",
        "teaspoons": "tsp",
        "teaspoon": "tsp",
        "cups": "cup",
        "ounces": "ounce",
        "pounds": "pound",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove punctuation while retaining letters and numbers.
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_word(word):
    """Apply conservative singularization for common plural words."""

    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"

    if (
        len(word) > 4
        and word.endswith("s")
        and not word.endswith(("ss", "us", "is"))
    ):
        return word[:-1]

    return word


def tokenize(text, remove_preparation=False):
    """Convert text to normalized ingredient keywords."""

    text = normalize_text(text)
    words = text.split()

    result = set()

    for word in words:
        word = normalize_word(word)

        if word in STOP_WORDS:
            continue

        if word in {"g", "kg", "mg", "ml", "cup", "tsp", "tbsp"}:
            continue

        if remove_preparation and word in PREPARATION_WORDS:
            continue

        result.add(word)

    return result


# =========================================================
# 3. LOAD USDA FOOD DATA
# =========================================================

def load_foods(path=FOODS_PATH):
    """Load USDA foods and precompute searchable word sets."""

    foods = pd.read_csv(path)

    required_columns = {"fdc_id", "description"}
    missing = required_columns - set(foods.columns)

    if missing:
        raise ValueError(
            f"The USDA CSV is missing required columns: {sorted(missing)}"
        )

    foods["description"] = foods["description"].fillna("").astype(str)

    for nutrient in NUTRIENTS:
        if nutrient not in foods.columns:
            foods[nutrient] = float("nan")

        # Preserve unknown nutrient values as NaN. Replacing missing values
        # with zero makes an unknown amount look like a measured zero.
        foods[nutrient] = pd.to_numeric(foods[nutrient], errors="coerce")

    foods["tokens"] = foods["description"].apply(tokenize)
    foods["base_tokens"] = foods["description"].apply(
        lambda value: tokenize(value, remove_preparation=True)
    )
    foods["description_segments"] = foods["description"].apply(
        lambda value: [tokenize(part) for part in str(value).split(",")]
    )

    return foods


# =========================================================
# 4. INGREDIENT MATCHING
# =========================================================




def score_candidate(ingredient_words, food_words, description="", description_segments=None):
    """Rank candidates conservatively to avoid matching generic words anywhere.

    A single-word query such as "salt" must match the food's primary name or
    an exact second segment ("Nuts, Almonds"), not a prepared food that merely
    mentions salt/almonds as an ingredient.
    """
    if not ingredient_words or not food_words:
        return 0.0

    if description_segments is None:
        description_segments = [tokenize(part) for part in str(description).split(",")]
    primary_words = description_segments[0] if description_segments else set()
    matched_words = ingredient_words & food_words
    coverage = len(matched_words) / len(ingredient_words)
    if coverage < 1.0:
        return max(0.0, min(0.35 * coverage, 1.0))

    if len(ingredient_words) == 1:
        if primary_words == ingredient_words:
            score = 0.95
        elif len(description_segments) > 1 and description_segments[1] == ingredient_words:
            score = 0.82
        else:
            return 0.0
    else:
        # A query must start with the candidate's primary food identity or
        # vice versa; this rejects e.g. "brown rice" -> "Beans And Brown Rice".
        if ingredient_words <= primary_words and primary_words <= ingredient_words:
            score = 0.96
        elif ingredient_words <= set().union(*description_segments[:3]) and primary_words <= ingredient_words:
            score = 0.86
        else:
            return 0.0

    unwanted_forms = (food_words & FORM_QUALIFIERS) - ingredient_words
    score -= min(0.18, 0.06 * len(unwanted_forms))
    unwanted_products = (food_words & PREPARED_PRODUCT_TERMS) - ingredient_words
    score -= min(0.40, 0.25 * len(unwanted_products))
    return max(0.0, min(score, 1.0))


def find_top_matches(ingredient_name, foods, top_n=10):
    """Return highest-scoring USDA candidates using precomputed tokens."""
    ingredient_words = tokenize(ingredient_name, remove_preparation=True)
    if not ingredient_words:
        return []
    if len(ingredient_words) == 1 and next(iter(ingredient_words)) in AMBIGUOUS_GENERIC_INGREDIENTS:
        # These labels cover materially different foods; do not silently pick
        # a random type (e.g. almond oil for unspecified cooking oil).
        return []

    columns = {name: foods.columns.get_loc(name) for name in
               ("fdc_id", "description", "tokens", "description_segments", *NUTRIENTS)}
    candidates = []

    # itertuples avoids the large overhead of DataFrame.iterrows; tokenization
    # is done once in load_foods rather than once per candidate per query.
    for row in foods.itertuples(index=False, name=None):
        description = row[columns["description"]]
        food_words = row[columns["tokens"]]
        score = score_candidate(
            ingredient_words, food_words, description,
            row[columns["description_segments"]],
        )
        if score <= 0:
            continue

        matched_words = ingredient_words & food_words
        nutrients = {}
        for nutrient in NUTRIENTS:
            value = row[columns[nutrient]]
            nutrients[nutrient] = None if pd.isna(value) else float(value)

        candidates.append({
            "fdc_id": str(row[columns["fdc_id"]]),
            "description": description,
            "score": score,
            "matched_words": sorted(matched_words),
            "nutrients": nutrients,
        })

    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
    return candidates[:top_n]


def find_best_food(ingredient_name, foods):
    """Return the best match, or None if the match is too weak."""

    matches = find_top_matches(ingredient_name, foods, top_n=1)

    if not matches:
        return None

    best = matches[0]

    if best["score"] < MIN_MATCH_SCORE:
        return None

    return best


def confidence_label(score):
    """Convert a match score to a readable confidence label."""

    if score >= HIGH_CONFIDENCE_SCORE:
        return "High"

    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "Medium"

    if score >= MIN_MATCH_SCORE:
        return "Low"

    return "Very low"


def print_top_matches(ingredient_name, top_n=10, foods=None):
    """Print ranked candidate foods for debugging."""

    if foods is None:
        foods = load_foods()

    matches = find_top_matches(ingredient_name, foods, top_n)

    print(f"\nIngredient: {ingredient_name}")

    if not matches:
        print("No matching foods found.")
        return

    for index, match in enumerate(matches, start=1):
        print(
            f"{index}. {match['description']} | "
            f"Score: {match['score']:.3f} | "
            f"Matched: {match['matched_words']}"
        )


# =========================================================
# 5. UNIT CONVERSION
# =========================================================

def grams_per_cup_for(ingredient_name):
    """Find a known cup-to-gram conversion for an ingredient."""

    words = tokenize(ingredient_name)
    normalized_name = normalize_text(ingredient_name)

    # Prefer the most specific matching name.
    for name in sorted(GRAMS_PER_CUP, key=len, reverse=True):
        if name in normalized_name:
            return GRAMS_PER_CUP[name]

    # Fall back to a keyword match for simple ingredient names.
    for name, grams in GRAMS_PER_CUP.items():
        if tokenize(name) == words:
            return grams

    return None


def grams_per_item_for(ingredient_name):
    """Find a known weight for one item of an ingredient."""

    normalized_name = normalize_text(ingredient_name)

    for name in sorted(GRAMS_PER_ITEM, key=len, reverse=True):
        if name in normalized_name:
            return GRAMS_PER_ITEM[name]

    return None


def convert_to_grams(quantity, unit, ingredient_name=""):
    """
    Convert a quantity to grams when a reliable conversion is known.

    Returns None for unsupported units or unknown volume densities.
    """

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return None

    if quantity < 0:
        return None

    unit = normalize_text(unit)

    unit_aliases = {
        "gram": "g",
        "grams": "g",
        "kilogram": "kg",
        "kilograms": "kg",
        "milligram": "mg",
        "milligrams": "mg",
        "teaspoon": "tsp",
        "teaspoons": "tsp",
        "tablespoon": "tbsp",
        "tablespoons": "tbsp",
        "cups": "cup",
        "milliliter": "ml",
        "milliliters": "ml",
        "liters": "l",
        "liter": "l",
        "ounce": "oz",
        "ounces": "oz",
        "pound": "lb",
        "pounds": "lb",
    }

    unit = unit_aliases.get(unit, unit)

    # Direct weight conversions.
    if unit in GRAMS_PER_UNIT:
        return quantity * GRAMS_PER_UNIT[unit]

    if unit == "oz":
        return quantity * 28.349523125

    if unit == "lb":
        return quantity * 453.59237

    # Volume conversions.
    if unit in {"cup", "tbsp", "tsp", "ml", "l"}:
        grams_per_cup = grams_per_cup_for(ingredient_name)

        if grams_per_cup is None:
            return None

        if unit == "cup":
            return quantity * grams_per_cup

        if unit == "tbsp":
            return quantity * grams_per_cup / 16.0

        if unit == "tsp":
            return quantity * grams_per_cup / 48.0

        if unit == "ml":
            return quantity * grams_per_cup / 240.0

        if unit == "l":
            return quantity * grams_per_cup * 1000.0 / 240.0

    # Count-based conversions.
    if unit in {
        "item", "items", "piece", "pieces",
        "whole", "egg", "eggs",
    }:
        grams_per_item = grams_per_item_for(ingredient_name)

        if grams_per_item is None:
            return None

        return quantity * grams_per_item

    # Do not silently guess weights for servings, slices, scoops, etc.
    return None


# =========================================================
# 6. RECIPE MACRO CALCULATION
# =========================================================

def calculate_recipe_macros(recipe, foods=None):
    """Calculate macros with conservative unknown handling (legacy interface).

    The newer integration path is ``python -m nutrition_engine.prototype``.
    This compatibility function remains for older callers, but any skipped
    ingredient or missing nutrient makes the affected recipe total unknown;
    missing values are never silently treated as zero.
    """
    if foods is None:
        foods = load_foods()

    totals = {nutrient: 0.0 for nutrient in NUTRIENTS}
    missing_nutrients = set()
    unresolved_contribution = False
    ingredient_results = []

    for ingredient in recipe:
        name = ingredient.get("name", "")
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit", "")
        result = {
            "ingredient": name, "quantity": quantity, "unit": unit,
            "grams": None, "matched_food": None, "match_score": None,
            "confidence": "Very low", "status": "", "nutrients": {},
        }

        if not name:
            result["status"] = "Skipped: missing ingredient name"
            unresolved_contribution = True
            ingredient_results.append(result)
            continue

        grams = convert_to_grams(quantity, unit, name)
        if grams is None:
            result["status"] = "Skipped: unsupported unit or unknown conversion"
            unresolved_contribution = True
            ingredient_results.append(result)
            continue
        result["grams"] = grams

        match = find_best_food(name, foods)
        if match is None:
            result["status"] = "Skipped: no suitable match found"
            unresolved_contribution = True
            ingredient_results.append(result)
            continue

        score = match["score"]
        result["matched_food"] = match["description"]
        result["match_score"] = score
        result["confidence"] = confidence_label(score)
        if score < MEDIUM_CONFIDENCE_SCORE:
            result["status"] = "Skipped: match confidence is too low for calculation"
            unresolved_contribution = True
            ingredient_results.append(result)
            continue

        ingredient_nutrients = {}
        for nutrient in NUTRIENTS:
            value_per_100g = match["nutrients"].get(nutrient)
            if value_per_100g is None:
                ingredient_nutrients[nutrient] = None
                missing_nutrients.add(nutrient)
            else:
                amount = value_per_100g * grams / 100.0
                ingredient_nutrients[nutrient] = amount
                totals[nutrient] += amount
        result["nutrients"] = ingredient_nutrients
        result["status"] = "Included" if not any(v is None for v in ingredient_nutrients.values()) else "Included with missing nutrient data"
        ingredient_results.append(result)

    for nutrient in NUTRIENTS:
        if unresolved_contribution or nutrient in missing_nutrients:
            totals[nutrient] = None
    return totals, ingredient_results


# =========================================================
# 7. EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":
    foods = load_foods()

    # Inspect the matcher.
    print_top_matches("egg", top_n=10, foods=foods)
    print_top_matches("onion", top_n=10, foods=foods)
    print_top_matches("unsalted butter", top_n=10, foods=foods)

    # Example recipe.
    recipe = [
        {"name": "unsalted butter", "quantity": 2, "unit": "tbsp"},
        {"name": "all purpose flour", "quantity": 1, "unit": "cup"},
        {"name": "egg", "quantity": 2, "unit": "item"},
    ]

    totals, ingredient_results = calculate_recipe_macros(
        recipe,
        foods,
    )

    print("\nRecipe ingredient results:")

    for result in ingredient_results:
        print(
            f"\n{result['ingredient']}: {result['status']}"
        )
        print(f"  Matched food: {result['matched_food']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Weight in grams: {result['grams']}")

    print("\nRecipe macro totals:")

    for nutrient, amount in totals.items():
        print(f"{nutrient}: {amount:.2f}")
