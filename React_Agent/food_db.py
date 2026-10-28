"""Thin adapter over the local USDA dataset.

- match(): the NLP matcher (ingredient_matching.find_top_matches).
- profile_for(): nutrients per 100 g for an ingredient, looked up by fdc_id.

Two deliberate choices:
1. Nutrient lookup reads the CSV itself and keeps blanks as None. The matcher's
   load_foods() fills missing nutrients with 0.0, which would silently turn
   "unknown" into "zero" and defeat math_engine's missing-data tracking.
2. nutrient_overrides (data/nutrient_overrides.json) beat the CSV. Use them for
   foods USDA lacks, e.g. paneer, with a `source` note for each entry:
       {"paneer_low_fat": {"source": "package label ...",
                           "per_100g": {"calories_kcal": ..., "protein_g": ..., "fat_g": ..., "carbs_g": ...}}}
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import ingredient_matching as im

NUTRIENTS = tuple(im.NUTRIENTS)


def _load_json(path):
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())
    return {}


class FoodDB:
    def __init__(self, foods_csv=None, nutrient_overrides=None):
        self.path = Path(foods_csv) if foods_csv else Path(im.FOODS_PATH)
        self.nutrient_overrides = dict(nutrient_overrides or {})
        self._foods = None       # frame for the matcher
        self._profiles = None    # {fdc_id: {nutrient: float | None}}

    @classmethod
    def from_paths(cls, foods_csv=None, nutrient_overrides_path=None):
        return cls(foods_csv, _load_json(nutrient_overrides_path))

    # ---- matching ---------------------------------------------------------
    def match(self, query: str, top_k: int = 3) -> list[dict]:
        if self._foods is None:
            self._foods = im.load_foods(self.path)
        out = []
        for m in im.find_top_matches(query, self._foods, top_n=top_k):
            out.append({"fdc_id": int(m["fdc_id"]), "description": m["description"],
                        "score": round(float(m["score"]), 3),
                        "confidence": im.confidence_label(m["score"])})
        return out

    # ---- nutrient lookup --------------------------------------------------
    def _load_profiles(self):
        df = pd.read_csv(self.path)
        cols = [n for n in NUTRIENTS if n in df.columns]
        profiles = {}
        for rec in df[["fdc_id", *cols]].to_dict("records"):
            profiles[int(rec["fdc_id"])] = {
                n: (None if (n not in rec or pd.isna(rec[n])) else float(rec[n])) for n in NUTRIENTS}
        self._profiles = profiles

    def profile_for(self, ingredient_id: str | None, fdc_id=None) -> dict | None:
        """Nutrients per 100 g (None for unknown nutrients), or None if no source exists."""
        ov = self.nutrient_overrides.get(ingredient_id)
        if ov:
            per = ov.get("per_100g", {})
            return {n: per.get(n) for n in NUTRIENTS}
        if fdc_id is None:
            return None
        if self._profiles is None:
            self._load_profiles()
        return self._profiles.get(int(fdc_id))

    def has_food(self, fdc_id) -> bool:
        if self._profiles is None:
            self._load_profiles()
        return int(fdc_id) in self._profiles