## Task 1 : Ingest and structure the local recipe seed database into normalized data structures.
# Two google doc recipes
# 1. High-Protein Indian Vegetarian Meal Plan & Grocery Matrix
# 2. High-Protein Indian Vegetarian Meal Plan & Grocery List


"""
Recipe seed ingestion: PDFs -> normalized plain-dict tables.

Tables (all plain dicts keyed by id, no Pydantic):
  INGREDIENTS   ingredient_id -> {name, aliases, category, fdc_id}
  RECIPES       recipe_id     -> {name, meal_type, source, servings_basis, steps, ...}
  RECIPE_ITEMS  list of {recipe_id, ingredient_id, qty, unit, qty_g, note}   (join table)
  MEAL_SLOTS    list of {source, day, slot, recipe_id}
  GROCERY       list of {source, ingredient_id, qty_g, family_size}

Run:  python3 build_database.py
"""
import json
import re

# ---------- 0. Source documents (one entry per PDF)
SRC_GROCERY_LIST = "grocery_list"
SRC_GROCERY_MATRIX = "grocery_matrix"

SOURCES = {
    SRC_GROCERY_LIST: {
        "title": "High-Protein Indian Vegetarian Meal Plan & Grocery List",
        "file": "High-Protein_Indian_Vegetarian_Meal_Plan___Grocery_List.pdf",
        "recipe_quantities": "per person",
        "servings_basis": 1,
    },
    SRC_GROCERY_MATRIX: {
        "title": "High-Protein Indian Vegetarian Meal Plan & Grocery Matrix",
        "file": "High-Protein_Vegetarian_Meal_Plan___Grocery_Matrix.pdf",
        "recipe_quantities": "batch for family of 4 (assumed; adult/kid split unclear)",
        "servings_basis": 4,
    },
}

# ---------- 1. Canonical ingredients (grow this as the validator reports misses)
INGREDIENTS = {
    "paneer_low_fat": {"name": "Low-fat paneer", "category": "dairy_protein", "fdc_id": None,
                       "aliases": ["low-fat paneer", "low fat paneer", "low-fat / skim-milk paneer",
                                   "crumbled low-fat paneer", "grated low-fat paneer", "grilled low-fat paneer"]},
    "tofu_extra_firm": {"name": "Extra-firm tofu", "category": "soy_protein", "fdc_id": None,
                        "aliases": ["extra-firm tofu", "firm tofu", "tofu"]},
    "soya_chunks_dry": {"name": "Soya chunks (dry)", "category": "soy_protein", "fdc_id": None,
                        "aliases": ["dry soya chunks", "soya chunks", "large soya chunks"]},
    "soya_granules_dry": {"name": "Soya granules (dry)", "category": "soy_protein", "fdc_id": None,
                          "aliases": ["dry soya granules", "soya granules", "soya keema"]},
    "oats": {"name": "Oats", "category": "grain", "fdc_id": None, "aliases": ["oats", "whole oats", "rolled oats"]},
    "greek_yogurt_lowfat": {"name": "Low-fat Greek yogurt", "category": "dairy_protein", "fdc_id": None,
                            "aliases": ["low-fat greek yogurt", "greek yogurt"]},
    "whey_isolate": {"name": "Whey protein isolate", "category": "supplement", "fdc_id": None,
                     "aliases": ["unflavored whey", "whey isolate", "whey protein isolate"]},
    "brown_rice": {"name": "Brown rice", "category": "grain", "fdc_id": None, "aliases": ["brown rice"]},
    "green_peas": {"name": "Green peas", "category": "vegetable", "fdc_id": None, "aliases": ["green peas", "matar"]},
    "atta": {"name": "Whole wheat flour (atta)", "category": "grain", "fdc_id": None,
             "aliases": ["whole wheat flour", "atta", "whole wheat atta"]},
    "ghee": {"name": "Ghee", "category": "fat", "fdc_id": None, "aliases": ["ghee"]},
    "cooking_oil": {"name": "Cooking oil", "category": "fat", "fdc_id": None, "aliases": ["oil", "cooking oil"]},
    "kala_chana": {"name": "Kala chana (black chickpeas)", "category": "legume", "fdc_id": None,
                   "aliases": ["kala chana", "black chana", "dry-roasted chana"]},
    "almonds": {"name": "Almonds", "category": "nut_seed", "fdc_id": None, "aliases": ["almonds"]},
    # ... add the rest (moong dal, quinoa, kabuli chana, edamame, ...)
}

