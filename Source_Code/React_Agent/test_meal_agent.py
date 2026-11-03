"""Fixtures for test_meal_agent.py.

!! The nutrient numbers below are SYNTHETIC, for testing the plumbing only.
!! They are NOT USDA values. Never use them for real plans.
Recipe lines are copied from our recipes.json (a subset).
"""
import json
from pathlib import Path

import pandas as pd

# fdc_id, description, calories_kcal, protein_g, fat_g, carbs_g   (per 100 g, synthetic)
FOODS = [
    (1001, "Tofu, raw, firm, prepared with calcium sulfate", 144, 17.0, 9.0, 3.0),
    (1002, "Peas, green, raw", 80, 5.0, 0.5, 14.0),
    (1003, "Rice, brown, long-grain, raw", 370, 8.0, 3.0, 77.0),
    (1004, "Oil, vegetable, soybean, refined", 884, 0.0, 100.0, 0.0),
    (1005, "Soy protein concentrate", 330, 58.0, 0.5, 30.0),
    (1006, "Wheat flour, whole-grain", 340, 13.0, 2.5, 72.0),
    (1007, "Butter oil, anhydrous", 876, 0.3, 99.5, 0.0),
    (1008, "Cereals, oats, regular and quick, not fortified, dry", 379, 13.0, 6.5, 68.0),
    (1009, "Yogurt, greek, plain, lowfat", 73, 10.0, 2.0, 4.0),
    (1010, "Soybeans, mature seeds, roasted, salted", 450, 35.0, 22.0, 33.0),
    (1011, "Bread, whole-wheat, commercially prepared", 252, 12.5, 3.5, 43.0),
    (1012, "Onions, raw", 40, 1.0, 0.1, 9.0),
    (1013, "Tomatoes, red, ripe, raw, year round average", 18, 0.9, 0.2, 3.9),
    (1014, "Tomato puree", 38, 1.7, 0.1, 9.0),
    (1015, "Whey protein concentrate", 380, 80.0, 5.0, 8.0),
    (1016, "Quinoa, uncooked", 368, 14.0, 6.0, 64.0),
    (1017, "Peppers, sweet, green, raw", 20, 0.9, 0.2, 4.6),
    (1018, "Broccoli, raw", 34, 2.8, 0.4, 6.6),
]

# synthetic stand-in for a team-sourced paneer label (USDA has no paneer)
NUTRIENT_OVERRIDES = {"paneer_low_fat": {"source": "TEST FIXTURE (synthetic)",
                                         "per_100g": {"calories_kcal": 200, "protein_g": 20, "fat_g": 10, "carbs_g": 4}}}


def ing(name, qty=None, unit=None, text=None, notes=None):
    return {"name": name, "quantity": qty, "unit": unit, "quantity_text": text, "fdc_id": None, "notes": notes}


def recipe(rid, name, meal, ingredients, servings=1, tags=("vegetarian", "high-protein")):
    return {"recipe_id": rid, "name": name, "cuisine": "Indian", "meal_type": meal,
            "diet_tags": list(tags), "servings": servings, "ingredients": ingredients,
            "instructions": [], "source": "grocery_list"}


RECIPES = [
    recipe("tofu-scramble-toast", "Tofu Scramble Toast", "breakfast", [
        ing("extra-firm tofu", 150, "g"), ing("whole wheat bread", 2, "slice"), ing("turmeric", 0.25, "tsp"),
        ing("kala namak", 0.25, "tsp"), ing("oil", 1, "tsp"), ing("cilantro", text="chopped, to garnish")]),
    recipe("protein-oats-upma", "Savory Protein Oats Upma", "breakfast", [
        ing("oats", 50, "g"), ing("low-fat Greek yogurt", 150, "g"), ing("unflavored whey protein", 15, "g"),
        ing("mustard seeds", 0.25, "tsp"), ing("curry leaves", text="5-6 leaves"),
        ing("green chili", text="1, to taste"), ing("ginger", text="minced, to taste"), ing("oil", 1, "tsp")]),
    recipe("soya-chunks-matar-curry", "Soya Chunks Matar Curry with Brown Rice", "lunch", [
        ing("dry soya chunks", 60, "g"), ing("green peas", 50, "g"), ing("brown rice", 60, "g"),
        ing("onion-tomato base gravy", 3, "tbsp", notes="or 1 onion + 2 tomatoes pureed"),
        ing("ginger-garlic paste", text="to taste"), ing("turmeric", text="to taste"),
        ing("garam masala", text="to finish"), ing("oil", 1, "tsp")]),
    recipe("kadhai-tofu-quinoa", "Kadhai Tofu with Quinoa", "lunch", [
        ing("extra-firm tofu", 200, "g"), ing("quinoa", 60, "g"), ing("capsicum", 0.5, "piece", notes="diced"),
        ing("onion", 0.5, "piece", notes="diced"), ing("tomato puree", 2, "tbsp"),
        ing("kadhai spice mix", text="crushed coriander seeds and dry red chili"),
        ing("turmeric", text="to taste"), ing("oil", 1, "tsp")]),
    recipe("paneer-bhurji-roti", "Paneer Bhurji with Whole Wheat Roti", "dinner", [
        ing("low-fat paneer", 150, "g"), ing("whole wheat flour", 50, "g", notes="for 2 rotis"),
        ing("onion", 1, "piece", notes="finely chopped"), ing("tomato", 1, "piece", notes="finely chopped"),
        ing("green chili", text="to taste"), ing("turmeric", 0.25, "tsp"), ing("ghee", 1, "tsp")]),
    recipe("soya-tofu-stir-fry", "Soya & Tofu Stir-Fry", "dinner", [
        ing("dry soya chunks", 40, "g", notes="boiled and squeezed"), ing("extra-firm tofu", 100, "g"),
        ing("broccoli and bell peppers", 1, "cup"), ing("soy sauce", 1, "tbsp"), ing("vinegar", 1, "tsp"),
        ing("garlic", text="minced"), ing("oil", 1, "tsp")]),
    recipe("roasted-soya-nuts", "Roasted Soya Nuts", "snack", [ing("dry-roasted soya nuts", 45, "g")]),
    # null quantities for real foods => must be UNUSABLE, never guessed
    recipe("mixed-dal-chilla-wraps", "Mixed Dal Chilla Wraps with Mint Chutney", "dinner", [
        ing("split moong dal", text="equal parts with chana dal and urad dal"), ing("chana dal", text="equal parts"),
        ing("urad dal", text="equal parts"), ing("hing", text="pinch"), ing("carrot", text="shredded raw")],
        servings=4),
]


def write_fixtures(folder) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    csv = folder / "foods.csv"
    pd.DataFrame(FOODS, columns=["fdc_id", "description", "calories_kcal", "protein_g", "fat_g", "carbs_g"]).to_csv(csv, index=False)
    recipes = folder / "recipes.json"
    recipes.write_text(json.dumps(RECIPES))
    overrides = folder / "nutrient_overrides.json"
    overrides.write_text(json.dumps(NUTRIENT_OVERRIDES))
    return {"csv": csv, "recipes": recipes, "overrides": overrides}