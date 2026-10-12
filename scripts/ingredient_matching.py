
import re
import pandas as pd


# =========================================================
# 1. CONFIGURATION
# =========================================================

FOODS_PATH = "../cleanedData/clean_usda_foods.csv"

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

# These are starting thresholds, not calibrated probabilities.
MIN_MATCH_SCORE = 0.35
HIGH_CONFIDENCE_SCORE = 0.80
MEDIUM_CONFIDENCE_SCORE = 0.60


# =========================================================
# 2. TEXT NORMALIZATION
# =========================================================

STOP_WORDS = {
    "a", "an", "the", "and", "of", "with", "for",
    "to", "in", "on", "from", "about"
}

# Convert common alternate phrases to a consistent form.
ALIASES = {
    "without salt": "unsalted",
    "no salt": "unsalted",
    "extra-virgin": "extra virgin",
    "all-purpose": "all purpose",
}

# Words describing preparation that usually do not identify
# a different food. Preserve raw, cooked, salted, etc.
PREPARATION_WORDS = {
    "chopped", "diced", "minced", "sliced",
    "grated", "shredded", "cubed", "crushed",
    "finely", "roughly", "thinly", "thickly",
    "peeled", "halved", "quartered"
}

# Remove measurement words from ingredient names.
# Quantity and unit should ideally be stored separately.
MEASUREMENT_WORDS = {
    "g", "gram", "grams",
    "kg", "kilogram", "kilograms",
    "mg", "milligram", "milligrams",
    "ml", "milliliter", "milliliters",
    "tsp", "teaspoon", "teaspoons",
    "tbsp", "tablespoon", "tablespoons",
    "cup", "cups",
    "oz", "ounce", "ounces",
    "lb", "lbs", "pound", "pounds"
}


def normalize_text(text):
    """Normalize spelling and punctuation before tokenization."""

    text = str(text).lower()

    for phrase, replacement in ALIASES.items():
        text = text.replace(phrase, replacement)

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def tokenize(text, remove_preparation=False):
    """Convert text into a set of normalized keywords."""

    text = normalize_text(text)
    words = text.split()

    result = set()

    for word in words:
        if word in STOP_WORDS:
            continue

        if word in MEASUREMENT_WORDS:
            continue

        # Remove numbers such as quantities from ingredient names.
        if word.isdigit():
            continue

        if remove_preparation and word in PREPARATION_WORDS:
            continue

        result.add(word)

    return result


# =========================================================
# 3. LOAD AND PREPROCESS USDA DATA
# =========================================================

def load_foods(path=FOODS_PATH):
    """Load USDA data and precompute tokens for faster matching."""

    foods = pd.read_csv(path)

    required_columns = {"description", "fdc_id"}

    missing = required_columns - set(foods.columns)

    if missing:
        raise ValueError(
            f"USDA CSV is missing required columns: {missing}"
        )

    foods["description"] = (
        foods["description"].fillna("").astype(str)
    )

    foods["tokens"] = foods["description"].apply(tokenize)

    # Tokens with preparation words removed are useful for
    # finding a base food, such as chopped onion -> onion.
    foods["base_tokens"] = foods["description"].apply(
        lambda text: tokenize(text, remove_preparation=True)
    )

    return foods


# Load once when this module is imported.
foods = load_foods()


# =========================================================
# 4. MATCH SCORING
# =========================================================

# A requested descriptor should not match an incompatible food.
CONFLICTS = {
    "unsalted": {"salted"},
    "salted": {"unsalted"},
    "raw": {"cooked", "roasted", "fried", "boiled", "baked"},
    "cooked": {"raw"},
    "frozen": {"canned"},
    "boneless": {"bone", "bonein"},
    "skinless": {"skin"},
    "whole": {"skim", "nonfat"},
    "skim": {"whole"},
    "nonfat": {"whole"},
}

# Important terms that should not be casually ignored.
IMPORTANT_DESCRIPTORS = {
    "raw", "cooked", "roasted", "fried", "boiled", "baked",
    "unsalted", "salted", "fresh", "frozen", "canned",
    "whole", "skim", "nonfat", "lowfat", "boneless",
    "skinless", "virgin", "smoked", "dried"
}


def score_candidate(ingredient_words, food_words):
    """
    Score one candidate from 0 to 1.

    The score measures text similarity, not the probability
    that the food is nutritionally correct.
    """

    if not ingredient_words or not food_words:
        return 0.0

    matching_words = ingredient_words & food_words

    # Fraction of requested words covered by the candidate.
    coverage = len(matching_words) / len(ingredient_words)

    # Prefer candidates whose words are more focused on the
    # requested ingredient rather than a long generic description.
    specificity = len(matching_words) / len(food_words)

    score = 0.85 * coverage + 0.15 * specificity

    # Penalize contradictory descriptors.
    for word in ingredient_words:
        incompatible_words = CONFLICTS.get(word, set())

        if food_words & incompatible_words:
            score -= 0.50

    # If the recipe specifies a meaningful descriptor, penalize
    # candidates that do not contain it.
    missing_important = (
        ingredient_words & IMPORTANT_DESCRIPTORS
    ) - food_words

    score -= 0.20 * len(missing_important)

    return max(0.0, min(score, 1.0))


