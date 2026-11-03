from food_db import FoodDB
from agent_tools import RecipeBank
db = FoodDB.from_paths("cleanedData/clean_usda_foods.csv", "data/nutrient_overrides.json")
bank = RecipeBank.from_file("data/recipes_normalized.json", db)
rows = []
for rid, r in bank.recipes.items():
    if r["usable"]:
        m = bank.macros(rid)
        rows.append((m["meal_type"], rid, m["protein_g"], m["calories_kcal"], m["core_complete"]))
for t, rid, p, k, c in sorted(rows):
    print(f"{t:<10}{rid:<34}protein={p:>6}  kcal={k:>7}  complete={c}")
