ISSUE #14: FIRST-PHASE SINGLE-AGENT PLANNER STARTER

This is a baseline, not a completed LLM tool-calling agent.
It reuses the existing repository's scripts/ingredient_matching.py
calculate_recipe_macros() function and cleaned USDA CSV. No mock macro
numbers are used in actual planning. The tests use synthetic fixture
numbers only to test planner logic.

SETUP
1. Clone the team repository, or open your existing local clone.
2. Create your own branch from your teammate's feature branch:
   git fetch origin
   git switch -c feat/single-agent-planner origin/feat/deterministic-nutrition-math-engine
3. Copy single_agent_planner.py and test_single_agent_planner.py into
   the repository root, next to recipes.json.
4. Install pandas if needed: python -m pip install pandas
5. Run unit tests: python -m unittest test_single_agent_planner -v
6. Run: python single_agent_planner.py --protein 140 --calories 2000
7. Review meal_plan_output.json, particularly excluded_recipes and
   all_days_valid. False is NOT a successful nutrition plan.

OPTIONAL LLM EXPERIMENT
   python -m pip install openai
   Set OPENAI_API_KEY in your environment.
   python single_agent_planner.py --llm
This optional mode is a simple LLM recipe selection experiment, not
full tool-calling orchestration. The seven-day plan is deterministic.

INTEGRATION AFTER TEAMMATE FINISHES
Replace the catalog() call to matcher.calculate_recipe_macros(recipe)
with the finalized engine's public function, adapting its inputs and
outputs. Do not copy or rewrite the engine's calculation logic.

KNOWN BLOCKERS
- Unresolved ingredients and quantities in recipes.json are excluded.
- Recipe matching may require human verification of USDA FDC matches.
- No dynamic ingredient quantity optimization, vector DB, or multi-agent.
- The optional LLM mode is not yet a full tool-calling loop.
- Strictly fewer than 2000 calories is checked; no target guarantee.
- Repetition across 48 hours is deferred to the later milestone.