# alias -> id lookup, built once
ALIAS_INDEX = {}
for _id, _ing in INGREDIENTS.items():
    for a in [_ing["name"], *_ing["aliases"]]:
        ALIAS_INDEX[a.lower().strip()] = _id

# ---------- 2. Units -> grams (only where unambiguous; else qty_g stays None)
UNIT_TO_G = {"g": 1, "kg": 1000}
# oil/ghee density approximations are an ASSUMPTION; keep them explicit and overridable
FAT_TSP_TO_G = {"cooking_oil": 4.5, "ghee": 4.7}

LINE_RE = re.compile(
    r"^(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|ml|l|tsp|tbsp|cups?)?\s+(?P<name>.+)$", re.I)


def parse_ingredient_line(line):
    """'60g Dry Soya Chunks' -> {'qty': 60.0, 'unit': 'g', 'raw_name': 'Dry Soya Chunks'}.
    Returns None for lines with no leading number (e.g. 'Bell peppers'); handle those by hand."""
    m = LINE_RE.match(line.strip().lstrip("•●- ").strip())
    if not m:
        return None
    unit = (m["unit"] or "count").lower().rstrip("s") if (m["unit"] or "").lower() != "cups" else "cup"
    return {"qty": float(m["qty"]), "unit": unit, "raw_name": m["name"].strip()}


def resolve_ingredient(raw_name):
    key = raw_name.lower().strip()
    if key in ALIAS_INDEX:
        return ALIAS_INDEX[key]
    # fall back: longest alias contained in the string
    hits = [a for a in ALIAS_INDEX if a in key]
    return ALIAS_INDEX[max(hits, key=len)] if hits else None


UNRESOLVED = []  # (recipe_id, raw line) pairs for manual review


def build_items(recipe_id, lines):
    items = []
    for line in lines:
        p = parse_ingredient_line(line)
        ing_id = resolve_ingredient(p["raw_name"]) if p else None
        if not p or not ing_id:
            UNRESOLVED.append((recipe_id, line))
            continue
        qty_g = p["qty"] * UNIT_TO_G[p["unit"]] if p["unit"] in UNIT_TO_G else None
        if p["unit"] == "tsp" and ing_id in FAT_TSP_TO_G:
            qty_g = p["qty"] * FAT_TSP_TO_G[ing_id]
        items.append({"recipe_id": recipe_id, "ingredient_id": ing_id, "qty": p["qty"],
                      "unit": p["unit"], "qty_g": qty_g, "note": p["raw_name"]})
    return items


# ---------- 3. Seed records (hand-curated from the PDFs; two shown as the pattern)
RECIPES, RECIPE_ITEMS, MEAL_SLOTS = {}, [], []


def add_recipe(recipe_id, name, meal_type, source, servings_basis, ingredient_lines, steps,
               stated_protein_g=None, tags=()):
    RECIPES[recipe_id] = {
        "name": name, "meal_type": meal_type,          # breakfast|lunch|snack|dinner
        "source": source,                              # key into SOURCES
        "servings_basis": servings_basis,              # see SOURCES[source]["servings_basis"]
        "steps": steps, "tags": list(tags),
        "stated_protein_g": stated_protein_g,          # provenance only; real macros come from FDC
        "diet": "vegetarian", "cuisine": "indian",
    }
    RECIPE_ITEMS.extend(build_items(recipe_id, ingredient_lines))


