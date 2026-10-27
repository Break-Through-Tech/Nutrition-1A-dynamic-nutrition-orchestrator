"""Run the meal-planning agent from the command line.

Prerequisites (once):
    pip install -U ollama pandas
    ollama pull qwen2.5:7b-instruct          # any tool-capable local model
    python build_recipes.py --recipes data/recipes.json --foods path/to/clean_usda_foods.csv

Then:
    python run_agent.py "Plan 7 days of vegetarian meals with at least 120g of protein per day and under 2000 calories."
    python run_agent.py "One high-protein day, no tofu" --verbose --trace trace.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_tools import RecipeBank
from food_db import FoodDB
from meal_agent import MealPlanningAgent, OllamaClient, format_plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", help="the user's requirements, in plain English")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--recipes", default="data/recipes_normalized.json")
    ap.add_argument("--foods", default=None, help="USDA CSV (default: ingredient_matching.FOODS_PATH)")
    ap.add_argument("--nutrient-overrides", default="data/nutrient_overrides.json")
    ap.add_argument("--max-steps", type=int, default=12, help="tool-call budget per day")
    ap.add_argument("--no-llm-parse", action="store_true", help="parse requirements with regex only")
    ap.add_argument("--verbose", action="store_true", help="print every tool call as it happens")
    ap.add_argument("--trace", default=None, help="write the full Thought/Action/Observation trace (JSON)")
    ap.add_argument("--json", dest="json_out", default=None, help="write the final plan (JSON)")
    a = ap.parse_args()

    db = FoodDB.from_paths(a.foods, a.nutrient_overrides)
    bank = RecipeBank.from_file(a.recipes, db)
    agent = MealPlanningAgent(OllamaClient(a.model), bank, max_steps=a.max_steps,
                              llm_parse=not a.no_llm_parse, verbose=a.verbose)
    result = agent.plan(a.request)
    print(format_plan(result))
    if a.trace:
        Path(a.trace).write_text(json.dumps(result["trace"], indent=2))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({k: v for k, v in result.items() if k != "trace"}, indent=2))


if __name__ == "__main__":
    main()