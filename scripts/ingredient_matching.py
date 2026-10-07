import re
import pandas as pd


# -----------------------------
# Text preprocessing
# -----------------------------

STOP_WORDS = {
    "a", "an", "the", "and", "of", "with", "for",
    "to", "in", "on", "from"
}


def tokenize(text):
    """
    Convert text into normalized keywords.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    words = text.split()

    return {
        word
        for word in words
        if word not in STOP_WORDS
    }


# -----------------------------
# Find USDA food
# -----------------------------

def find_best_food(ingredient_name, foods, top_n=10):
    """
    Find the USDA food that best matches an ingredient.

    Returns:
        matched food row
        match score
    """

    ingredient_words = tokenize(ingredient_name)

    if not ingredient_words:
        return None, 0

    # Calculate keyword overlap
    candidates = []

    for index, food in foods.iterrows():

        food_words = tokenize(food["description"])

        matching_words = ingredient_words & food_words

        if matching_words:
            # Basic score:
            # percentage of ingredient keywords found
            score = len(matching_words) / len(ingredient_words)

            candidates.append(
                (score, index, matching_words)
            )

    if not candidates:
        return None, 0

    # Highest score first
    candidates.sort(reverse=True, key=lambda x: x[0])

    best_score, best_index, matching_words = candidates[0]

    return foods.loc[best_index], best_score


# -----------------------------
# Calculate recipe macros
# -----------------------------

def calculate_recipe_macros(recipe, foods):
    """
    recipe should look something like:

    {
        "name": "Chicken Pasta",
        "ingredients": [
            {
                "name": "chicken breast",
                "amount_g": 200
            },
            {
                "name": "pasta",
                "amount_g": 100
            },
            {
                "name": "olive oil",
                "amount_g": 10
            }
        ]
    }
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

    for ingredient in recipe["ingredients"]:

        name = ingredient["name"]
        amount_g = ingredient["amount_g"]

        # Find USDA food
        food, score = find_best_food(name, foods)

        if food is None:
            print(f"Could not find a match for: {name}")

            ingredient_results.append({
                "ingredient": name,
                "amount_g": amount_g,
                "fdc_id": None,
                "matched_food": None,
                "match_score": 0
            })

            continue

        # USDA nutrition is per 100g
        multiplier = amount_g / 100

        # Add nutrition to recipe total
        for nutrient in totals:
            totals[nutrient] += (
                food[nutrient] * multiplier
            )

        ingredient_results.append({
            "ingredient": name,
            "amount_g": amount_g,
            "fdc_id": food["fdc_id"],
            "matched_food": food["description"],
            "match_score": score
        })

    return totals, ingredient_results
