# ReAct Meal Planner Agent

Tell the agent what you want ("7 days, vegetarian, at least 120g protein, under 2000 calories") and it builds a daily and weekly meal plan from our fixed list of recipes.

**The idea in three lines**
- A small AI model running on your laptop (through Ollama) picks the recipes.
- The model never does nutrition math. A normal Python tool calculates every number.
- Plain Python code checks each plan against your limits, so a plan is either checked or clearly marked as failed.

This is Phase 1 only: no multi-agent setup, no vector database, and no made-up recipes.

## How it works

```
SETUP (do once, and again whenever recipes or food choices change)
  agent_data/recipes.json + clean_usda_foods.csv + fdc_overrides.json
      └─► build_normalized_recipe.py ─► agent_data/recipes_normalized.json (+ match_review.csv)

RUNNING THE AGENT
  user input ─► run_agent.py (or server.py) ─► meal_agent.py   (the ReAct loop, talks to Ollama)
                                                  └─► agent_tools.py   (tools + the rules)
                                                         ├─► food_db.py      (nutrients for each food)
                                                         └─► math_engine.py  (the macro math)
```

For each day the agent repeats this: **pick a tool → Python runs it → the agent reads the result**. It stops when the day passes the check or runs out of steps. If it can't hit your targets, it says so instead of pretending. A 7-day plan is seven checked days plus a weekly summary.

Tools the model can use: `search_recipes`, `get_recipe_macros`, `set_meal`, `clear_meal`, `check_plan`, `match_ingredient`.

## Contents of React_Agent Folder

- **Run it:** `run_agent.py` (command line), `server.py` + `index.html` (website)
- **The agent:** `meal_agent.py` (the loop), `agent_tools.py` (tools and rules), `food_db.py` (looks up nutrients)
- **Recipe setup:** `build_normalized_recipe.py` (does the setup), `ingredient_registry.py` (ingredient lookup table: USDA search text, unit-to-gram conversions, which spices to skip)
- **Our teammates' code (copies):** `ingredient_matching.py`, `math_engine.py`
- **Our choices:** `fdc_overrides.json` (which USDA food to use, e.g. `"onion": 170000`)
- **Checks:** `check_foods.py`, `macro_table.py`
- **Tests:** `test_meal_agent.py`, `test_fixtures.py` (the fixtures use fake nutrient numbers)

## Setup (once)

