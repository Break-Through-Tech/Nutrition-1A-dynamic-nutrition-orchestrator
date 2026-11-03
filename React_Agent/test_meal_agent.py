"""Tests. Run:  python -m unittest test_meal_agent -v      (or: pytest test_meal_agent.py)

Nutrient values come from test_fixtures.py and are SYNTHETIC. Expected numbers are
computed by hand from them, independent of the code under test.
"""
import json
import tempfile
import unittest
from pathlib import Path

from agent_tools import DayTools, PlanState, RecipeBank, normalize_constraints
from build_normalized_recipe import build_normalized
from food_db import FoodDB
from ingredient_registry import normalize_line
from meal_agent import (LLMReply, MealPlanningAgent, ScriptedClient, _inline_call, call, parse_constraints,
                        parse_constraints_regex)
from test_fixtures import RECIPES, ing, recipe, write_fixtures


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        paths = write_fixtures(cls.tmp.name)
        cls.db = FoodDB.from_paths(paths["csv"], paths["overrides"])
        cls.normalized, cls.review = build_normalized(RECIPES, cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bank(self):
        return RecipeBank(self.normalized, self.db)

    def agent(self, replies, **kw):
        return MealPlanningAgent(ScriptedClient(replies), self.bank(), llm_parse=False, repair_rounds=0, **kw)


class TestRegistry(unittest.TestCase):
    def test_spoon_and_piece_conversions(self):
        self.assertEqual(normalize_line(ing("oil", 1, "tsp"))["grams"], 4.5)
        self.assertEqual(normalize_line(ing("ghee", 1, "tsp"))["grams"], 4.7)
        self.assertEqual(normalize_line(ing("onion-tomato base gravy", 3, "tbsp"))["grams"], 45.0)
        self.assertEqual(normalize_line(ing("whole wheat bread", 2, "slice"))["grams"], 60.0)
        self.assertEqual(normalize_line(ing("onion", 1, "piece"))["grams"], 110.0)

    def test_seasonings_are_negligible_with_reason(self):
        line = normalize_line(ing("turmeric", 0.25, "tsp"))
        self.assertEqual(line["status"], "negligible_excluded")
        self.assertTrue(line["reason"])

    def test_real_food_without_quantity_is_unresolved_not_guessed(self):
        line = normalize_line(ing("split moong dal", text="equal parts"))
        self.assertEqual(line["status"], "unresolved")
        self.assertIsNone(line["grams"])

    def test_default_amount_is_flagged_estimated(self):
        line = normalize_line(ing("onion", text="sliced"))
        self.assertEqual((line["status"], line["grams"]), ("estimated", 50.0))

    def test_unknown_ingredient_and_unknown_unit(self):
        self.assertEqual(normalize_line(ing("dragon fruit", 100, "g"))["status"], "unresolved")
        self.assertEqual(normalize_line(ing("brown rice", 1, "bowl"))["status"], "unresolved")

    def test_kala_chana_state_follows_note(self):
        boiled = normalize_line(ing("kala chana", 80, "g", notes="soaked overnight and boiled"))
        roasted = normalize_line(ing("kala chana", 40, "g", notes="dry-roasted"))
        self.assertEqual((boiled["ingredient_id"], roasted["ingredient_id"]), ("chickpeas_boiled", "chickpeas_roasted"))


class TestBuild(Base):
    def by_id(self, rid):
        return next(r for r in self.normalized if r["recipe_id"] == rid)

    def test_usable_flags(self):
        self.assertTrue(self.by_id("paneer-bhurji-roti")["usable"])
        bad = self.by_id("mixed-dal-chilla-wraps")
        self.assertFalse(bad["usable"])
        self.assertTrue(any("split moong dal" in b for b in bad["blockers"]))

    def test_matcher_picks_expected_foods(self):
        tofu = next(l for l in self.by_id("tofu-scramble-toast")["ingredients"] if l["ingredient_id"] == "tofu")
        self.assertEqual(tofu["fdc_id"], 1001)

    def test_low_confidence_match_is_rejected(self):
        carrot = next(l for l in self.by_id("mixed-dal-chilla-wraps")["ingredients"] if l["name"] == "carrot")
        self.assertEqual(carrot["status"], "unresolved")
        self.assertIn("scored", carrot["reason"])

    def test_paneer_uses_nutrient_override(self):
        line = next(l for l in self.by_id("paneer-bhurji-roti")["ingredients"] if l["ingredient_id"] == "paneer_low_fat")
        self.assertEqual((line["fdc_id"], line["source"]), (None, "nutrient_override"))

    def test_fdc_override_beats_matcher_and_bad_override_is_unresolved(self):
        recipes = [recipe("r", "R", "lunch", [ing("tofu", 100, "g")])]
        norm, _ = build_normalized(recipes, self.db, {"tofu": 1002})
        self.assertEqual(norm[0]["ingredients"][0]["fdc_id"], 1002)
        norm, _ = build_normalized(recipes, self.db, {"tofu": 99999})
        self.assertFalse(norm[0]["usable"])

    def test_review_rows_written_for_each_ingredient(self):
        self.assertIn("tofu", {r["ingredient_id"] for r in self.review})


class TestMacros(Base):
    def test_matar_curry_matches_hand_calculation(self):
        # protein: soy 60g*.58 + peas 50g*.05 + rice 60g*.08 + puree 45g*.017 + oil 0
        m = self.bank().macros("soya-chunks-matar-curry")
        self.assertAlmostEqual(m["protein_g"], 34.8 + 2.5 + 4.8 + 0.765, delta=0.1)
        # kcal: 198 + 40 + 222 + 17.1 + 4.5g*8.84
        self.assertAlmostEqual(m["calories_kcal"], 198 + 40 + 222 + 17.1 + 39.78, delta=0.2)
        self.assertTrue(m["core_complete"])

    def test_paneer_recipe_uses_override_nutrients(self):
        m = self.bank().macros("paneer-bhurji-roti")
        self.assertAlmostEqual(m["protein_g"], 30 + 6.5 + 1.1 + 1.107 + 0.014, delta=0.1)

    def test_servings_scale_linearly(self):
        b = self.bank()
        self.assertAlmostEqual(b.macros("roasted-soya-nuts", 1.5)["protein_g"], b.macros("roasted-soya-nuts")["protein_g"] * 1.5, delta=0.2)   # outputs are rounded to 0.1

    def test_batch_recipe_is_divided_per_serving(self):
        rec = recipe("batch", "Batch", "dinner", [ing("extra-firm tofu", 800, "g")], servings=4)
        norm, _ = build_normalized([rec], self.db)
        self.assertAlmostEqual(RecipeBank(norm, self.db).macros("batch")["protein_g"], 800 * 0.17 / 4, delta=0.1)

    def test_estimated_amounts_are_reported(self):
        rec = recipe("est", "Est", "lunch", [ing("extra-firm tofu", 100, "g"), ing("onion", text="sliced")])
        norm, _ = build_normalized([rec], self.db)
        m = RecipeBank(norm, self.db).macros("est")
        self.assertEqual(m["estimated_items"], ["onion"])
        self.assertTrue(m["core_complete"])

    def test_missing_nutrient_is_unknown_not_zero(self):
        # fixture CSV has no fiber column; totals for fiber must be None, never 0
        res = self.bank().result("paneer-bhurji-roti")
        self.assertIsNone(res["per_serving_totals"]["fiber_g"])
        self.assertIsNotNone(res["per_serving_totals"]["protein_g"])


class TestRules(Base):
    def state(self, **c):
        base = {"days": 3, "meal_types": ["breakfast", "lunch", "dinner", "snack"], "protein_g_min_per_day": 100,
                "calories_max_per_day": 2000, "no_repeat_days": 1}
        base.update(c)
        return PlanState(normalize_constraints(base)[0], self.bank())

    def test_wrong_meal_type_is_rejected(self):
        r = self.state().set_meal(1, "lunch", "protein-oats-upma")
        self.assertFalse(r["ok"])
        self.assertIn("breakfast recipe", r["error"])

    def test_unusable_recipe_is_rejected(self):
        self.assertIn("unresolved", self.state().set_meal(1, "dinner", "mixed-dal-chilla-wraps")["error"])

    def test_repeat_window(self):
        s = self.state()
        self.assertTrue(s.set_meal(1, "breakfast", "tofu-scramble-toast")["ok"])
        self.assertFalse(s.set_meal(2, "breakfast", "tofu-scramble-toast")["ok"])
        self.assertTrue(s.set_meal(3, "breakfast", "tofu-scramble-toast")["ok"])    # 2 days apart, window is 1

    def test_repeat_rule_can_be_disabled(self):
        s = self.state(no_repeat_days=0)
        s.set_meal(1, "breakfast", "tofu-scramble-toast")
        self.assertTrue(s.set_meal(2, "breakfast", "tofu-scramble-toast")["ok"])

    def test_servings_validation(self):
        s = self.state()
        self.assertFalse(s.set_meal(1, "snack", "roasted-soya-nuts", 0.25)["ok"])
        self.assertFalse(s.set_meal(1, "snack", "roasted-soya-nuts", 4)["ok"])
        self.assertFalse(s.set_meal(1, "snack", "roasted-soya-nuts", 1.3)["ok"])
        self.assertTrue(s.set_meal(1, "snack", "roasted-soya-nuts", 1.5)["ok"])

    def test_exclusions_filter_search(self):
        ids = lambda **c: {x["recipe_id"] for x in DayTools(self.state(**c), 1).search_recipes("dinner")["recipes"]}
        self.assertEqual(ids(), {"paneer-bhurji-roti", "soya-tofu-stir-fry"})       # chilla is unusable
        self.assertEqual(ids(excluded_ingredients=["tofu"]), {"paneer-bhurji-roti"})
        self.assertEqual(ids(excluded_ingredients=["paneer"]), {"soya-tofu-stir-fry"})
        self.assertEqual(ids(excluded_ingredients=["soy"]), {"paneer-bhurji-roti"})  # 'soy' covers soya chunks + tofu
        self.assertEqual(ids(excluded_ingredients=["dairy"]), {"soya-tofu-stir-fry"})

    def test_required_tag(self):
        self.assertEqual(DayTools(self.state(required_tags=["kid-friendly"]), 1).search_recipes("lunch")["count"], 0)

    def test_check_day_reports_gap_and_missing_meals(self):
        s = self.state()
        s.set_meal(1, "breakfast", "tofu-scramble-toast")
        chk = s.check_day(1)
        self.assertFalse(chk["ok"])
        self.assertTrue(any("missing meals" in v for v in chk["violations"]))
        self.assertTrue(any("protein" in v for v in chk["violations"]))
        self.assertGreater(chk["protein_short_by_g"], 60)

    def test_calorie_cap(self):
        s = self.state(calories_max_per_day=900, protein_g_min_per_day=None, meal_types=["breakfast", "lunch"])
        s.set_meal(1, "breakfast", "tofu-scramble-toast")
        s.set_meal(1, "lunch", "kadhai-tofu-quinoa")
        chk = s.check_day(1)
        self.assertFalse(chk["ok"])
        self.assertIn("exceed", chk["violations"][0])
        self.assertGreater(chk["calories_over_by"], 0)

    def test_tool_errors_are_informative(self):
        t = DayTools(self.state(), 1)
        self.assertIn("available_tools", t.call("nope", {}))
        self.assertIn("bad arguments", t.call("set_meal", {"wrong": 1})["error"])
        self.assertIn("unknown recipe_id", t.call("get_recipe_macros", {"recipe_id": "zzz"})["error"])
        self.assertEqual(t.call("match_ingredient", {"query": "tofu"})["candidates"][0]["fdc_id"], 1001)


class TestParsing(unittest.TestCase):
    def test_headline_example(self):
        c, notes = parse_constraints("Plan 7 days of vegetarian meals with at least 120g of protein per day and under 2000 calories.")
        self.assertEqual((c["days"], c["protein_g_min_per_day"], c["calories_max_per_day"]), (7, 120, 2000))
        self.assertEqual(c["required_tags"], ["vegetarian"])
        self.assertEqual(c["meal_types"], ["breakfast", "lunch", "dinner", "snack"])
        self.assertTrue(any("meal types not specified" in n for n in notes))

    def test_structured_requirement_formats(self):
        for text in ["Protein target: 140g/day\nCalories: < 2,000 kcal/day\nDiet: Vegetarian",
                     "Protein target: 140g/day, Calories: under 2000, Diet: Vegetarian",
                     "Protein: 140 g per day; calories less than 2,000",
                     "at least 140g protein and fewer than 2000 calories",
                     "Calories: \u2264 2,000 kcal/day, protein 140g/day"]:
            f = parse_constraints_regex(text)
            self.assertEqual((f.get("protein_g_min_per_day"), f.get("calories_max_per_day")), (140, 2000), text)

    def test_exclusions_and_meals(self):
        f = parse_constraints_regex("I need a high-protein day: breakfast, lunch, dinner and one snack. No tofu or soy, and at least 100g protein.")
        self.assertEqual(f["excluded_ingredients"], ["tofu", "soy"])
        self.assertEqual((f["days"], f["protein_g_min_per_day"], f["meal_types"]), (1, 100, ["breakfast", "lunch", "dinner", "snack"]))

    def test_dinners_only_no_repeats(self):
        f = parse_constraints_regex("Give me a week of dinners only, no repeats, around 40g protein each.")
        self.assertEqual((f["days"], f["meal_types"]), (7, ["dinner"]))
        self.assertNotIn("excluded_ingredients", f)

    def test_dont_eat(self):
        f = parse_constraints_regex("Vegetarian plan for the week, I don't eat paneer, and I want at least 130g protein and no more than 1800 calories.")
        self.assertEqual((f["excluded_ingredients"], f["protein_g_min_per_day"], f["calories_max_per_day"]), (["paneer"], 130, 1800))

    def test_no_snacks(self):
        f = parse_constraints_regex("3 days, no snacks")
        self.assertEqual(f["meal_types"], ["breakfast", "lunch", "dinner"])

    def test_unsupported_requests_are_surfaced_not_ignored(self):
        c, notes = parse_constraints("5 days vegan and gluten free")
        self.assertIn("vegan", c["unsupported"])
        self.assertTrue(any("NOT enforced" in n for n in notes))

    def test_llm_only_fills_gaps_regex_missed(self):
        llm = ScriptedClient([LLMReply(json.dumps({"days": 3, "protein_g_min_per_day": 999, "meal_types": ["dinner"]}))])
        c, notes = parse_constraints("Give me 90g of protein", llm)       # regex finds protein=90, LLM must not override it
        self.assertEqual((c["protein_g_min_per_day"], c["days"], c["meal_types"]), (90, 3, ["dinner"]))
        self.assertTrue(any("language model" in n for n in notes))

    def test_inline_json_tool_call(self):
        tc = _inline_call('Sure! {"name": "check_plan", "arguments": {}}')
        self.assertEqual((tc.name, tc.args), ("check_plan", {}))
        self.assertIsNone(_inline_call("all done"))


class TestAgentLoop(Base):
    REQ_1_DAY = "Plan 1 day of vegetarian meals with at least 135g of protein and under 2000 calories."

    def test_one_day_with_error_recovery_and_fix(self):
        script = [
            call("search_recipes", meal_type="breakfast"),
            call("get_recipe_macros", recipe_id="tofu-scramble-toast"),
            call("set_meal", meal_type="breakfast", recipe_id="tofu-scramble-toast"),
            call("set_meal", meal_type="lunch", recipe_id="protein-oats-upma"),          # wrong slot -> error
            call("set_meal", meal_type="lunch", recipe_id="soya-chunks-matar-curry"),
            call("set_meal", meal_type="dinner", recipe_id="paneer-bhurji-roti"),
            call("set_meal", meal_type="snack", recipe_id="roasted-soya-nuts"),
            call("check_plan"),                                                          # ~130.4 g: short
            call("set_meal", meal_type="snack", recipe_id="roasted-soya-nuts", servings=1.5),
            call("check_plan"),                                                          # ok -> Python stops the loop
        ]
        client = ScriptedClient(script)
        agent = MealPlanningAgent(client, self.bank(), llm_parse=False, repair_rounds=0)
        res = agent.plan(self.REQ_1_DAY)
        self.assertTrue(res["constraints_met"])
        day = res["days"][0]
        self.assertEqual(day["meals"]["snack"]["servings"], 1.5)
        self.assertAlmostEqual(day["totals"]["protein_g"], 33.0 + 42.9 + 38.7 + 15.8 * 1.5, delta=0.5)
        self.assertEqual(client.replies, [])                                            # consumed the whole script, no more
        actions = [t["action"]["tool"] for t in res["trace"]]
        self.assertEqual(actions.count("check_plan"), 2)
        err = next(t for t in res["trace"] if t["action"]["tool"] == "set_meal" and t["observation"].get("ok") is False)
        self.assertIn("breakfast recipe", err["observation"]["error"])
        first_check = next(t for t in res["trace"] if t["action"]["tool"] == "check_plan")["observation"]
        self.assertFalse(first_check["ok"])
        self.assertGreater(first_check["protein_short_by_g"], 0)

    def test_two_days_enforce_repeat_rule_and_weekly_summary(self):
        script = [
            call("set_meal", meal_type="breakfast", recipe_id="tofu-scramble-toast"),
            call("set_meal", meal_type="lunch", recipe_id="soya-chunks-matar-curry"),
            call("set_meal", meal_type="dinner", recipe_id="paneer-bhurji-roti"),
            call("check_plan"),
            call("set_meal", meal_type="breakfast", recipe_id="tofu-scramble-toast"),   # repeat -> error
            call("search_recipes", meal_type="breakfast"),
            call("set_meal", meal_type="breakfast", recipe_id="protein-oats-upma"),
            call("set_meal", meal_type="lunch", recipe_id="kadhai-tofu-quinoa"),
            call("set_meal", meal_type="dinner", recipe_id="soya-tofu-stir-fry"),
            call("check_plan"),
        ]
        res = self.agent(script).plan("Plan 2 days of breakfast, lunch and dinner with at least 100g of protein")
        self.assertTrue(res["constraints_met"], res["violations"])
        trace = res["trace"]
        repeat_err = next(t for t in trace if t["day"] == 2 and t["action"]["tool"] == "set_meal")["observation"]
        self.assertIn("already used on day 1", repeat_err["error"])
        search = next(t for t in trace if t["day"] == 2 and t["action"]["tool"] == "search_recipes")["observation"]
        self.assertEqual([r["recipe_id"] for r in search["recipes"]], ["protein-oats-upma"])
        self.assertAlmostEqual(res["weekly"]["avg_protein_g_per_day"], (114.6 + 120.2) / 2, delta=0.5)

    def test_impossible_target_is_reported_honestly(self):
        script = [call("set_meal", meal_type="breakfast", recipe_id="tofu-scramble-toast"),
                  call("set_meal", meal_type="lunch", recipe_id="soya-chunks-matar-curry"),
                  call("set_meal", meal_type="dinner", recipe_id="paneer-bhurji-roti"),
                  call("check_plan")]
        res = self.agent(script).plan("1 day, breakfast lunch dinner, at least 400g of protein")
        self.assertFalse(res["constraints_met"])
        self.assertTrue(any("protein" in v for v in res["violations"]))
        self.assertFalse(res["days"][0]["constraints_met"])
        self.assertEqual(len(res["days"][0]["meals"]), 3)                  # best attempt is kept

    def test_model_that_never_calls_tools_does_not_crash_or_loop_forever(self):
        client = ScriptedClient([])
        res = MealPlanningAgent(client, self.bank(), llm_parse=False, repair_rounds=0).plan("1 day of dinners only")
        self.assertFalse(res["constraints_met"])
        self.assertLessEqual(len(client.seen), 3)                          # initial + 2 nudges, then stops

    def test_step_cap(self):
        script = [call("search_recipes", meal_type="lunch")] * 50
        client = ScriptedClient(script)
        MealPlanningAgent(client, self.bank(), max_steps=4, llm_parse=False, repair_rounds=0).plan("1 day of lunches only")
        self.assertEqual(len(client.replies), 46)

    def test_repair_round_reruns_failed_days(self):
        script = [call("set_meal", meal_type="dinner", recipe_id="paneer-bhurji-roti"), call("check_plan"),      # fails (<60g)
                  call("set_meal", meal_type="dinner", recipe_id="paneer-bhurji-roti", servings=2), call("check_plan")]
        agent = MealPlanningAgent(ScriptedClient(script), self.bank(), llm_parse=False, repair_rounds=1)
        res = agent.plan("1 day of dinners only with at least 60g of protein")
        self.assertTrue(res["constraints_met"])
        self.assertEqual(res["days"][0]["meals"]["dinner"]["servings"], 2)


if __name__ == "__main__":
    unittest.main()