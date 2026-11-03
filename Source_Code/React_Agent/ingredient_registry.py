"""Ingredient registry for the fixed recipe bank (data/recipes.json).

This file is DATA plus a few small functions. Every number below (grams per
tsp/piece/cup, default amounts, which items count as "negligible") is a TEAM
DECISION written down in one place. They are typical values, not verified
facts: review them, change them, and re-run build_recipes.py.

For each raw recipe line, normalize_line() returns a line with one of these
statuses, which are the statuses math_engine.calculate_recipe understands:

  resolved            grams known, nutrients come from a matched FDC food
  estimated           no quantity in the recipe; a default `est` grams is assumed
  negligible_excluded seasoning/garnish excluded by rule (reason recorded)
  unresolved          cannot be computed (no registry entry, no quantity, ...)

A recipe with any unresolved line is marked unusable for planning, and the
build report says exactly which line blocks it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SEASONING = "seasoning/garnish: negligible, excluded by team rule"
SMALL = "small condiment amount (~1 tbsp or less): negligible, excluded by team rule"

_WEIGHT_UNITS = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "mg": 0.001}


def norm(text) -> str:
    """lowercase, hyphens/punctuation -> spaces, collapsed whitespace."""
    s = str(text or "").lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug(text) -> str:
    return norm(text).replace(" ", "_")


@dataclass(frozen=True)
class Entry:
    id: str
    names: tuple
    query: str | None = None          # text handed to the NLP matcher
    grams: dict = field(default_factory=dict)  # grams per 1 unit (tsp, tbsp, cup, piece, slice, scoop, ml)
    est: float | None = None          # grams to assume when the recipe gives no quantity
    skip: str | None = None           # reason string => negligible_excluded
    notes_any: tuple = ()             # only use this entry if the recipe note contains one of these words
    groups: tuple = ()                # allergen/food groups: dairy, soy, nuts


def E(id, names, query=None, grams=None, est=None, skip=None, notes_any=(), groups=()):
    return Entry(id, tuple(names), query, dict(grams or {}), est, skip, tuple(notes_any), tuple(groups))


# Order matters inside a name: entries with notes_any are tried before the default.
ENTRIES: list[Entry] = [
    # ---- proteins ---------------------------------------------------------
    # USDA has no paneer; the matcher will usually miss it. Add a nutrient
    # override (data/nutrient_overrides.json) or a team-confirmed fdc_id.
    E("paneer_low_fat", ["low-fat paneer", "paneer"], "paneer", groups=["dairy"]),
    E("tofu", ["extra-firm tofu", "firm tofu", "tofu"], "tofu firm", groups=["soy"]),
    E("soya_chunks", ["dry soya chunks", "soya chunks"], "soy protein", groups=["soy"]),
    E("soya_granules", ["dry soya granules", "soya granules"], "soy protein", groups=["soy"]),
    E("soya_nuts", ["dry-roasted soya nuts"], "soybeans roasted", groups=["soy"]),
    E("soy_flour", ["soy flour"], "soy flour", {"tbsp": 6}, groups=["soy"]),
    E("soy_milk", ["unsweetened soy milk"], "soymilk unsweetened", {"ml": 1.03}, groups=["soy"]),
    E("edamame", ["edamame pods"], "edamame frozen", groups=["soy"]),
    E("whey_isolate", ["unflavored whey protein", "whey protein isolate"], "whey protein", {"scoop": 30}, groups=["dairy"]),
    E("greek_yogurt", ["low-fat greek yogurt", "greek yogurt", "fat-free greek yogurt"], "greek yogurt", {"cup": 245}, groups=["dairy"]),
    E("curd", ["low-fat curd"], "yogurt plain low fat", {"cup": 245}, groups=["dairy"]),
    E("low_fat_milk", ["low-fat milk"], "milk lowfat", {"ml": 1.03}, groups=["dairy"]),
    E("cheese_blend", ["mozzarella and cheddar blend"], "cheese mozzarella", {"cup": 113}, groups=["dairy"]),
    # ---- legumes / grains -------------------------------------------------
    # kala/kabuli chana appear boiled (80 g) and dry-roasted (40 g): different foods.
    E("chickpeas_roasted", ["kala chana", "kabuli chana"], "chickpeas raw", notes_any=["roasted"]),
    E("chickpeas_boiled", ["kala chana", "kabuli chana"], "chickpeas cooked boiled"),
    E("moong_dal", ["moong dal", "split moong dal", "yellow moong or toor dal"], "mung beans", {"cup": 200}),
    E("moong_sprouts", ["mixed sprouts", "sprouted moong"], "mung beans sprouted"),
    E("urad", ["whole black urad", "urad dal"], "urad beans"),
    E("rajma", ["rajma"], "kidney beans raw"),
    E("chana_dal", ["chana dal"], "chickpeas raw"),
    E("green_peas", ["green peas"], "peas green raw"),
    E("oats", ["oats"], "oats"),
    E("brown_rice", ["brown rice"], "rice brown raw"),          # assumed dry weight
    E("basmati_rice", ["basmati rice"], "rice white raw"),      # assumed dry weight
    E("quinoa", ["quinoa"], "quinoa uncooked"),                  # assumed dry weight
    E("quinoa_rice_mix", ["quinoa-rice mix"], "quinoa uncooked", {"cup": 170}),  # assumed dry
    E("whole_wheat_flour", ["whole wheat flour", "atta"], "whole wheat flour"),
    E("whole_wheat_bread", ["whole wheat bread"], "bread whole wheat", {"slice": 30}),
    E("flour_tortilla", ["flour tortilla"], "tortillas flour"),
    E("sweet_corn", ["sweet corn kernels"], "corn sweet"),
    E("soft_paratha", ["soft paratha"], "paratha"),
    E("chia_seeds", ["chia seeds"], "chia seeds"),
    E("almonds", ["almonds"], "almonds", {"piece": 1.2}, groups=["nuts"]),
    # ---- fats -------------------------------------------------------------
    E("cooking_oil", ["oil", "cooking oil"], "oil vegetable soybean", {"tsp": 4.5, "tbsp": 13.6}),
    E("olive_oil", ["olive oil"], "oil olive salad cooking", {"tsp": 4.5, "tbsp": 13.5}),
    E("mustard_oil", ["mustard oil"], "oil mustard", {"tsp": 4.5, "tbsp": 13.6}),
    E("ghee", ["ghee"], "butter oil", {"tsp": 4.7, "tbsp": 14.1}, groups=["dairy"]),
    E("butter", ["butter"], "butter", {"tbsp": 14.2}, est=5, groups=["dairy"]),
    # ---- vegetables (est = amount assumed when the recipe gives none) ------
    E("onion", ["onion", "red onion"], "onions raw", {"piece": 110}, est=50),
    E("tomato", ["tomato"], "tomatoes red raw", {"piece": 123}),
    E("tomato_puree", ["tomato puree", "onion-tomato base gravy"], "tomato puree", {"tbsp": 15, "cup": 250}, est=30),
    E("bell_pepper", ["capsicum", "bell peppers", "mixed bell peppers"], "peppers sweet raw", {"piece": 120, "cup": 149}, est=60),
    E("cucumber", ["cucumber"], "cucumber raw", {"piece": 200}, est=50),
    E("carrot", ["carrot"], "carrots raw", {"piece": 61}, est=30),
    E("broccoli", ["broccoli florets", "broccoli and bell peppers"], "broccoli raw", {"cup": 91}),
    E("spinach", ["spinach"], "spinach raw"),
    # ---- seasonings & garnish: excluded by rule (one entry, one id per name) ----
    E("seasoning", [
        "mustard seeds", "curry leaves", "green chili", "ginger", "garlic", "coriander", "cilantro",
        "coriander leaves", "hing", "salt", "kala namak", "black salt", "sea salt", "turmeric", "ajwain",
        "red chili powder", "red chili flakes", "kashmiri red chili powder", "degi mirch", "garam masala",
        "chaat masala", "cumin powder", "cumin seeds", "roasted cumin powder", "kasuri methi",
        "kadhai spice mix", "biryani spice mix", "mint leaves", "ginger-garlic paste", "lemon juice",
        "mint-cilantro-yogurt chutney"], skip=SEASONING),
    E("small_condiments", ["soy sauce", "low-sodium soy sauce", "vinegar", "cornstarch"], skip=SMALL),
]

_INDEX: dict[str, list[Entry]] = {}
for _e in ENTRIES:
    for _n in _e.names:
        _INDEX.setdefault(norm(_n), []).append(_e)

ENTRY_BY_ID = {e.id: e for e in ENTRIES}
GROUPS: dict[str, set[str]] = {}
for _e in ENTRIES:
    for _g in _e.groups:
        GROUPS.setdefault(_g, set()).add(_e.id)

SYNONYMS = {"soya": "soy", "nut": "nuts", "curd": "yogurt", "yoghurt": "yogurt"}


def find_entry(name, notes="") -> Entry | None:
    candidates = _INDEX.get(norm(name), [])
    note = norm(notes)
    for e in candidates:
        if e.notes_any and any(k in note for k in e.notes_any):
            return e
    for e in candidates:
        if not e.notes_any:
            return e
    return None


def to_grams(qty, unit, entry: Entry):
    """Grams for `qty unit` of this ingredient, or None if no conversion is known."""
    unit = norm(unit)
    if qty is None or not unit:
        return None
    if unit in _WEIGHT_UNITS:
        return qty * _WEIGHT_UNITS[unit]
    g = dict(entry.grams)
    cup = g.get("cup") or (g["tbsp"] * 16 if "tbsp" in g else None) or (g["tsp"] * 48 if "tsp" in g else None)
    if cup:
        g.setdefault("cup", cup)
        g.setdefault("tbsp", cup / 16)
        g.setdefault("tsp", cup / 48)
    if unit == "ml":
        return qty * g.get("ml", 1.0)       # water-like default for liquids
    if unit in g:
        return qty * g[unit]
    return None


def normalize_line(raw: dict) -> dict:
    """Turn one raw recipe ingredient into a normalized line (see module docstring)."""
    name = raw.get("name", "")
    notes = raw.get("notes") or ""
    qty, unit, qtext = raw.get("quantity"), raw.get("unit"), raw.get("quantity_text")
    line = {"name": name, "note": notes or None, "quantity": qty, "unit": unit,
            "quantity_text": qtext, "ingredient_id": None, "grams": None,
            "status": "unresolved", "reason": None, "fdc_id": None, "source": None}
    entry = find_entry(name, notes)
    if entry is None:
        line["reason"] = "not in ingredient registry (add it to ingredient_registry.py)"
        return line
    line["ingredient_id"] = slug(name) if entry.skip else entry.id
    if entry.skip:
        g = to_grams(qty, unit, entry)
        line.update(status="negligible_excluded", reason=entry.skip,
                    grams=None if g is None else round(g, 2))
        return line
    grams = to_grams(qty, unit, entry)
    if grams is not None:
        line.update(status="resolved", grams=round(grams, 2))
    elif qty is not None:
        line["reason"] = f"no gram conversion for {qty} {unit} of {entry.id}"
    elif entry.est:
        line.update(status="estimated", grams=float(entry.est),
                    reason=f"no quantity given ({qtext!r}); assumed {entry.est} g")
    else:
        line["reason"] = f"no quantity given ({qtext!r}); add grams to the recipe or an `est` to the registry"
    return line


def ingredient_matches(line: dict, term: str) -> bool:
    """True if an exclusion term (e.g. 'tofu', 'soy', 'dairy') hits this normalized line."""
    t = norm(term)
    if not t:
        return False
    syn = SYNONYMS.get(t, t)
    name, iid = norm(line.get("name")), (line.get("ingredient_id") or "")
    if t in name or syn in name or syn in iid.replace("_", " ") or t in iid.replace("_", " "):
        return True
    return iid in GROUPS.get(syn, set()) or iid in GROUPS.get(t, set())