You need Python 3.10+, the free [Ollama](https://ollama.com/download) app, and about 5 GB of free space for the model.

```bash
pip3 install pandas ollama flask     # flask is only for the website
ollama pull qwen2.5:3b-instruct      # use qwen2.5:7b-instruct if your laptop has the RAM
ollama list                          # your model should show up here
```

Your folders should look like this. Run everything from inside `React_Agent`:

```
Nutrition-1A-dynamic-nutrition-orchestrator/
├── cleanedData/clean_usda_foods.csv
└── React_Agent/
    ├── agent_data/recipes.json
    └── (the files above)
```

### Build the recipe data

```bash
python3 build_normalized_recipe.py \
  --recipes agent_data/recipes.json \
  --foods ../cleanedData/clean_usda_foods.csv \
  --fdc-overrides fdc_overrides.json \
  --out agent_data/recipes_normalized.json \
  --review agent_data/match_review.csv
```

It prints how many recipes are usable and why the others aren't. It also writes two files:
- `recipes_normalized.json`: what the agent reads.
- `match_review.csv`: the top 3 USDA matches for each ingredient. **Look through it.** When matches tie, the first one wins, and that has been wrong before (green onion instead of onion, hot chocolate mix instead of milk).

Note: if the script can't find `fdc_overrides.json`, it skips it without telling you. If your fixes seem ignored, check the path.

### Check the data (after every rebuild)

```bash
python3 check_foods.py     # flags foods with suspicious calories
python3 macro_table.py     # protein and calories for every usable recipe
```

Some rows in our USDA file have **0 calories stored** (usually IDs starting with 25 or 27). `check_foods.py` marks them `<-- CHECK`. To fix one, add a better ID to `fdc_overrides.json` and rebuild. Don't trust any calorie totals until nothing is flagged.

## Run it

```bash
python3 run_agent.py "Plan 1 day of vegetarian meals with at least 140g of protein and under 2000 calories." \
  --foods ../cleanedData/clean_usda_foods.csv --model qwen2.5:3b-instruct \
  --no-llm-parse --max-steps 20 --verbose --trace trace.json
```

- `--verbose` shows each tool call as it happens.
- `--trace trace.json` saves every step the agent took.
- `--no-llm-parse` reads your request with simple pattern matching, which is more reliable on small models.
- Start with 1 day. A 7-day run takes much longer.

**What you can ask for:** number of days, which meals (breakfast, lunch, dinner, snack), a protein minimum, a calorie maximum, a diet tag (`vegetarian`, `kid-friendly`), foods to avoid ("no tofu or soy"), and whether recipes can repeat. Anything you leave out gets a default (7 days, all four meals, no repeats within 2 days), and the output tells you which defaults it used. Things we can't check (vegan, gluten-free, keto) are flagged as "not enforced", not silently ignored.

### Website 

```bash
python3 server.py --foods ../cleanedData/clean_usda_foods.csv
```

Open **http://localhost:8000**, pick an example, press *Plan meals*, and wait. You'll see each day's meals, protein and calorie bars, pass/fail checks, and the agent's steps. *Download trace.json* saves the run. 

## Changing things

- **Pick a different USDA food:** add it to `fdc_overrides.json` as `{"ingredient_id": fdc_id}`. It always beats the automatic match. Ingredient IDs are in `ingredient_registry.py` and `match_review.csv`.
- **Use a nutrition label instead of USDA** (good for paneer and soya chunks): put the per-100g label values in `agent_data/nutrient_overrides.json`:
  ```json
  {"soya_chunks": {"source": "label of <brand>",
                   "per_100g": {"calories_kcal": <kcal>, "protein_g": <g>, "fat_g": <g>, "carbs_g": <g>}}}
  ```
  Replace every `<...>` with a real number. Never leave a placeholder 0, because the code treats a 0 as a real value.
- **Change gram conversions or assumptions** (like 1 tsp oil = 4.5 g, or which spices to skip): edit `ingredient_registry.py`. These are typical values, not checked ones.
- **Add or edit a recipe:** change `agent_data/recipes.json`, rebuild, then run both checks.

After any change, rebuild first so the agent sees it.

## Tests

```bash
python3 -m unittest test_meal_agent -v
```

You should see `Ran 43 tests` and `OK`. They use a scripted fake model, so you don't need Ollama. The nutrient numbers in the tests are made up, so they check that the code works, not that the nutrition is right.

## Known problems

- **Only 20 of 26 recipes are usable.** Two urad dal recipes have no matching USDA food, and four recipes list a real food with no amount (paratha, tortilla and corn, jeera-rice basmati, mixed dals). To fix them, add grams to `recipes.json` or find a matching food.
- **Some numbers are rough.** USDA's paneer is probably full-fat, but our recipes say low-fat. "Soy protein concentrate" stands in for soya chunks and likely makes protein look too high. Whey and edamame are generic matches. Label overrides fix this.
- **Batch recipes assume 4 servings,** and the source isn't clear about that. `soya-tofu-stir-fry-batch` comes out around 103g protein per serving, so it takes over plans. Confirm the real serving count.
- **Small models get confused.** A 3B model may retry a lot or leave a day unfinished. A 7B model is better. Failed days are reported, never hidden.
- **The website waits for the whole run.** It doesn't show live steps, and it only runs one plan at a time. (It may take a little while to run.)

## Stuck?

| What you see | What to do |
|---|---|
| `No module named 'scripts'` or `'nutrition_engine'` | An import still points at the old folder. In `food_db.py` and `build_normalized_recipe.py` use `import ingredient_matching as im`. In `agent_tools.py` use `from math_engine import ...` |
| `No module named 'agent_tools'` (or another of our files) | You're not inside `React_Agent`, or that file is missing |
| `Failed to connect to Ollama` | Open the Ollama app (llama icon in the menu bar) or run `ollama serve` |
| `command not found: ollama` | Install it from ollama.com/download, then open a new terminal |
| `model not found` | The name after `--model` has to match `ollama list` exactly |
| `No such file: agent_data/recipes_normalized.json` | Run the build step |
| Agent never calls a tool, or loops | Try the 7B model, raise `--max-steps`, and share the `trace.json` |
| Port already in use | `python3 server.py --port 8001 ...` |

## Team notes

- `ingredient_matching.py` and `math_engine.py` in this folder are **copies**. If the originals change, copy them again.
- Do commit: the code, `fdc_overrides.json`, `nutrient_overrides.json`, and `agent_data/recipes_normalized.json`.
- Don't commit: `__pycache__/`, `.DS_Store`, or the raw USDA download files.

## Progress (update as you go)

- [x] Recipe setup and USDA matching
- [x] Macro tool connected, data checks pass
- [x] Agent loop and tools built, tests pass (with a fake model)
- [ ] Ran end to end with a real Ollama model (1 day)
- [ ] Ran a 7-day plan
- [ ] Added paneer and soya label values
- [ ] Confirmed batch-recipe serving counts