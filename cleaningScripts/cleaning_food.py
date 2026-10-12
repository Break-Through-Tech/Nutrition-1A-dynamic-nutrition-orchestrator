
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

# These are heuristic thresholds, not probabilities.
MIN_MATCH_SCORE = 0.35
REVIEW_MATCH_SCORE = 0.60
HIGH_MATCH_SCORE = 0.80

# Generic ingredients generally favor Foundation or SR Legacy.
# This is only a tie-breaker, not a substitute for a good match.
DATA_TYPE_PREFERENCE = {
    "foundation": 3,
    "sr legacy": 2,
    "survey (fndds)": 1,
}

STOP_WORDS = {
    "a", "an", "the", "and", "of", "with", "for",
    "to", "in", "on", "from"
}

# Normalize common alternate phrases.
ALIASES = {
    "extra-virgin": "extra virgin",
    "all-purpose": "all purpose",
    "without salt": "unsalted",
    "no salt": "unsalted",
}

# Words that usually describe preparation rather than identity.
PREPARATION_WORDS = {
    "chopped", "diced", "minced", "sliced", "grated",
    "shredded", "cubed", "crushed", "peeled",
    "halved", "quartered", "finely", "roughly",
    "thinly", "thickly"
}

# Important descriptors that may affect nutrition.
IMPORTANT_DESCRIPTORS = {
    "raw", "cooked", "roasted", "fried", "boiled",
    "baked", "unsalted", "salted", "fresh", "frozen",
    "canned", "whole", "skim", "nonfat", "boneless",
    "skinless", "virgin", "smoked", "dried"
}

# Conflicting descriptors should penalize a candidate.
CONFLICTS = {
    "unsalted": {"salted"},
    "salted": {"unsalted"},
    "raw": {"cooked", "roasted", "fried", "boiled", "baked"},
    "cooked": {"raw"},
    "fresh": {"frozen", "canned"},
    "frozen": {"fresh", "canned"},
    "canned": {"fresh", "frozen"},
    "boneless": {"bone", "bonein"},
    "skinless": {"skin"},
    "whole": {"skim", "nonfat"},
    "skim": {"whole"},
    "nonfat": {"whole"},
}


# =========================================================
# 2. TEXT NORMALIZATION
# =========================================================

def normalize_text(text):
    """Lowercase text, normalize aliases, and remove punctuation."""

    text = str(text).lower()

    for phrase, replacement in ALIASES.items():
        text = text.replace(phrase, replacement)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text, remove_preparation=False):
    """Convert text into normalized keyword sets."""

    words = normalize_text(text).split()
    tokens = set()

    for word in words:
        if word in STOP_WORDS:
            continue

        # Remove standalone numeric quantities.
        if word.isdigit():
            continue

        if remove_preparation and word in PREPARATION_WORDS:
            continue

        tokens.add(word)

    return tokens


# =========================================================
# 3. LOAD USDA DATA
# =========================================================

def load_foods(path=FOODS_PATH):
    """Load the existing cleaned CSV without changing the file."""

    df = pd.read_csv(path)

    required = {
        "fdc_id",
        "description",
        "data_type",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns in USDA CSV: {missing}"
        )

    df["description"] = df["description"].fillna("").astype(str)
    df["data_type"] = df["data_type"].fillna("").astype(str)

    # Ensure nutrient columns exist for the calculator.
    # Missing columns are represented as unavailable (NaN) in memory.
    # This does not modify the source CSV.
    for nutrient in NUTRIENTS:
        if nutrient not in df.columns:
            df[nutrient] = float("nan")
        else:
            df[nutrient] = pd.to_numeric(
                df[nutrient], errors="coerce"
            )

    df["tokens"] = df["description"].apply(tokenize)

    df["base_tokens"] = df["description"].apply(
        lambda text: tokenize(
            text,
            remove_preparation=True
        )
    )

    return df


foods = load_foods()


# =========================================================
# 4. MATCH SCORING
# =========================================================

