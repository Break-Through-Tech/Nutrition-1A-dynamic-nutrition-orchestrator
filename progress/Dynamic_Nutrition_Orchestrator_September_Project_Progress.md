# Dynamic Nutrition Orchestrator: Project Progress

## September: Architecture, Data Pipelines & Deterministic Baseline

For September, we are focusing on the first-phase prototype described in the challenge: a fixed set of recipes, local USDA nutrition data, keyword/NLP ingredient matching, deterministic macro calculations, and a single-agent workflow that can generate daily and weekly meal plans.

---

## Task 1: Build the Local Recipe Seed Database

**Owner:**  
**Status:** 🟡 In Progress

### Goal

Create a local, structured dataset from the provided recipe and ingredient seed data so that recipes can be used by the nutrition orchestrator.

### Work Completed

- Reviewed and structured the provided recipe/ingredient data.
- Began organizing recipe information into a format that can be used programmatically.
- Established the need to separate:
  - Recipe information
  - Individual recipe ingredients
  - Ingredient quantities and units
  - USDA food identifiers
  - Nutrition information

### Remaining Work

- Finalize the normalized recipe representation.
- Store ingredient quantities and units consistently.
- Connect recipe ingredients to their corresponding USDA `fdc_id`.
- Make sure the local recipe dataset can be queried by the nutrition calculation system.

---

## Task 2: Integrate USDA FoodData Central Data

**Owner:**  
**Status:** 🟡 In Progress

### Goal

Create a local USDA nutrition dataset that can be queried by the nutrition system instead of repeatedly depending on external API calls.

### Work Completed

We have a USDA data ingestion and cleaning pipeline in `cleaningScripts/cleaning_food.py`.

The pipeline:

- Queries the USDA FoodData Central API.
- Retrieves food records from relevant USDA data types.
- Extracts USDA `fdc_id`.
- Extracts food descriptions and metadata.
- Extracts important nutrient values.
- Standardizes nutrition fields.
- Produces cleaned local CSV data.

The cleaned nutrition dataset contains:

```text
fdc_id
data_type
description
food_category_id
publication_date
calories_kcal
protein_g
fat_g
carbs_g
fiber_g
sugars_g
sodium_mg
potassium_mg
calcium_mg
iron_mg
```

This gives us the nutrition data foundation needed for the deterministic macro calculator.

### Remaining Work

- Make the local USDA dataset the primary lookup source for the prototype.
- Document the exact dataset/version used for evaluation.
- Make the ingestion process reproducible.
- Keep API credentials outside committed source code.

---

## Task 3: Build the Deterministic Macro Calculation Engine

**Owner:**  
**Status:** 🟡 In Progress

### Goal

Create a deterministic nutrition calculation tool for calories, protein, carbs, fat, and other nutrients without relying on the LLM to do the arithmetic.

### Required Calculation

For an ingredient with USDA nutrition listed per 100g:

```text
nutrient_total =
    nutrient_per_100g * ingredient_weight_g / 100
```

For a recipe:

```text
recipe_nutrient =
    sum of ingredient nutrient totals
```

For a meal plan:

```text
daily_nutrient =
    sum of recipe/meal nutrient totals
```

The engine should:

1. Receive identified ingredients.
2. Retrieve USDA nutrition information.
3. Convert the requested quantity to grams.
4. Scale USDA nutrition by quantity.
5. Sum nutrition across ingredients.
6. Produce daily totals.
7. Produce weekly totals for a seven-day plan.

### Main Design Rule

The LLM should not perform the final nutrition arithmetic. The LLM/NLP side can interpret the recipe and identify ingredients, while deterministic code handles the actual calculations.

---
## Task 4: Normalize Ingredient Quantities and Units

**Owner:**
**Status:** 🟡 In Progress

### Goal

Convert the quantities in the recipe dataset into consistent, calculation-ready measurements for the deterministic macro engine.

The recipe dataset already stores:

```text
recipe_id | ingredient_name | quantity | unit
```

This task focuses on making those quantities usable for nutrition calculations.

### Work Includes

