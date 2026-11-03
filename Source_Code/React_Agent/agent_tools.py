"""Everything the ReAct agent can do, and every rule it must satisfy.

Design rule: the LLM only DECIDES (which recipe, how many servings). Every
number comes from math_engine, and every pass/fail comes from PlanState.check_*.
Plan state lives here in Python, so the model never has to copy numbers around.
"""
from __future__ import annotations

import json
from pathlib import Path

from food_db import FoodDB
from ingredient_registry import ingredient_matches
from nutrition_engine.math_engine import aggregate_results, calculate_meal, calculate_recipe

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
MAX_SERVINGS = 3.0


def _r(x, nd=1):
    return None if x is None else round(float(x), nd)


# ---------------------------------------------------------------- constraints
def normalize_constraints(raw: dict | None):
    """Validate/complete a constraints dict. Returns (constraints, assumptions)."""
    raw, notes = dict(raw or {}), []

    def number(key, lo, hi, cast):
        try:
            v = cast(raw.get(key))
        except (TypeError, ValueError):
            return None
        return v if lo <= v <= hi else None

    days = number("days", 1, 14, int)
    if days is None:
        days = 7
        notes.append("days not specified: planning 7 days")
    wanted = {str(m).lower() for m in (raw.get("meal_types") or [])}
    meal_types = [m for m in MEAL_TYPES if m in wanted]
    if not meal_types:
        meal_types = list(MEAL_TYPES)
        notes.append("meal types not specified: planning breakfast, lunch, dinner and a snack")
    repeat = number("no_repeat_days", 0, 6, int)
    if repeat is None:
        repeat = 2
        notes.append("repeat rule not specified: a recipe will not reappear within 2 days")
    tags = [str(t).lower() for t in (raw.get("required_tags") or [])] or ["vegetarian"]
    c = {
        "days": days,
        "meal_types": meal_types,
        "protein_g_min_per_day": number("protein_g_min_per_day", 0, 500, float),
        "calories_max_per_day": number("calories_max_per_day", 300, 8000, float),
        "excluded_ingredients": [str(x).lower().strip() for x in (raw.get("excluded_ingredients") or []) if str(x).strip()],
        "required_tags": tags,
        "no_repeat_days": repeat,
        "unsupported": [str(x) for x in (raw.get("unsupported") or [])],
    }
    return c, notes


# ---------------------------------------------------------------- recipe bank
class RecipeBank:
    """Normalized recipes + per-recipe macros computed by math_engine."""

    def __init__(self, recipes: list[dict], db: FoodDB):
        self.recipes = {r["recipe_id"]: r for r in recipes}
        self.db = db
        self._results: dict[str, dict] = {}

    @classmethod
    def from_file(cls, path, db: FoodDB):
        data = json.loads(Path(path).read_text())
        return cls(data["recipes"] if isinstance(data, dict) else data, db)

    def result(self, recipe_id: str) -> dict:
        """math_engine.calculate_recipe output (per-serving totals), cached."""
        if recipe_id not in self._results:
            r = self.recipes[recipe_id]
            lines = []
            for l in r["ingredients"]:
                item = {"name": l["name"], "amount_g": l.get("grams"), "reason": l.get("reason")}
                status = l["status"]
                if status in ("resolved", "estimated"):
                    profile = self.db.profile_for(l.get("ingredient_id"), l.get("fdc_id"))
                    if profile is None:
                        item.update(status="unresolved", reason="no nutrient profile available")
                    else:
                        item.update(status=status, fdc_id=l.get("fdc_id") or l["ingredient_id"],
                                    nutrients_per_100g=profile)
                else:
                    item["status"] = status      # negligible_excluded / unresolved
                lines.append(item)
            self._results[recipe_id] = calculate_recipe(lines, servings=r.get("servings", 1))
        return self._results[recipe_id]

    def macros(self, recipe_id: str, servings: float = 1.0) -> dict:
        r = self.recipes[recipe_id]
        meal = calculate_meal(self.result(recipe_id), servings)
        t = meal["totals"]
        return {
            "recipe_id": recipe_id, "name": r["name"], "meal_type": r["meal_type"], "servings": servings,
            "protein_g": _r(t["protein_g"]), "calories_kcal": _r(t["calories_kcal"]),
            "carbs_g": _r(t["carbs_g"]), "fat_g": _r(t["fat_g"]),
            "core_complete": meal["core_complete"],
            "estimated_items": [l["name"] for l in r["ingredients"] if l["status"] == "estimated"],
        }

    def excluded_by(self, recipe_id: str, terms: list[str]) -> str | None:
        for l in self.recipes[recipe_id]["ingredients"]:
            for t in terms:
                if ingredient_matches(l, t):
                    return f"contains '{l['name']}' (excluded: {t})"
        return None


