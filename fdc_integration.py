"""
USDA FoodData Central integration with Pydantic validation.

Pydantic is used only at the API boundary (validating what FDC sends back and what
we store). After validation everything is converted back to plain dicts via
.model_dump(), so it plugs into the dict-based seed_db.json from seed_ingest.py.

Setup:
    pip install pydantic requests
    export FDC_API_KEY="NfyMaKQi3W7HOQMGcWVwnia0TykDYgzeQzR1Ymge"        (Windows PowerShell: $env:FDC_API_KEY="your_key")

Workflow:
    python fdc_integration.py propose            # search FDC, write fdc_candidates.json
    (open fdc_candidates.json, pick the best fdc_id per ingredient, put them in fdc_choices.json)
    python fdc_integration.py apply              # fetch nutrients, write them into seed_db.json
    python fdc_integration.py macros soya_matar_curry_list
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

BASE_URL = "https://api.nal.usda.gov/fdc/v1"
CACHE_DIR = Path(".fdc_cache")
DB_PATH = Path("seed_db.json")

# ---------------------------------------------------------------- 1. Schemas
# FDC nutrient numbers. Energy is not always 208 (Foundation foods often use
# Atwater energy 957/958), so calories falls back through this list.
CALORIE_NUMBERS = ("208", "957", "958")
MACRO_NUMBERS = {"203": "protein_g", "204": "fat_g", "205": "carbs_g", "291": "fiber_g"}

_LOOSE = ConfigDict(extra="ignore", populate_by_name=True, coerce_numbers_to_str=False)


class FDCSearchFood(BaseModel):
    model_config = _LOOSE
    fdc_id: int = Field(alias="fdcId")
    description: str
    data_type: str = Field(alias="dataType")
    brand_owner: Optional[str] = Field(default=None, alias="brandOwner")


class FDCSearchResponse(BaseModel):
    model_config = _LOOSE
    total_hits: int = Field(default=0, alias="totalHits")
    foods: list[FDCSearchFood] = Field(default_factory=list)


class FDCNutrientInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, coerce_numbers_to_str=True)
    number: Optional[str] = None          # e.g. "203" for protein
    name: Optional[str] = None
    unit_name: Optional[str] = Field(default=None, alias="unitName")


class FDCFoodNutrient(BaseModel):
    model_config = _LOOSE
    nutrient: FDCNutrientInfo
    amount: Optional[float] = None


class FDCFoodDetail(BaseModel):
    model_config = _LOOSE
    fdc_id: int = Field(alias="fdcId")
    description: str
    data_type: str = Field(alias="dataType")
    food_nutrients: list[FDCFoodNutrient] = Field(default_factory=list, alias="foodNutrients")


class NutrientsPer100g(BaseModel):
    """What we actually store on each ingredient. Strict, so bad data fails loudly."""
    calories_kcal: float = Field(ge=0, le=900)      # pure fat is ~884 kcal/100g
    protein_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fiber_g: float = Field(default=0.0, ge=0, le=100)

    @model_validator(mode="after")
    def macros_fit_in_100g(self):
        if self.protein_g + self.fat_g + self.carbs_g > 105:   # small slack for rounding
            raise ValueError("protein + fat + carbs exceeds 100g per 100g of food")
        return self


class FDCChoice(BaseModel):
    """One entry of fdc_choices.json (your manual decision)."""
    fdc_id: int
    note: str = ""


# ---------------------------------------------------------------- 2. Client
class FDCClient:
    def __init__(self, api_key: Optional[str] = None, cache_dir: Path = CACHE_DIR):
        self.api_key = api_key or os.environ["FDC_API_KEY"]
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.session = requests.Session()

    def _get(self, path: str, params: dict) -> dict:
        # Cache by request (key excluded) so reruns don't burn your hourly rate limit.
        raw = path + json.dumps(params, sort_keys=True)
        cache_file = self.cache_dir / (hashlib.md5(raw.encode()).hexdigest() + ".json")
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        for attempt in range(4):
            resp = self.session.get(f"{BASE_URL}{path}", params={**params, "api_key": self.api_key}, timeout=20)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            cache_file.write_text(json.dumps(data))
            return data
        resp.raise_for_status()
        raise RuntimeError("FDC request failed after retries")

    def search(self, query: str, data_types=("Foundation", "SR Legacy"), page_size: int = 8) -> FDCSearchResponse:
        data = self._get("/foods/search", {"query": query, "dataType": ",".join(data_types), "pageSize": page_size})
        return FDCSearchResponse.model_validate(data)

    def food(self, fdc_id: int) -> FDCFoodDetail:
        return FDCFoodDetail.model_validate(self._get(f"/food/{fdc_id}", {}))


# ---------------------------------------------------------------- 3. Extraction
def to_per_100g(detail: FDCFoodDetail) -> NutrientsPer100g:
    by_number = {n.nutrient.number: n.amount for n in detail.food_nutrients
                 if n.nutrient.number and n.amount is not None}
    calories = next((by_number[k] for k in CALORIE_NUMBERS if k in by_number), None)
    if calories is None:
        raise ValueError(f"FDC {detail.fdc_id} ({detail.description}) has no energy value")
    fields = {name: by_number.get(num, 0.0) for num, name in MACRO_NUMBERS.items()}
    return NutrientsPer100g(calories_kcal=calories, **fields)


# ---------------------------------------------------------------- 4. Matching
# STARTER queries only. Review the candidates by hand: FDC has no "paneer" in
# Foundation/SR Legacy, so low-fat paneer needs a proxy (or a Branded entry).
FDC_QUERIES = {
    "paneer_low_fat": "cheese cottage lowfat",
    "tofu_extra_firm": "tofu raw firm",
    "soya_chunks_dry": "soy protein",
    "soya_granules_dry": "soy protein",
    "oats": "oats",
    "greek_yogurt_lowfat": "yogurt greek plain lowfat",
    "whey_isolate": "whey protein isolate",
    "brown_rice": "rice brown long-grain raw",
    "green_peas": "peas green raw",
    "atta": "wheat flour whole-grain",
    "ghee": "butter oil anhydrous",
    "cooking_oil": "oil olive salad or cooking",
    "kala_chana": "chickpeas mature seeds raw",
    "almonds": "nuts almonds",
}


def propose_matches(client: FDCClient, out_path="fdc_candidates.json"):
    db = json.loads(DB_PATH.read_text())
    out = {}
    for ing_id in db["ingredients"]:
        query = FDC_QUERIES.get(ing_id, db["ingredients"][ing_id]["name"])
        res = client.search(query)
        out[ing_id] = {"query": query,
                       "candidates": [f.model_dump(exclude={"brand_owner"}) for f in res.foods]}
    Path(out_path).write_text(json.dumps(out, indent=2))
    template = {k: {"fdc_id": None, "note": ""} for k in out}
    if not Path("fdc_choices.json").exists():
        Path("fdc_choices.json").write_text(json.dumps(template, indent=2))
    print(f"Wrote {out_path}. Fill in fdc_choices.json with the fdc_id you want per ingredient.")


def apply_matches(client: FDCClient):
    db = json.loads(DB_PATH.read_text())
    choices = json.loads(Path("fdc_choices.json").read_text())
    for ing_id, raw in choices.items():
        if raw.get("fdc_id") is None:
            print(f"skip {ing_id}: no fdc_id chosen")
            continue
        choice = FDCChoice.model_validate(raw)
        detail = client.food(choice.fdc_id)
        nutrients = to_per_100g(detail)                 # raises if data is nonsense
        ing = db["ingredients"][ing_id]
        ing["fdc_id"] = choice.fdc_id
        ing["fdc_description"] = detail.description
        ing["fdc_data_type"] = detail.data_type
        ing["fdc_note"] = choice.note
        ing["nutrients_per_100g"] = nutrients.model_dump()
        print(f"ok   {ing_id}: {detail.description} -> {nutrients.calories_kcal} kcal, {nutrients.protein_g}g P")
    DB_PATH.write_text(json.dumps(db, indent=2))


# ---------------------------------------------------------------- 5. Recipe macros
def recipe_macros(db: dict, recipe_id: str) -> dict:
    recipe = db["recipes"][recipe_id]
    total = {"calories_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0, "fiber_g": 0.0}
    missing = []
    for item in (i for i in db["recipe_items"] if i["recipe_id"] == recipe_id):
        n = db["ingredients"][item["ingredient_id"]].get("nutrients_per_100g")
        if item["qty_g"] is None or n is None:
            missing.append(item["ingredient_id"])       # never silently count as zero
            continue
        for k in total:
            total[k] += n[k] * item["qty_g"] / 100
    basis = recipe["servings_basis"]
    return {"per_serving": {k: round(v / basis, 1) for k, v in total.items()},
            "stated_protein_g": recipe.get("stated_protein_g"),
            "missing_items": missing}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "propose":
        propose_matches(FDCClient())
    elif cmd == "apply":
        apply_matches(FDCClient())
    elif cmd == "macros":
        print(json.dumps(recipe_macros(json.loads(DB_PATH.read_text()), sys.argv[2]), indent=2))
    else:
        print(__doc__)