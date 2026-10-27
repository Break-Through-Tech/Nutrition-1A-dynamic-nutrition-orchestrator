# Dynamic Nutrition Orchestrator

An AI-powered nutrition workflow that transforms recipes and ingredient quantities into structured nutritional data using USDA FoodData Central and a deterministic macro-calculation engine.

---

## Team Members

| Name | GitHub Handle | Contributions |
|---|---|---|
| Prisha Goyal | [@PGoyal224](https://github.com/PGoyal224) | Data exploration, preprocessing, ingredient keyword matching |
| Asha Thomas | [@jramirez](https://github.com/jramirez) | Data exploration, preprocessing, ingredient seed database development |
| Trang Hoang | [@aminahassan](https://github.com/aminahassan) | Data exploration, preprocessing, orchestrator agent development |
| Chandana Robba | [@pmehta](https://github.com/pmehta) | Data exploration, macro calculator development and tuning |

---

## Project Highlights

- Developed a structured ingredient catalog with canonical ingredient names, aliases, categories, and USDA FoodData Central identifiers.
- Built a data-processing workflow to prepare USDA food records and nutrient information for downstream calculations.
- Implemented ingredient keyword matching to connect recipe ingredients with corresponding food database entries.
- Developed a deterministic nutrition-calculation workflow that uses ingredient quantities to calculate nutritional information.
- Designed an orchestration workflow to connect recipe data, ingredient identification, and macro calculations into a unified pipeline.

## Project Overview

The Dynamic Nutrition Orchestrator is a Break Through Tech AI Studio Challenge project focused on generating personalized meal plans based on users' dietary restrictions and macronutrient targets.

Planning meals that satisfy specific dietary needs while meeting daily protein, carbohydrate, fat, and calorie goals can be challenging and time-consuming. Our project addresses this challenge by coordinating recipe selection, ingredient identification, and nutritional calculations to create meal plans tailored to individual requirements.

The system integrates structured recipe and ingredient data with USDA FoodData Central to estimate nutritional content and evaluate meals against user-defined goals. Through ingredient matching, deterministic macro calculations, and an orchestration workflow, the Dynamic Nutrition Orchestrator aims to make personalized meal planning more accessible, consistent, and efficient.

### Project Objectives

- **Personalized meal planning:** Generate meal plans aligned with users' dietary restrictions and nutritional preferences.
- **Macronutrient targeting:** Select and evaluate meals against user-defined calorie, protein, carbohydrate, and fat targets.
- **Ingredient identification:** Match recipe ingredients and their aliases to standardized ingredient records.
- **Nutrition data integration:** Use USDA FoodData Central to obtain food composition data for nutritional calculations.
- **Meal plan orchestration:** Coordinate recipe selection, ingredient resolution, and macro calculations to support cohesive meal plans.
- **Dietary compatibility:** Account for dietary restrictions when selecting recipes and ingredients.

## Data Exploration and Preprocessing

### Data Sources

**USDA FoodData Central**

The project uses USDA FoodData Central as its primary source of food composition and nutrient information. The local dataset-generation workflow retrieves food records from the following data types:

- Foundation Foods
- SR Legacy
- Survey (FNDDS)

The raw dataset includes food identifiers, descriptions, data types, food category information, publication dates, and available nutrient values.

### Data Processing

The data preparation workflow includes:

1. Retrieving food records from the USDA FoodData Central API.
2. Extracting food metadata and available nutrient information.
3. Organizing nutrient values into columns for downstream processing.
4. Selecting relevant nutrient fields, including energy, protein, fat, carbohydrates, fiber, sugars, sodium, potassium, calcium, and iron.
5. Standardizing food descriptions and preparing a cleaned CSV for ingredient lookup and macro calculations.

### Ingredient Catalog

The project maintains a structured ingredient seed database containing:

- Canonical ingredient names and categories.
- Alternative names and aliases for ingredient matching.
- USDA FoodData Central identifiers, where resolved.
- Recipe definitions, ingredient quantities, and preparation instructions.
- Recipe-to-ingredient relationships and meal-planning metadata.

The catalog includes ingredients such as tofu, paneer, soya chunks, oats, Greek yogurt, brown rice, green peas, whole wheat flour, and other foods used in vegetarian meal plans.

### Data Challenges

Key challenges include differences between recipe ingredient names and USDA food descriptions, regional ingredient terminology, variations in food preparation, and the availability of exact nutritional matches.

Ingredient matching requires more than exact string comparisons. Candidate food records must be evaluated for nutritional relevance, preparation state, and suitability for the intended calculation.

## System Development

### Ingredient Matching

The ingredient-matching component uses canonical names and aliases to identify candidate food records for recipe ingredients. This helps account for differences in terminology and formatting between recipes and the USDA dataset.

When an exact match is unavailable, alternative search terms and candidate records can be evaluated before assigning an FDC identifier.

### Macro Calculator

The macro calculator uses ingredient quantities and corresponding nutrient data to calculate nutritional values.

For a nutrient reported per 100 grams, the calculation for an ingredient is:

$$
\text{Nutrient amount}
=
\frac{\text{Ingredient quantity (g)}}{100}
\times
\text{Nutrient value per 100 g}
$$

Nutrient totals can then be aggregated across the ingredients in a recipe.

Accurate calculations depend on appropriate food-record selection, consistent units, and the availability of the relevant nutrient values.

### Orchestrator Agent

The orchestrator coordinates the workflow between structured recipe data, ingredient identification, and nutrition calculations. Its role is to connect the individual components so that recipe inputs can be processed through a consistent pipeline.

The project combines ingredient matching with deterministic calculations, separating food identification from the arithmetic used to compute nutritional values.

## Results and Key Findings

The project establishes a structured workflow for translating recipe data into ingredient-level nutritional calculations.

Key development outcomes include:

- A standardized ingredient catalog designed to support reusable ingredient identification.
- A USDA-based food dataset containing food descriptions, identifiers, and selected nutrient fields.
- An alias-based ingredient-matching approach to address naming inconsistencies.
- A deterministic calculation method for deriving nutrient amounts from ingredient quantities.
- An orchestration architecture that connects ingredient resolution and nutritional calculations.

**Evaluation status:** Quantitative performance metrics, ingredient-matching coverage, and macro-calculation accuracy should be added after validation against verified food records and reference nutrition calculations.

## Limitations

- Not every ingredient has an exact match in USDA FoodData Central.
- Regional foods and specialized products may require alternative records or additional nutrition sources.
- Similar food descriptions may represent different preparation methods or nutrient profiles.
- Missing nutrient values require careful handling to avoid treating unknown values as genuine zeros.
- Ingredient matching and macro calculations depend on the quality of the source data and the correctness of ingredient quantities and units.

## Next Steps

- Improve ingredient matching through normalized text, expanded aliases, and candidate ranking.
- Resolve and validate FDC identifiers for the ingredient seed database.
- Expand food coverage for specialized and regionally named ingredients.
- Validate calculated nutrient totals against trusted reference values.
- Evaluate ingredient-matching coverage and accuracy using a manually verified test set.
- Improve handling of missing nutrient values and ambiguous food records.
- Extend testing across additional recipes, serving sizes, and unit conversions.

## References

- [USDA FoodData Central](https://fdc.nal.usda.gov/) - Food composition data and nutrition information.
- [USDA FoodData Central API Guide](https://fdc.nal.usda.gov/api-guide.html) - API documentation and data retrieval.

## Acknowledgements

We thank Break Through Tech AI, our AI Studio Challenge Advisor, and the project mentors and teaching staff for their guidance and support throughout the development of the Dynamic Nutrition Orchestrator.