* Preserve the existing `quantity` and `unit` from the recipe dataset.
* Normalize standard units such as `g`, `tsp`, `tbsp`, `slice`, and `small`.
* Use USDA portion and measurement data where available to convert non-gram quantities into grams.
* Identify ambiguous units such as `servings`.
* Define consistent handling for ingredients where a direct gram conversion is unavailable.
* Produce a final `amount_g` value that can be passed to the deterministic macro calculator.

### Example

```text
recipe_id | ingredient_name | quantity | unit | amount_g
S1-R01    | Oats            | 50       | g    | 50
S1-R01    | Yogurt          | 150      | g    | 150
S1-R01    | Mustard seeds   | 0.25     | tsp  | X
S1-R01    | Oil             | 1        | tsp  | X
```

The main output of this task is a consistent gram-based quantity that the macro calculation engine can use.

---

## Task 5: Implement Keyword/NLP Ingredient Matching

**Owner:**  
**Status:** ⬜ To Do

### Goal

Allow the system to take a natural-language recipe ingredient and identify the correct USDA food record.

The user should NOT need to know or provide the `fdc_id`.

Example:

```text
"paneer"
```

becomes:

```text
ingredient -> USDA candidate search -> best match -> fdc_id
```

The `fdc_id` is an internal identifier used by the nutrition engine.

### First-Phase Approach

The first phase uses:

- NLP/keyword-based matching
- Local USDA ingredient data
- Existing recipes

The system should retrieve candidate USDA foods using text/keyword matching and select the best match.

### Evaluation Requirement

Eventually, entity resolution should reach:

`F1 > 90%`

on an unseen validation set of 30 common Indian vegetarian ingredients.

---

## Task 6: Connect Ingredient Resolution to the Macro Tool

**Owner:**  
**Status:** ⬜ To Do

### Goal

Connect ingredient matching to the deterministic nutrition engine.

Flow:

```text
Recipe
    ->
Ingredient + Quantity Extraction
    ->
Keyword/NLP Ingredient Matching
    ->
USDA fdc_id
    ->
Nutrition Lookup
    ->
Quantity to Grams
    ->
Deterministic Macro Calculation
    ->
Recipe / Meal Macros
```

This is the main integration point between ingredient matching and deterministic nutrition calculation.

---

## Task 7: Build the First-Phase Single-Agent Meal Planner

**Owner:**  
**Status:** ⬜ To Do

### Goal

Build the initial single-agent prototype described in the challenge.

Example inputs:

```text
Protein target: 140g/day
Calories: <2,000 kcal/day
Diet: vegetarian
```

The planner should use the fixed recipe set to construct a meal plan.

### First-Phase Requirements

1. Accept user nutrition requirements.
2. Access the local recipe database.
3. Select recipes.
4. Resolve recipe ingredients to USDA foods.
5. Call the macro calculation tool.
6. Calculate daily nutrition totals.
7. Produce a daily meal plan.
8. Extend the plan to a weekly meal plan.

Single-agent is the September baseline.

---

## Task 8: Define Evaluation Benchmarks

**Owner:**  
**Status:** 🟡 Defined

### Goal

Define measurable benchmarks for the deterministic baseline.

Challenge success criteria:

### 1. Macro Optimization Precision

Target:

`MAE < 2%`

Example: 140g protein/day means the result should be between 137.2g and 142.8g.

### 2. Entity Resolution Accuracy

Target:

`F1 > 90%`

on an unseen validation set of 30 common Indian vegetarian ingredients.

### 3. Scheduling Constraint Adherence

Target:

`100% compliance`

with the specified ingredient-repeat constraints across consecutive 48-hour periods.

For the September baseline, the main goal is to define these metrics and prepare the evaluation datasets and test cases.

---

# Current September Progress Summary

| Task | Owner | Status |
|---|---|---|
| Local recipe seed database | | 🟡 In Progress |
| USDA FoodData Central integration | | 🟡 In Progress |
| Deterministic macro calculation engine | | 🟡 In Progress |
| Ingredient quantity/unit handling | | 🟡 In Progress |
| Keyword/NLP ingredient matching | | ⬜ To Do |
| Ingredient matching -> macro tool integration | | ⬜ To Do |
| First-phase single-agent meal planner | | ⬜ To Do |
| Evaluation benchmarks | | 🟡 Defined |

---