add_recipe(
    "soya_matar_curry_list", "Soya Chunks Matar Curry with Brown Rice", "lunch", SRC_GROCERY_LIST, 1,
    ["60g Dry Soya Chunks", "50g Green Peas", "60g Brown Rice", "1 tsp oil"],
    ["Boil soya chunks 10 min, squeeze dry.", "Cook brown rice.",
     "Saute gravy base with spices in 1 tsp oil.", "Add soya + peas, toss 2 min.",
     "Add 150ml water, simmer 10 min, finish with garam masala."],
    stated_protein_g=40, tags=["batch_base_gravy"])

add_recipe(
    "paneer_bhurji_roti_list", "Paneer Bhurji with Whole Wheat Roti", "dinner", SRC_GROCERY_LIST, 1,
    ["150g Low-fat Paneer", "50g Whole wheat flour", "1 tsp ghee"],
    ["Make 2 rotis.", "Saute onion, chilli, tomato.", "Crumble paneer in, cook 3-4 min max."],
    stated_protein_g=35)

for day, slot, rid in [("Monday", "lunch", "soya_matar_curry_list"),
                       ("Monday", "dinner", "paneer_bhurji_roti_list"),
                       ("Thursday", "lunch", "soya_matar_curry_list"),
                       ("Thursday", "dinner", "paneer_bhurji_roti_list")]:
    MEAL_SLOTS.append({"source": SRC_GROCERY_LIST, "day": day, "slot": slot, "recipe_id": rid})


# ---------- 4. Validation: surfaces data problems instead of hiding them
def validate():
    problems = []
    for it in RECIPE_ITEMS:
        if it["recipe_id"] not in RECIPES:
            problems.append(f"orphan item -> recipe {it['recipe_id']}")
        if it["ingredient_id"] not in INGREDIENTS:
            problems.append(f"unknown ingredient {it['ingredient_id']}")
    for s in MEAL_SLOTS:
        if s["recipe_id"] not in RECIPES:
            problems.append(f"slot references missing recipe {s['recipe_id']}")
        elif RECIPES[s["recipe_id"]]["meal_type"] != s["slot"]:
            problems.append(f"slot/meal_type mismatch: {s}")
    for rid, r in RECIPES.items():
        if r["source"] not in SOURCES:
            problems.append(f"recipe {rid} has unknown source {r['source']}")
    for rid in RECIPES:
        if not any(i["recipe_id"] == rid for i in RECIPE_ITEMS):
            problems.append(f"recipe with no ingredients: {rid}")
    problems += [f"UNRESOLVED line in {r}: {l!r}" for r, l in UNRESOLVED]
    return problems


def per_serving(recipe_id):
    """Scale item quantities to one serving, so family-scaled (grocery matrix) and per-person (grocery list) compare."""
    basis = RECIPES[recipe_id]["servings_basis"]
    return [{**i, "qty": i["qty"] / basis, "qty_g": (i["qty_g"] / basis) if i["qty_g"] else None}
            for i in RECIPE_ITEMS if i["recipe_id"] == recipe_id]


# ---------- 5. Export
def export(path="seed_db.json"):
    with open(path, "w") as f:
        json.dump({"ingredients": INGREDIENTS, "recipes": RECIPES, "recipe_items": RECIPE_ITEMS,
                   "meal_slots": MEAL_SLOTS, "sources": SOURCES}, f, indent=2)


# Optional helper to dump raw PDF text so you can copy lines into add_recipe(...)
def dump_pdf_text(pdf_path):
    import pdfplumber  # pip install pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


if __name__ == "__main__":
    issues = validate()
    print(f"{len(INGREDIENTS)} ingredients, {len(RECIPES)} recipes, {len(RECIPE_ITEMS)} items")
    print("\n".join(issues) or "validation clean")
    export()