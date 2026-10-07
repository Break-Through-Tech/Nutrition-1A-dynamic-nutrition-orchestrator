import re
import pandas as pd

# Load USDA food data
foods = pd.read_csv("../cleanedData/clean_usda_foods.csv")


# ---------------------------------------------------------
# 1. Text processing
# ---------------------------------------------------------

STOP_WORDS = {
    "a", "an", "the", "and", "of", "with", "for",
    "to", "in", "on", "from"
}


def tokenize(text):
    """
    Convert text into normalized keywords.
    """
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    words = text.split()

    return {
        word
        for word in words
        if word not in STOP_WORDS
    }


# Precompute tokens for every USDA food
foods["tokens"] = foods["description"].apply(tokenize)


# ---------------------------------------------------------
# 2. Find the best USDA food match
# ---------------------------------------------------------

def find_best_food(ingredient_name, foods):
    """
    Find the USDA food that best matches an ingredient.

    Returns:
        matched food row
        match score
    """

    ingredient_words = tokenize(ingredient_name)

    if not ingredient_words:
        return None, 0

    candidates = []

    for index, food in foods.iterrows():

        food_words = food["tokens"]

        matching_words = ingredient_words & food_words

        if matching_words:

            score = len(matching_words) / len(ingredient_words)

            candidates.append(
                (score, index, matching_words)
            )

    if not candidates:
        return None, 0

    candidates.sort(
        reverse=True,
        key=lambda x: x[0]
    )

    best_score, best_index, matching_words = candidates[0]

    return foods.loc[best_index], best_score


# ---------------------------------------------------------
# 3. Convert ingredient quantity to grams
# ---------------------------------------------------------

def convert_to_grams(ingredient):
    """
    Convert an ingredient quantity into grams.

    Supported:
        g
        kg
        mg
        tsp
        tbsp
        cup
        cups
        ml

    Not currently convertible without
    ingredient-specific information:
        servings
        slices
        pieces
        scoop
        small

    Returns:
        amount in grams, or None
    """

    quantity = ingredient.get("quantity")
    unit = ingredient.get("unit")

    if quantity is None or unit is None:
        return None

    unit = unit.lower().strip()

    # Weight
    if unit == "g":
        return quantity

    elif unit == "kg":
        return quantity * 1000

    elif unit == "mg":
        return quantity / 1000

    # Volume
    elif unit == "tsp":
        return quantity * 5

    elif unit == "tbsp":
        return quantity * 15

    elif unit in {"cup", "cups"}:
        return quantity * 240

    elif unit == "ml":
        return quantity

    # Requires ingredient-specific conversion
    elif unit in {
        "servings",
        "slices",
        "pieces",
        "scoop",
        "small"
    }:
        return None

    return None


# ---------------------------------------------------------
# 4. Calculate recipe macros
# ---------------------------------------------------------

def calculate_recipe_macros(recipe, foods):

    """
    Calculate total nutrition for a recipe.

    Returns:
        totals
        ingredient_results
    """

    totals = {
        "calories_kcal": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbs_g": 0,
        "fiber_g": 0,
        "sugars_g": 0,
        "sodium_mg": 0,
        "potassium_mg": 0,
        "calcium_mg": 0,
        "iron_mg": 0
    }

    ingredient_results = []

    # -----------------------------------------------------
    # Go through every ingredient
    # -----------------------------------------------------

    for ingredient in recipe["ingredients"]:

        name = ingredient["name"]
        quantity = ingredient.get("quantity")
        unit = ingredient.get("unit")

        # -------------------------------------------------
        # Convert quantity to grams
        # -------------------------------------------------

        amount_g = convert_to_grams(ingredient)

        # -------------------------------------------------
        # Handle ingredients we can't convert yet
        # -------------------------------------------------

        if amount_g is None:

            print(
                f"Skipping '{name}': "
                f"cannot convert {quantity} {unit} to grams."
            )

            ingredient_results.append({
                "ingredient": name,
                "quantity": quantity,
                "unit": unit,
                "amount_g": None,
                "fdc_id": None,
                "matched_food": None,
                "match_score": 0,
                "status": "needs_conversion"
            })

            continue

        # -------------------------------------------------
        # Find USDA food
        # -------------------------------------------------

        food, score = find_best_food(
            name,
            foods
        )

        # -------------------------------------------------
        # Handle no USDA match
        # -------------------------------------------------

        if food is None:

            print(
                f"Could not find a USDA match for: {name}"
            )

            ingredient_results.append({
                "ingredient": name,
                "quantity": quantity,
                "unit": unit,
                "amount_g": amount_g,
                "fdc_id": None,
                "matched_food": None,
                "match_score": 0,
                "status": "no_food_match"
            })

            continue

        # -------------------------------------------------
        # USDA nutrition is per 100 g
        # -------------------------------------------------

        multiplier = amount_g / 100

        for nutrient in totals:

            value = food[nutrient]

            if pd.isna(value):
                value = 0

            totals[nutrient] += value * multiplier

        # -------------------------------------------------
        # Save result
        # -------------------------------------------------

        ingredient_results.append({
            "ingredient": name,
            "quantity": quantity,
            "unit": unit,
            "amount_g": amount_g,
            "fdc_id": food["fdc_id"],
            "matched_food": food["description"],
            "match_score": score,
            "status": "matched"
        })

    return totals, ingredient_results
