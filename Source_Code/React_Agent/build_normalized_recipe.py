"""Offline step: data/recipes.json  ->  data/recipes_normalized.json

For every recipe line this (1) converts the quantity to grams using
ingredient_registry, (2) runs the NLP matcher once per ingredient to pick an
FDC id, and (3) records what could not be computed and why.

Run once, then REVIEW data/match_review.csv: it lists the top-3 FDC candidates
for every ingredient. Put the ones you confirm in data/fdc_overrides.json
({"tofu": 174290, ...}) and re-run; overrides always win over the matcher.

    python build_recipes.py --recipes data/recipes.json --foods path/to/clean_usda_foods.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import scripts.ingredient_matching as im
from food_db import FoodDB, _load_json
from ingredient_registry import ENTRY_BY_ID, normalize_line

ACCEPT_SCORE = getattr(im, "MEDIUM_CONFIDENCE_SCORE", 0.60)


def build_normalized(recipes: list[dict], db: FoodDB, fdc_overrides: dict | None = None,
                     accept_score: float = ACCEPT_SCORE):
    """Returns (normalized_recipes, review_rows)."""
    fdc_overrides = fdc_overrides or {}
    decided: dict[str, tuple] = {}     # ingredient_id -> (fdc_id | None, source, failure_reason | None)
    review_rows: list[dict] = []

    def decide(iid: str):
        if iid in decided:
            return decided[iid]
        entry = ENTRY_BY_ID[iid]
        if iid in db.nutrient_overrides:
            result = (None, "nutrient_override", None)
        elif iid in fdc_overrides:
            fdc = int(fdc_overrides[iid])
            result = (fdc, "fdc_override", None) if db.has_food(fdc) else \
                     (None, None, f"fdc_override {fdc} is not in the local dataset")
        else:
            matches = db.match(entry.query, top_k=3)
            for rank, m in enumerate(matches, 1):
                review_rows.append({"ingredient_id": iid, "query": entry.query, "rank": rank,
                                    "fdc_id": m["fdc_id"], "description": m["description"],
                                    "score": m["score"], "auto_accepted": rank == 1 and m["score"] >= accept_score})
            if not matches:
                review_rows.append({"ingredient_id": iid, "query": entry.query, "rank": 0, "fdc_id": "",
                                    "description": "(no candidates)", "score": 0, "auto_accepted": False})
                result = (None, None, f"no FDC candidates for query {entry.query!r}")
            elif matches[0]["score"] >= accept_score:
                result = (matches[0]["fdc_id"], f"matched:{matches[0]['score']}", None)
            else:
                result = (None, None, f"best match {matches[0]['description']!r} scored "
                                      f"{matches[0]['score']} < {accept_score}; confirm in fdc_overrides.json")
        decided[iid] = result
        return result

    normalized = []
    for r in recipes:
        lines = []
        for raw in r["ingredients"]:
            line = normalize_line(raw)
            if line["status"] in ("resolved", "estimated"):
                fdc, source, failure = decide(line["ingredient_id"])
                if failure:
                    line.update(status="unresolved", reason=failure)
                else:
                    line.update(fdc_id=fdc, source=source)
            lines.append(line)
        blockers = [f"{l['name']}: {l['reason']}" for l in lines if l["status"] == "unresolved"]
        normalized.append({
            "recipe_id": r["recipe_id"], "name": r["name"], "meal_type": r["meal_type"],
            "diet_tags": r.get("diet_tags", []), "servings": r.get("servings", 1),
            "source": r.get("source"), "ingredients": lines,
            "usable": not blockers, "blockers": blockers,
        })
    return normalized, review_rows


def write_review_csv(rows: list[dict], path: Path):
    fields = ["ingredient_id", "query", "rank", "fdc_id", "description", "score", "auto_accepted"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def summarize(normalized: list[dict]) -> str:
    usable = [r for r in normalized if r["usable"]]
    out = [f"{len(usable)}/{len(normalized)} recipes usable for planning."]
    for r in normalized:
        if not r["usable"]:
            out.append(f"  UNUSABLE {r['recipe_id']}:")
            out += [f"      - {b}" for b in r["blockers"]]
    est = [(r["recipe_id"], l["name"], l["grams"]) for r in normalized for l in r["ingredients"]
           if l["status"] == "estimated"]
    if est:
        out.append("Assumed amounts (status 'estimated'), please confirm:")
        out += [f"  {rid}: {name} ~{g} g" for rid, name, g in est]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipes", default="data/recipes.json")
    ap.add_argument("--out", default="data/recipes_normalized.json")
    ap.add_argument("--foods", default=None, help="USDA CSV (default: ingredient_matching.FOODS_PATH)")
    ap.add_argument("--fdc-overrides", default="data/fdc_overrides.json")
    ap.add_argument("--nutrient-overrides", default="data/nutrient_overrides.json")
    ap.add_argument("--review", default="data/match_review.csv")
    a = ap.parse_args()

    db = FoodDB.from_paths(a.foods, a.nutrient_overrides)
    recipes = json.loads(Path(a.recipes).read_text())
    normalized, rows = build_normalized(recipes, db, _load_json(a.fdc_overrides))
    Path(a.out).write_text(json.dumps({"recipes": normalized}, indent=2))
    write_review_csv(rows, Path(a.review))
    print(summarize(normalized))
    print(f"\nWrote {a.out} and {a.review}")


if __name__ == "__main__":
    main()