def score_candidate(ingredient_words, food_words):
    """
    Rank text similarity from 0 to 1.

    This score is a heuristic, not a probability.
    """

    if not ingredient_words or not food_words:
        return 0.0

    matched = ingredient_words & food_words

    coverage = len(matched) / len(ingredient_words)
    specificity = len(matched) / len(food_words)

    score = 0.85 * coverage + 0.15 * specificity

    # Penalize explicit contradictions.
    for word in ingredient_words:
        incompatible = CONFLICTS.get(word, set())

        if food_words & incompatible:
            score -= 0.50

    # Penalize missing requested descriptors.
    missing_descriptors = (
        ingredient_words & IMPORTANT_DESCRIPTORS
    ) - food_words

    score -= 0.20 * len(missing_descriptors)

    return max(0.0, min(score, 1.0))


def get_data_type_rank(food):
    """Return a preference rank for a USDA record."""

    data_type = str(food.get("data_type", "")).strip().lower()

    return DATA_TYPE_PREFERENCE.get(data_type, 0)


def find_top_matches(ingredient_name, foods_df=None, top_n=5):
    """
    Return the highest-ranked USDA candidates.

    Each candidate includes its description, ID, score,
    matched keywords, and data type.
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

        # If the full description is not a good match, try
        # matching the base food without preparation words.
        base_score = score_candidate(
            ingredient_words,
            food["base_tokens"]
        )

        score = max(score, base_score)

        if score < MIN_MATCH_SCORE:
            continue

        candidates.append({
            "index": index,
            "fdc_id": food["fdc_id"],
            "description": food["description"],
            "data_type": food["data_type"],
            "score": score,
            "data_type_rank": get_data_type_rank(food),
            "matched_words": sorted(
                ingredient_words & food_words
            ),
        })

    # Food match quality comes first.
    # USDA data type only breaks ties.
    candidates.sort(
        key=lambda item: (
            item["score"],
            item["data_type_rank"]
        ),
        reverse=True
    )

    return candidates[:top_n]


def find_best_food(ingredient_name, foods_df=None):
    """
    Return (matched food row, score).

    Returns (None, best_score) if no candidate meets the
    minimum threshold.
    """

    if foods_df is None:
        foods_df = foods

    candidates = find_top_matches(
        ingredient_name,
        foods_df=foods_df,
        top_n=1
    )

    if not candidates:
        return None, 0.0

    best = candidates[0]

    if best["score"] < MIN_MATCH_SCORE:
        return None, best["score"]

    return foods_df.loc[best["index"]], best["score"]


def confidence_label(score):
    """Describe the heuristic score for review."""

    if score >= HIGH_MATCH_SCORE:
        return "high"

    if score >= REVIEW_MATCH_SCORE:
        return "medium"

    if score >= MIN_MATCH_SCORE:
        return "low"

    return "very_low"


# =========================================================
# 5. QUANTITY CONVERSION
# =========================================================

# Approximate grams per US cup.
# Add entries for ingredients used frequently in your recipes.
GRAMS_PER_CUP = {
    "all purpose flour": 120,
    "bread flour": 127,
    "whole wheat flour": 120,
    "granulated sugar": 200,
    "brown sugar": 220,
    "powdered sugar": 120,
    "butter": 227,
    "olive oil": 216,
    "vegetable oil": 218,
    "honey": 340,
    "water": 240,
    "milk": 245,
    "rolled oats": 90,
    "cooked rice": 158,
}

# Approximate grams per item.
# These values depend on item size and preparation.
GRAMS_PER_ITEM = {
    "large egg": 50,
    "medium egg": 44,
    "small egg": 38,
    "egg": 50,
    "garlic clove": 3,
    "clove garlic": 3,
}


def lookup_conversion_value(name, conversion_table):
    """Find the most specific conversion key in a name."""

    normalized = normalize_text(name)

    for key in sorted(
        conversion_table,
        key=len,
        reverse=True
    ):
        if key in normalized:
            return conversion_table[key]

    return None


def convert_to_grams(ingredient, food=None):
    """
    Convert a recipe ingredient to grams.

    Supports weight units directly.
    Volume and count units require a known conversion.

    Returns None when conversion information is unavailable.
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

    # Direct mass conversions.
    weight_factors = {
        "g": 1.0,
        "kg": 1000.0,
        "mg": 0.001,
        "oz": 28.3495,
        "lb": 453.592,
    }

    if unit in weight_factors:
        return quantity * weight_factors[unit]

    description = (
        food["description"]
        if food is not None
        else ""
    )

    ingredient_name = ingredient.get("name", "")
    combined_name = f"{ingredient_name} {description}"

    # Volume conversions need an ingredient-specific mass per cup.
    if unit in {"cup", "tbsp", "tsp", "ml"}:

        grams_per_cup = lookup_conversion_value(
            combined_name,
            GRAMS_PER_CUP
        )

        if grams_per_cup is None:
            return None

        volume_factors = {
            "cup": 1.0,
            "tbsp": 1.0 / 16.0,
            "tsp": 1.0 / 48.0,
            "ml": 1.0 / 240.0,
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

    # Unknown units such as slice, scoop, or serving need
    # more information before they can be converted.
    return None


# =========================================================
# 6. CALCULATE RECIPE MACROS
# =========================================================

def calculate_recipe_macros(recipe, foods_df=None):
    """
    Calculate total nutrition for a recipe.

    Returns:
        totals
        ingredient_results

    Important:
        Missing nutrient values in the CSV may already have been
        replaced with zero by your existing cleaning script.
        This function cannot recover those original missing values.
    """

    if foods_df is None:
        foods_df = foods

    totals = {
        nutrient: 0.0
        for nutrient in NUTRIENTS
    }

    # Track whether each nutrient is available for every matched
    # ingredient that has a usable quantity.
    nutrient_complete = {
        nutrient: True
        for nutrient in NUTRIENTS
    }

    ingredient_results = []

    for ingredient in recipe.get("ingredients", []):

        name = ingredient.get("name", "")
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit")

        food, score = find_best_food(
            name,
            foods_df
        )

        # No suitable food found.
        if food is None:

            for nutrient in NUTRIENTS:
                nutrient_complete[nutrient] = False

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

        # Match found, but quantity may not be convertible.
        amount_g = convert_to_grams(
            ingredient,
            food
        )

        if amount_g is None:

            for nutrient in NUTRIENTS:
                nutrient_complete[nutrient] = False

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

        # Do not silently calculate macros from a weak match.
        if score < REVIEW_MATCH_SCORE:

            for nutrient in NUTRIENTS:
                nutrient_complete[nutrient] = False

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

        multiplier = amount_g / 100.0
        missing_for_ingredient = []

        for nutrient in NUTRIENTS:

            value = food[nutrient]

            if pd.isna(value):
                nutrient_complete[nutrient] = False
                missing_for_ingredient.append(nutrient)
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
            "missing_nutrients": missing_for_ingredient,
            "status": (
                "matched_with_missing_nutrients"
                if missing_for_ingredient
                else "matched"
            ),
        })

    # A total is only complete if every ingredient was usable
    # and every matched food had that nutrient available.
    for nutrient in NUTRIENTS:
        if not nutrient_complete[nutrient]:
            totals[nutrient] = None

    return totals, ingredient_results


