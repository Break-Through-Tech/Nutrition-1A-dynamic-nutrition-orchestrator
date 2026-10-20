
import re
from pathlib import Path

import pandas as pd


# =========================================================
# 1. CONFIGURATION
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
    "extract", "juice", "oil", "sauce", "paste",
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
            foods[nutrient] = 0.0

        foods[nutrient] = pd.to_numeric(
            foods[nutrient], errors="coerce"
        ).fillna(0.0)

    foods["tokens"] = foods["description"].apply(tokenize)

    foods["base_tokens"] = foods["description"].apply(
        lambda value: tokenize(value, remove_preparation=True)
    )

    return foods


# =========================================================
# 4. INGREDIENT MATCHING
# =========================================================




def score_candidate(ingredient_words, food_words, description=""):
    """Rank foods by primary identity, requested form, and relevance."""

    if not ingredient_words or not food_words:
        return 0.0

    description = normalize_text(description)
    description_words = tokenize(description)
    matching_words = ingredient_words & food_words

    if not matching_words:
        return 0.0

    # Reward matching all requested ingredient words.
    coverage = len(matching_words) / len(ingredient_words)
    score = 0.45 * coverage

    # USDA descriptions often put the main food before the first comma.
    parts = description.split(",")
    primary_words = tokenize(parts[0]) if parts else set()

    if ingredient_words <= primary_words:
        score += 0.45
    elif primary_words & ingredient_words:
        score += 0.20
    else:
        # The ingredient appears only in a secondary description.
        score -= 0.20

    # Penalize unrequested forms such as powder, juice, or extract.
    unwanted_forms = (
        description_words & FORM_QUALIFIERS
    ) - ingredient_words
    score -= min(0.20, 0.08 * len(unwanted_forms))

    # Penalize prepared products that contain, rather than represent,
    # the requested ingredient.
    unwanted_products = (
        description_words & PREPARED_PRODUCT_TERMS
    ) - ingredient_words
    score -= min(0.45, 0.30 * len(unwanted_products))

    # Prefer ordinary raw, whole ingredients when no form was specified.
    requested_form = ingredient_words & FORM_QUALIFIERS

    if not requested_form:
        if "whole" in description_words:
            score += 0.03
        if "raw" in description_words:
            score += 0.03

    return max(0.0, min(score, 1.0))


def find_top_matches(ingredient_name, foods, top_n=10):
    """Return the highest-scoring USDA candidates for an ingredient."""

    ingredient_words = tokenize(
        ingredient_name,
        remove_preparation=True,
    )

    if not ingredient_words:
        return []

    candidates = []

    for _, food in foods.iterrows():
        food_words = food["tokens"]
        description = food["description"]

        score = score_candidate(
            ingredient_words,
            food_words,
            description,
        )

        if score <= 0:
            continue

        matched_words = ingredient_words & food_words

        candidates.append({
            "fdc_id": food["fdc_id"],
            "description": description,
            "score": score,
            "matched_words": sorted(matched_words),
            "nutrients": {
                nutrient: float(food[nutrient])
                for nutrient in NUTRIENTS
            },
        })

    candidates.sort(
        key=lambda candidate: candidate["score"],
        reverse=True,
    )

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
    """
    Calculate recipe macros from ingredient dictionaries.

    Each ingredient should look like:
        {
            "name": "unsalted butter",
            "quantity": 2,
            "unit": "tbsp"
        }

    Returns:
        totals, ingredient_results

    Nutrient values are assumed to be per 100 grams in the USDA CSV.
    """

    if foods is None:
        foods = load_foods()

    totals = {nutrient: 0.0 for nutrient in NUTRIENTS}
    ingredient_results = []

    for ingredient in recipe:
        name = ingredient.get("name", "")
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit", "")

        result = {
            "ingredient": name,
            "quantity": quantity,
            "unit": unit,
            "grams": None,
            "matched_food": None,
            "match_score": None,
            "confidence": "Very low",
            "status": "",
            "nutrients": {},
        }

        if not name:
            result["status"] = "Skipped: missing ingredient name"
            ingredient_results.append(result)
            continue

        grams = convert_to_grams(quantity, unit, name)

        if grams is None:
            result["status"] = (
                "Skipped: unsupported unit or unknown conversion"
            )
            ingredient_results.append(result)
            continue

        result["grams"] = grams

        match = find_best_food(name, foods)

        if match is None:
            result["status"] = "Skipped: no suitable match found"
            ingredient_results.append(result)
            continue

        score = match["score"]
        result["matched_food"] = match["description"]
        result["match_score"] = score
        result["confidence"] = confidence_label(score)

        # Low-confidence matches are reported but not included in totals.
        if score < MEDIUM_CONFIDENCE_SCORE:
            result["status"] = (
                "Skipped: match confidence is too low for calculation"
            )
            ingredient_results.append(result)
            continue

        ingredient_nutrients = {}

        for nutrient in NUTRIENTS:
            value_per_100g = match["nutrients"].get(nutrient, 0.0)
            amount = value_per_100g * grams / 100.0

            ingredient_nutrients[nutrient] = amount
            totals[nutrient] += amount

        result["nutrients"] = ingredient_nutrients
        result["status"] = "Included"
        ingredient_results.append(result)

    return totals, ingredient_results

#Function to connect to the nutrition engine and send fdc_ids to calculator
def get_recipe_fdc_ids(recipe, foods=None):
    """Return a list of USDA FDC IDs for ingredients in a recipe."""

    if foods is None:
        foods = load_foods()

    fdc_ids = []

    for ingredient in recipe:
        name = ingredient.get("name", "")

        if not name:
            continue

        match = find_best_food(name, foods)

        if match is not None:
            fdc_ids.append(match["fdc_id"])

    return fdc_ids


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