# ---------------------------------------------------------------- plan state
class PlanState:
    def __init__(self, constraints: dict, bank: RecipeBank):
        self.c = constraints
        self.bank = bank
        self.days: dict[int, dict[str, dict]] = {}     # day -> meal_type -> {recipe_id, servings}

    # -- rules shared by search_recipes and set_meal ------------------------
    def conflict(self, day: int, recipe_id: str, meal_type: str | None = None) -> str | None:
        for mt, m in self.days.get(day, {}).items():
            if m["recipe_id"] == recipe_id and mt != meal_type:
                return f"already used for {mt} on day {day}"
        w = self.c["no_repeat_days"]
        for d, meals in self.days.items():
            if d != day and abs(d - day) <= w and any(m["recipe_id"] == recipe_id for m in meals.values()):
                return f"already used on day {d} (no repeats within {w} days)"
        return None

    def eligible(self, recipe_id: str, meal_type: str, extra_terms=()) -> str | None:
        """None if the recipe may fill this slot, else the reason it may not."""
        r = self.bank.recipes.get(recipe_id)
        if r is None:
            return "unknown recipe_id (use ids returned by search_recipes)"
        if not r["usable"]:
            return "recipe has unresolved ingredients: " + "; ".join(r["blockers"][:2])
        if r["meal_type"] != meal_type:
            return f"is a {r['meal_type']} recipe, not {meal_type}"
        missing = [t for t in self.c["required_tags"] if t not in r["diet_tags"]]
        if missing:
            return f"missing required diet tag(s): {missing}"
        return self.bank.excluded_by(recipe_id, list(self.c["excluded_ingredients"]) + list(extra_terms))

    def set_meal(self, day, meal_type, recipe_id, servings=1.0) -> dict:
        if meal_type not in self.c["meal_types"]:
            return {"ok": False, "error": f"meal_type must be one of {self.c['meal_types']}"}
        if not (0.5 <= servings <= MAX_SERVINGS) or (servings * 2) % 1:
            return {"ok": False, "error": f"servings must be 0.5 to {MAX_SERVINGS:g} in steps of 0.5"}
        why = self.eligible(recipe_id, meal_type) or self.conflict(day, recipe_id, meal_type)
        if why:
            return {"ok": False, "error": f"cannot use {recipe_id}: {why}"}
        self.days.setdefault(day, {})[meal_type] = {"recipe_id": recipe_id, "servings": servings}
        return {"ok": True, "meal": self.bank.macros(recipe_id, servings), "day_so_far": self._brief(day)}

    def clear_meal(self, day, meal_type) -> dict:
        removed = self.days.get(day, {}).pop(meal_type, None)
        return {"ok": removed is not None, "day_so_far": self._brief(day),
                **({} if removed else {"error": f"no {meal_type} was set"})}

    # -- numbers -------------------------------------------------------------
    def day_aggregate(self, day):
        meals = self.days.get(day, {})
        results = [calculate_meal(self.bank.result(m["recipe_id"]), m["servings"]) for m in meals.values()]
        return aggregate_results(results, totals_key="totals") if results else None

    def _brief(self, day) -> dict:
        agg = self.day_aggregate(day)
        t = agg["totals"] if agg else {}
        return {"protein_g": _r(t.get("protein_g")), "calories_kcal": _r(t.get("calories_kcal")),
                "missing_meals": [m for m in self.c["meal_types"] if m not in self.days.get(day, {})]}

    def meal_details(self, day) -> dict:
        return {mt: self.bank.macros(m["recipe_id"], m["servings"])
                for mt, m in self.days.get(day, {}).items()}

    # -- checks (authoritative; plain Python) ---------------------------------
    def check_day(self, day) -> dict:
        c, v, warn = self.c, [], []
        brief = self._brief(day)
        if brief["missing_meals"]:
            v.append(f"missing meals: {brief['missing_meals']}")
        protein, kcal = brief["protein_g"], brief["calories_kcal"]
        out = {"day": day, "meals": {mt: m["recipe_id"] for mt, m in self.days.get(day, {}).items()},
               "totals": {"protein_g": protein, "calories_kcal": kcal}}
        pmin, cmax = c["protein_g_min_per_day"], c["calories_max_per_day"]
        if self.days.get(day):
            if pmin is not None:
                if protein is None:
                    v.append("protein total unknown (incomplete nutrition data)")
                elif protein < pmin:
                    v.append(f"protein {protein:g}g is below the {pmin:g}g minimum")
                    out["protein_short_by_g"] = _r(pmin - protein)
            if cmax is not None:
                if kcal is None:
                    v.append("calorie total unknown (incomplete nutrition data)")
                elif kcal > cmax:
                    v.append(f"calories {kcal:g} exceed the {cmax:g} maximum")
                    out["calories_over_by"] = _r(kcal - cmax)
                else:
                    out["calorie_headroom_kcal"] = _r(cmax - kcal)
        est = sorted({n for m in self.meal_details(day).values() for n in m["estimated_items"]})
        if est:
            warn.append(f"amounts assumed for: {est}")
        out.update(ok=not v, violations=v, warnings=warn)
        return out

    def check_week(self) -> dict:
        checks, aggs, v = [], [], []
        for d in range(1, self.c["days"] + 1):
            res = self.check_day(d)
            checks.append(res)
            v += [f"day {d}: {x}" for x in res["violations"]]
            agg = self.day_aggregate(d)
            if agg:
                aggs.append(agg)
        week = aggregate_results(aggs, totals_key="totals") if aggs else None
        n = self.c["days"]
        avg = lambda k: _r(week["totals"][k] / n) if week and week["totals"].get(k) is not None else None
        return {"ok": not v, "violations": v, "days": checks,
                "weekly": {"avg_protein_g_per_day": avg("protein_g"), "avg_calories_per_day": avg("calories_kcal"),
                           "total_protein_g": _r(week["totals"]["protein_g"]) if week else None,
                           "total_calories_kcal": _r(week["totals"]["calories_kcal"]) if week else None}}