# =========================================================
# 7. DEBUGGING HELPER
# =========================================================

def print_top_matches(
    ingredient_name,
    foods_df=None,
    top_n=5
):
    """Print candidate foods to inspect matching behavior."""

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
            f"| Type: {candidate['data_type']} "
            f"| Score: {candidate['score']:.3f} "
            f"| Matched: {candidate['matched_words']}"
        )


# =========================================================
# 8. EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":

    print_top_matches("unsalted butter")
    print_top_matches("extra virgin olive oil")
    print_top_matches("chopped onion")
    print_top_matches("cooked white rice")

    example_recipe = {
        "ingredients": [
            {
                "name": "unsalted butter",
                "quantity": 2,
                "unit": "tbsp",
            },
            {
                "name": "all purpose flour",
                "quantity": 1,
                "unit": "cup",
            },
            {
                "name": "large egg",
                "quantity": 2,
                "unit": "eggs",
            },
        ]
    }

    totals, ingredient_results = calculate_recipe_macros(
        example_recipe
    )

    print("\nRecipe totals:")

    for nutrient, value in totals.items():
        if value is None:
            print(f"{nutrient}: INCOMPLETE")
        else:
            print(f"{nutrient}: {value:.2f}")

    print("\nIngredient results:")

    for result in ingredient_results:
        print(result)