def find_top_matches(ingredient_name, foods_df=None, top_n=5):
    """
    Return the highest-ranked USDA candidates.

    Each result contains:
        description, fdc_id, score, matched_words
    """

    if foods_df is None:
        foods_df = foods

    ingredient_words = tokenize(ingredient_name)

    if not ingredient_words:
        return []

    candidates = []

    for index, food in foods_df.iterrows():

        food_words = food["tokens"]

        score = score_candidate(
            ingredient_words,
            food_words
        )

        if score > 0:
            candidates.append({
                "index": index,
                "score": score,
                "matched_words": sorted(
                    ingredient_words & food_words
                ),
                "description": food["description"],
                "fdc_id": food["fdc_id"],
            })

    candidates.sort(
        key=lambda candidate: candidate["score"],
        reverse=True
    )

    return candidates[:top_n]


def find_best_food(ingredient_name, foods_df=None):
    """
    Return the best USDA match and its score.

    Returns:
        (food row, score), or (None, 0)
    """

    if foods_df is None:
        foods_df = foods

    candidates = find_top_matches(
        ingredient_name,
        foods_df,
        top_n=1
    )

    if not candidates:
        return None, 0.0

    best = candidates[0]

    if best["score"] < MIN_MATCH_SCORE:
        return None, best["score"]

    return foods_df.loc[best["index"]], best["score"]


def confidence_label(score):
    """Label a match score for reporting."""

    if score >= HIGH_CONFIDENCE_SCORE:
        return "high"

    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "medium"

    if score >= MIN_MATCH_SCORE:
        return "low"

    return "very_low"


# =========================================================
# 5. QUANTITY CONVERSION
# =========================================================

# Approximate grams per US cup for selected ingredients.
# Extend this dictionary as your project needs grow.
#
# Values are estimates. Actual weights depend on preparation,
# packing, and the particular ingredient.

GRAMS_PER_CUP = {
    "all purpose flour": 120,
    "bread flour": 127,
    "whole wheat flour": 120,
    "granulated sugar": 200,
    "brown sugar": 220,
    "powdered sugar": 120,
    "butter": 227,
    "unsalted butter": 227,
    "olive oil": 216,
    "vegetable oil": 218,
    "honey": 340,
    "water": 240,
    "milk": 245,
    "rolled oats": 90,
    "cooked rice": 158,
    "white rice cooked": 158,
}

# Approximate weights for common individual items.
# These should be refined using your USDA data and recipe needs.
GRAMS_PER_ITEM = {
    "egg": 50,
    "large egg": 50,
    "medium egg": 44,
    "small egg": 38,
    "garlic clove": 3,
    "clove garlic": 3,
}


def get_conversion_key(ingredient_name):
    """Create a normalized phrase for conversion lookups."""

    return normalize_text(ingredient_name)


def lookup_conversion_value(name, conversion_table):
    """Find a conversion entry contained in the ingredient name."""

    normalized = get_conversion_key(name)

    # Prefer the longest matching key to avoid choosing a generic
    # entry when a more specific entry is available.
    keys = sorted(
        conversion_table.keys(),
        key=len,
        reverse=True
    )

    for key in keys:
        if key in normalized:
            return conversion_table[key]

    return None


def convert_to_grams(ingredient, food=None):
    """
    Convert an ingredient quantity to grams.

    Supports:
        Weight: g, kg, mg, oz, lb
        Volume: ml, tsp, tbsp, cup(s), with known density
        Count: selected items using estimated weights

    Returns None when a reliable conversion is unavailable.
    """

    quantity = ingredient.get("quantity")
    unit = ingredient.get("unit")

    if quantity is None or unit is None:
        return None

    try:
        quantity = float(quantity)
    except (ValueError, TypeError):
        return None

    if quantity < 0:
        return None

    unit = str(unit).strip().lower()

    # Normalize common unit spellings.
    unit_aliases = {
        "grams": "g",
        "gram": "g",
        "kilograms": "kg",
        "kilogram": "kg",
        "milligrams": "mg",
        "milligram": "mg",
        "ounces": "oz",
        "ounce": "oz",
        "pounds": "lb",
        "pound": "lb",
        "lbs": "lb",
        "teaspoon": "tsp",
        "teaspoons": "tsp",
        "tablespoon": "tbsp",
        "tablespoons": "tbsp",
        "cups": "cup",
        "milliliter": "ml",
        "milliliters": "ml",
    }

    unit = unit_aliases.get(unit, unit)

    # Direct weight conversions.
    weight_factors = {
        "g": 1,
        "kg": 1000,
        "mg": 0.001,
        "oz": 28.3495,
        "lb": 453.592,
    }

    if unit in weight_factors:
        return quantity * weight_factors[unit]

    # Use the matched USDA description when available.
    food_description = (
        food["description"]
        if food is not None
        else ""
    )

    ingredient_name = ingredient.get("name", "")
    combined_name = f"{ingredient_name} {food_description}"

    grams_per_cup = lookup_conversion_value(
        combined_name,
        GRAMS_PER_CUP
    )

    # Volume conversions require ingredient-specific density.
    if unit in {"cup", "tbsp", "tsp", "ml"}:

        if grams_per_cup is None:
            return None

        volume_factors = {
            "cup": 1,
            "tbsp": 1 / 16,
            "tsp": 1 / 48,
            "ml": 1 / 240,
        }

        return (
            quantity
            * volume_factors[unit]
            * grams_per_cup
        )

    # Count-based conversions.
    if unit in {
        "piece", "pieces", "item", "items",
        "egg", "eggs", "clove", "cloves"
    }:

        grams_per_item = lookup_conversion_value(
            combined_name,
            GRAMS_PER_ITEM
        )

        if grams_per_item is None:
            return None

        return quantity * grams_per_item

    # Serving sizes, scoops, slices, and size descriptors need
    # additional information to determine their weight.
    return None