# ---------------------------------------------------------------- tools
def _servings(x) -> float:
    return float(x)


class DayTools:
    """The tool set for planning ONE day. `day` is bound, so the model never passes it."""

    def __init__(self, state: PlanState, day: int, db: FoodDB | None = None):
        self.state, self.day, self.db = state, day, db or state.bank.db
        self.registry = {
            "search_recipes": self.search_recipes, "get_recipe_macros": self.get_recipe_macros,
            "set_meal": self.set_meal, "clear_meal": self.clear_meal,
            "check_plan": self.check_plan, "match_ingredient": self.match_ingredient,
        }
        self.schemas = TOOL_SCHEMAS

    def call(self, name: str, args) -> dict:
        fn = self.registry.get(name)
        if fn is None:
            return {"error": f"unknown tool '{name}'", "available_tools": sorted(self.registry)}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}
        except (ValueError, KeyError) as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def search_recipes(self, meal_type: str, exclude_ingredients=None) -> dict:
        mt = str(meal_type).lower()
        if mt not in self.state.c["meal_types"]:
            return {"error": f"meal_type must be one of {self.state.c['meal_types']}"}
        extra = [str(x).lower() for x in (exclude_ingredients or [])]
        found = [{"recipe_id": rid, "name": r["name"]}
                 for rid, r in self.state.bank.recipes.items()
                 if self.state.eligible(rid, mt, extra) is None
                 and self.state.conflict(self.day, rid, mt) is None]
        return {"meal_type": mt, "count": len(found), "recipes": found}

    def get_recipe_macros(self, recipe_id: str, servings=1) -> dict:
        r = self.state.bank.recipes.get(recipe_id)
        if r is None:
            return {"error": "unknown recipe_id (use ids returned by search_recipes)"}
        if not r["usable"]:
            return {"error": "recipe has unresolved ingredients", "blockers": r["blockers"][:3]}
        return self.state.bank.macros(recipe_id, _servings(servings))

    def set_meal(self, meal_type: str, recipe_id: str, servings=1) -> dict:
        return self.state.set_meal(self.day, str(meal_type).lower(), recipe_id, _servings(servings))

    def clear_meal(self, meal_type: str) -> dict:
        return self.state.clear_meal(self.day, str(meal_type).lower())

    def check_plan(self) -> dict:
        return self.state.check_day(self.day)

    def match_ingredient(self, query: str, top_k=3) -> dict:
        return {"query": query, "candidates": self.db.match(str(query), int(top_k))}


def _fn(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


_MEAL = {"type": "string", "enum": list(MEAL_TYPES), "description": "breakfast, lunch, dinner or snack"}
TOOL_SCHEMAS = [
    _fn("search_recipes", "List recipes that may fill a meal slot today (diet, exclusions and repeat rules already applied).",
        {"meal_type": _MEAL}, ["meal_type"]),
    _fn("get_recipe_macros", "Protein, calories, carbs and fat for a recipe at a number of servings. Use to compare candidates.",
        {"recipe_id": {"type": "string"}, "servings": {"type": "number", "description": "0.5 to 3, default 1"}}, ["recipe_id"]),
    _fn("set_meal", "Put a recipe in a meal slot for today. Returns running day totals or an error to fix.",
        {"meal_type": _MEAL, "recipe_id": {"type": "string"}, "servings": {"type": "number", "description": "0.5 to 3 in steps of 0.5, default 1"}},
        ["meal_type", "recipe_id"]),
    _fn("clear_meal", "Remove the recipe from a meal slot today.", {"meal_type": _MEAL}, ["meal_type"]),
    _fn("check_plan", "Check today's plan against the user's constraints. ok=true means today is done.", {}),
    _fn("match_ingredient", "Find USDA FDC candidates for an ingredient name (NLP match).",
        {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
]