# =========================================================
# 6. CALCULATE RECIPE MACROS
# =========================================================

def calculate_recipe_macros(recipe, foods_df=None):
    """
    Calculate total nutrition for a recipe.

    USDA nutrient values are assumed to be per 100 g.

    Returns:
        totals
        ingredient_results
    """

    if foods_df is None:
        foods_df = foods

    totals = {nutrient: 0.0 for nutrient in NUTRIENTS}
    ingredient_results = []

    for ingredient in recipe.get("ingredients", []):

        name = ingredient.get("name", "")
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit")

        # Match first so the matched food can help with
        # ingredient-specific volume or count conversions.
        food, score = find_best_food(name, foods_df)

        if food is None:

            ingredient_results.append({
                "ingredient": name,
                "quantity": quantity,
                "unit": unit,
                "amount_g": None,
                "fdc_id": None,
                "matched_food": None,
                "match_score": score,
                "confidence": confidence_label(score),
                "status": "no_food_match",
            })

            continue

        # Convert the quantity using the ingredient and match.
        amount_g = convert_to_grams(ingredient, food)

        if amount_g is None:

            ingredient_results.append({
                "ingredient": name,
                "quantity": quantity,
                "unit": unit,
                "amount_g": None,
                "fdc_id": food["fdc_id"],
                "matched_food": food["description"],
                "match_score": score,
                "confidence": confidence_label(score),
                "status": "needs_conversion",
            })

            continue

        # A low-confidence match should not silently affect totals.
        if score < MEDIUM_CONFIDENCE_SCORE:

            ingredient_results.append({
                "ingredient": name,
                "quantity": quantity,
                "unit": unit,
                "amount_g": amount_g,
                "fdc_id": food["fdc_id"],
                "matched_food": food["description"],
                "match_score": score,
                "confidence": confidence_label(score),
                "status": "needs_match_review",
            })

            continue

        # USDA values are per 100 g.
        multiplier = amount_g / 100

        for nutrient in NUTRIENTS:

            # Missing nutrient columns are treated as unavailable,
            # not as evidence that the food contains zero nutrients.
            if nutrient not in foods_df.columns:
                continue

            value = food[nutrient]

            if pd.isna(value):
                continue

            totals[nutrient] += float(value) * multiplier

        ingredient_results.append({
            "ingredient": name,
            "quantity": quantity,
            "unit": unit,
            "amount_g": amount_g,
            "fdc_id": food["fdc_id"],
            "matched_food": food["description"],
            "match_score": score,
            "confidence": confidence_label(score),
            "status": "matched",
        })

    return totals, ingredient_results


# =========================================================
# 7. OPTIONAL DEBUGGING HELPER
# =========================================================

def print_top_matches(ingredient_name, foods_df=None, top_n=5):
    """Print candidate matches to help evaluate the matcher."""

    candidates = find_top_matches(
        ingredient_name,
        foods_df=foods_df,
        top_n=top_n
    )

    print(f"\nIngredient: {ingredient_name}")

    if not candidates:
        print("No candidates found.")
        return

    for rank, candidate in enumerate(candidates, start=1):
        print(
            f"{rank}. {candidate['description']} "
            f"| Score: {candidate['score']:.3f} "
            f"| Matched: {candidate['matched_words']}"
        )


# =========================================================
# 8. EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":

    # Inspect candidates before trusting a match.
    print_top_matches("unsalted butter")
    print_top_matches("extra virgin olive oil")
    print_top_matches("chopped onion")

    example_recipe = {
        "ingredients": [
            {
                "name": "unsalted butter",
                "quantity": 2,
                "unit": "tbsp"
            },
            {
                "name": "all purpose flour",
                "quantity": 1,
                "unit": "cup"
            },
            {
                "name": "egg",
                "quantity": 2,
                "unit": "eggs"
            }
        ]
    }

    totals, ingredient_results = calculate_recipe_macros(
        example_recipe
    )

    print("\nRecipe totals:")

    for nutrient, value in totals.items():
        print(f"{nutrient}: {value:.2f}")

    print("\nIngredient results:")

    for result in ingredient_results:
        print(result)
