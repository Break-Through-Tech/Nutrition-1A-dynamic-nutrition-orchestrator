# Ingredient Matching

## 1. Overview

The `ingredient_matching.py` module contains functionality for:

- Loading and preprocessing USDA FoodData Central records.
- Normalizing ingredient names and food descriptions.
- Extracting keywords from text.
- Scoring and ranking food candidates.
- Assigning confidence labels to matching scores.
- Searching the USDA FoodData Central API.
- Retrieving and normalizing USDA nutrient information.
- Converting ingredient quantities into grams.
- Calculating recipe nutrient totals.
- Preparing recipe ingredients for the deterministic math engine.
- Retrieving USDA FDC IDs for recipe ingredients.

The module uses Pandas to process local USDA data and Requests to communicate with the USDA FoodData Central API.

---

## 2. Configuration and Constants

### 2.1 File Paths and API Configuration

The local USDA dataset is loaded from:

`cleanedData/clean_usda_foods.csv`

The path is constructed relative to the location of `ingredient_matching.py`.

The USDA API base URL is:

`https://api.nal.usda.gov/fdc/v1`

The API key is retrieved from the `API_KEY` environment variable.

### 2.2 Nutrient Fields

The `NUTRIENTS` list defines the nutrient fields used throughout the module:

| Field | Description |
|---|---|
| `calories_kcal` | Calories in kilocalories |
| `protein_g` | Protein in grams |
| `fat_g` | Fat in grams |
| `carbs_g` | Carbohydrates in grams |
| `fiber_g` | Fiber in grams |
| `sugars_g` | Sugars in grams |
| `sodium_mg` | Sodium in milligrams |
| `potassium_mg` | Potassium in milligrams |
| `calcium_mg` | Calcium in milligrams |
| `iron_mg` | Iron in milligrams |

These fields are used when loading local food records, processing API nutrient data, and calculating recipe totals.

### 2.3 Matching Thresholds

The module defines three matching thresholds:

| Constant | Value |
|---|---:|
| `MIN_MATCH_SCORE` | 0.35 |
| `MEDIUM_CONFIDENCE_SCORE` | 0.60 |
| `HIGH_CONFIDENCE_SCORE` | 0.80 |

These thresholds are used by the matching and recipe-processing functions.

### 2.4 Stop Words

`STOP_WORDS` contains words removed during tokenization:

- a
- an
- the
- and
- of
- with
- for
- to
- in
- on
- from
- about

### 2.5 Preparation Words

`PREPARATION_WORDS` contains preparation-related terms:

- chopped
- diced
- minced
- sliced
- grated
- shredded
- cubed
- crushed
- finely
- roughly
- thinly
- thickly
- peeled
- halved
- quartered

These words can be removed from ingredient keywords by calling `tokenize()` with `remove_preparation=True`.

### 2.6 Form Qualifiers

`FORM_QUALIFIERS` contains terms used when scoring food descriptions:

- dried
- dehydrated
- powder
- powdered
- white
- yolk
- pickled
- smoked
- salted
- unsalted
- frozen
- canned
- concentrated
- extract
- juice
- oil
- sauce
- paste

These terms are used to calculate penalties for unrequested food forms.

### 2.7 Prepared Product Terms

`PREPARED_PRODUCT_TERMS` contains terms associated with prepared food descriptions:

- bread
- bagel
- sandwich
- burrito
- quesadilla
- taquito
- pizza
- salad
- soup
- dip
- casserole
- stuffing
- noodle
- pasta
- cracker
- chip
- ring
- burger
- sushi
- benedict
- deviled
- omelet
- omelette
- pancake
- waffle
- cookie
- cake
- pie
- pastry
- muffin
- snack
- gravy
- dressing
- spread
- topping
- candy
- dessert
- custard

These terms are used when calculating candidate scores.

---

## 3. Text Normalization and Tokenization

### 3.1 `normalize_text(text)`

Converts text into a standardized format.

Operations include:

1. Returns an empty string when the input is missing.
2. Converts the input to lowercase.
3. Removes leading and trailing whitespace.
4. Replaces common wording variations.
5. Removes punctuation while retaining letters, numbers, and whitespace.
6. Replaces consecutive whitespace with a single space.

The replacement dictionary includes:

| Original | Replacement |
|---|---|
| all-purpose | all purpose |
| self-rising | self rising |
| extra-virgin | extra virgin |
| tbsps | tbsp |
| tablespoons | tbsp |
| tablespoon | tbsp |
| teaspoons | tsp |
| teaspoon | tsp |
| cups | cup |
| ounces | ounce |
| pounds | pound |

### 3.2 `normalize_word(word)`

Performs conservative singularization.

The function applies the following rules:

- Words longer than four characters ending in `ies` have that ending replaced with `y`.
- Words longer than four characters ending in `s` have the final `s` removed, unless they end in `ss`, `us`, or `is`.
- Other words remain unchanged.

### 3.3 `tokenize(text, remove_preparation=False)`

Converts text into a set of normalized keywords.

The function:

1. Calls `normalize_text()`.
2. Splits the text into individual words.
3. Applies `normalize_word()` to each word.
4. Removes stop words.
5. Removes measurement units.
6. Optionally removes preparation words.
7. Stores the remaining words in a set.

The measurement units removed include:

- g
- kg
- mg
- ml
- cup
- tsp
- tbsp

When `remove_preparation=True`, words in `PREPARATION_WORDS` are also excluded.

---

## 4. Loading USDA Food Data

### `load_foods(path=FOODS_PATH)`

Loads the local USDA CSV using Pandas.

The function performs the following operations:

1. Reads the CSV into a DataFrame.
2. Checks that `fdc_id` and `description` columns exist.
3. Raises a `ValueError` if either required column is missing.
4. Replaces missing descriptions with empty strings.
5. Converts descriptions to strings.
6. Checks each nutrient field in `NUTRIENTS`.
7. Adds missing nutrient columns with `pd.NA`.
8. Converts nutrient columns to numeric values using `pd.to_numeric()` with `errors="coerce"`.
9. Creates a `tokens` column containing tokenized food descriptions.
10. Creates a `base_tokens` column containing food description tokens with preparation words removed.

The function returns the processed DataFrame.

---


## 5. Keyword Matching and Candidate Ranking

### 5.1 `score_candidate(ingredient_words, food_words, description="")`

Calculates a matching score between an ingredient and a USDA food candidate.

The scoring function considers:

- Keyword coverage.
- Primary food identity.
- Unrequested form qualifiers.
- Prepared-product terms.
- Raw and whole food descriptions.

If either keyword set is empty, or there are no matching keywords, the function returns `0.0`.

The final score is restricted to the range [0, 1].

### 5.2 Keyword Coverage

The matcher calculates the intersection between the ingredient keyword set and the food keyword set.

Coverage is calculated as:

\[
\text{Coverage} =
\frac{|\text{Ingredient Words} \cap \text{Food Words}|}
{|\text{Ingredient Words}|}
\]

The coverage contribution is:

\[
\text{Coverage Score} = 0.45 \times \text{Coverage}
\]

This rewards candidates that contain the requested ingredient keywords.

### 5.3 Primary Food Identity

USDA food descriptions are split at the first comma.

The words before the first comma are tokenized and treated as the primary description.

The matcher compares the requested ingredient keywords against this primary description.

| Condition | Score Adjustment |
|---|---:|
| All requested keywords appear in the primary description | +0.45 |
| At least one requested keyword appears in the primary description | +0.20 |
| Requested keywords appear only outside the primary description | -0.20 |

The primary description adjustment is calculated using the following conditions:

1. If all ingredient keywords are contained in the primary description, add 0.45.
2. Otherwise, if the primary description contains at least one ingredient keyword, add 0.20.
3. Otherwise, subtract 0.20.

This component distinguishes candidates whose primary description contains the requested ingredient from candidates where the ingredient appears only in a secondary portion of the description.

### 5.4 Unrequested Food Form Penalty

The matcher uses the `FORM_QUALIFIERS` set to identify food forms and characteristics.

The set contains:

- `dried`
- `dehydrated`
- `powder`
- `powdered`
- `white`
- `yolk`
- `pickled`
- `smoked`
- `salted`
- `unsalted`
- `frozen`
- `canned`
- `concentrated`
- `extract`
- `juice`
- `oil`
- `sauce`
- `paste`

The matcher identifies unrequested form qualifiers using:

```python
unwanted_forms = (
    description_words & FORM_QUALIFIERS
) - ingredient_words
```

This operation:

1. Finds form qualifiers present in the candidate description.
2. Removes qualifiers included in the requested ingredient keywords.
3. Uses the remaining qualifiers to calculate the penalty.

The penalty is:

\[
P_{\text{form}} = \min(0.20,\ 0.08n)
\]

where \(n\) is the number of unrequested form qualifiers.

The penalty is subtracted from the candidate score.

| Number of unrequested form qualifiers | Penalty |
|---:|---:|
| 0 | 0.00 |
| 1 | 0.08 |
| 2 | 0.16 |
| 3 or more | 0.20 |

The maximum form penalty is 0.20.

A form qualifier explicitly included in the ingredient request is not penalized.

### 5.5 Prepared-Product Penalty

The matcher uses the `PREPARED_PRODUCT_TERMS` set to identify terms associated with prepared food descriptions.

The set contains:

- `bread`
- `bagel`
- `sandwich`
- `burrito`
- `quesadilla`
- `taquito`
- `pizza`
- `salad`
- `soup`
- `dip`
- `casserole`
- `stuffing`
- `noodle`
- `pasta`
- `cracker`
- `chip`
- `ring`
- `burger`
- `sushi`
- `benedict`
- `deviled`
- `omelet`
- `omelette`
- `pancake`
- `waffle`
- `cookie`
- `cake`
- `pie`
- `pastry`
- `muffin`
- `snack`
- `gravy`
- `dressing`
- `spread`
- `topping`
- `candy`
- `dessert`
- `custard`

The matcher identifies unrequested prepared-product terms using:

```python
unwanted_products = (
    description_words & PREPARED_PRODUCT_TERMS
) - ingredient_words
```

This operation:

1. Finds prepared-product terms present in the candidate description.
2. Removes terms included in the requested ingredient keywords.
3. Uses the remaining terms to calculate the penalty.

The penalty is:

\[
P_{\text{prepared}} = \min(0.45,\ 0.30n)
\]

where \(n\) is the number of unrequested prepared-product terms.

The penalty is subtracted from the candidate score.

| Number of unrequested prepared-product terms | Penalty |
|---:|---:|
| 0 | 0.00 |
| 1 | 0.30 |
| 2 | 0.45 |
| 3 or more | 0.45 |

The maximum prepared-product penalty is 0.45.

### 5.6 Raw and Whole Ingredient Bonuses

The matcher checks whether the requested ingredient contains any form qualifiers:

```python
requested_form = ingredient_words & FORM_QUALIFIERS
```

If the requested ingredient does not contain any form qualifiers, the matcher applies the following adjustments:

| Description contains | Score Adjustment |
|---|---:|
| `whole` | +0.03 |
| `raw` | +0.03 |

Both adjustments can apply to the same candidate.

If the requested ingredient contains a form qualifier, these bonuses are not applied.

These adjustments increase the candidate score and are not penalties.

### 5.7 Complete Scoring Calculation

The candidate score combines keyword coverage, primary food identity, form penalties, prepared-product penalties, and raw/whole bonuses.

The calculation is:

\[
\begin{aligned}
S ={}& 0.45C + P \\
&- \min(0.20,\ 0.08F) \\
&- \min(0.45,\ 0.30D) \\
&+ R
\end{aligned}
\]

Where:

- \(S\) is the final candidate score.
- \(C\) is keyword coverage.
- \(P\) is the primary food identity adjustment.
- \(F\) is the number of unrequested form qualifiers.
- \(D\) is the number of unrequested prepared-product terms.
- \(R\) is the raw and whole ingredient bonus.

The final score is bounded:

```python
return max(0.0, min(score, 1.0))
```

Therefore:

- Scores below 0 are returned as 0.
- Scores above 1 are returned as 1.
- Scores between 0 and 1 are returned unchanged.

The form and prepared-product penalties are calculated independently. A candidate can receive both penalties when its description contains terms from both sets.

A term contributes to a penalty only when it appears in the candidate's tokenized description and is not included in the requested ingredient keywords.

### 5.8 Candidate Ranking

The `rank_food_candidates()` function applies the same scoring algorithm to local USDA records and USDA API search results.

For each candidate, the function:

1. Reads its food description.
2. Uses its existing token set when available.
3. Otherwise, tokenizes the description.
4. Calculates the candidate score.
5. Excludes candidates with scores less than or equal to zero.
6. Extracts nutrient values.
7. Records the FDC ID, data type, description, score, matched keywords, and nutrient values.

The function sorts candidates in descending order by:

1. Candidate score.
2. Whether the data type is `SR Legacy`.

SR Legacy is preferred when candidate scores are equal.

The function returns up to `top_n` candidates.

The default value of `top_n` is 10.

### 5.9 `find_top_matches(ingredient_name, foods, top_n=10)`

Returns the highest-scoring candidates from the local USDA dataset.

The function:

1. Checks whether the provided DataFrame is empty or missing.
2. Converts the DataFrame to records.
3. Calls `rank_food_candidates()`.
4. Returns the ranked candidates.

The default number of candidates returned is 10.

### 5.10 `find_best_food(ingredient_name, foods)`

Returns the highest-ranked local USDA candidate if it meets the minimum matching threshold.

The function:

1. Calls `find_top_matches()` with `top_n=1`.
2. Returns `None` if no candidates are found.
3. Checks the best candidate's score.
4. Returns `None` if the score is below `MIN_MATCH_SCORE`.
5. Otherwise, returns the best candidate.

The minimum matching threshold is 0.35.

### 5.11 `confidence_label(score)`

Converts a matching score into a confidence label.

| Score | Confidence |
|---|---|
| 0.80 or higher | High |
| 0.60 to below 0.80 | Medium |
| 0.35 to below 0.60 | Low |
| Below 0.35 | Very low |

The function returns the corresponding string.

### 5.12 `print_top_matches(ingredient_name, top_n=10, foods=None)`

Prints ranked candidate foods for inspection.

If no DataFrame is provided, the function loads the local USDA dataset.

It prints:

- The ingredient name.
- A message when no candidates are found.
- The ranked food descriptions.
- The candidate scores.
- The matched keywords.

This function is used to inspect the matching results.

## 6. Unit Conversion

This section contains the constants and functions used to convert ingredient quantities into grams.

### 6.1 `GRAMS_PER_UNIT`

`GRAMS_PER_UNIT` is a dictionary containing direct weight-to-gram conversion factors.

| Unit | Conversion to Grams |
|---|---:|
| kg | 1000 |
| g | 1 |
| gram | 1 |
| grams | 1 |
| mg | 0.001 |
| milligram | 0.001 |
| milligrams | 0.001 |

These conversions are used when an ingredient's quantity is already expressed as a unit of weight.

### 6.2 `GRAMS_PER_CUP`

`GRAMS_PER_CUP` is a dictionary containing estimated gram weights for one cup of specific ingredients.

| Ingredient | Grams per Cup |
|---|---:|
| all purpose flour | 120 |
| flour | 120 |
| whole wheat flour | 120 |
| granulated sugar | 200 |
| sugar | 200 |
| brown sugar | 220 |
| powdered sugar | 120 |
| butter | 227 |
| unsalted butter | 227 |
| salted butter | 227 |
| water | 240 |
| milk | 244 |
| whole milk | 244 |
| honey | 340 |
| olive oil | 216 |
| vegetable oil | 218 |
| rolled oats | 90 |
| oats | 90 |
| rice | 185 |
| white rice | 185 |
| chopped onion | 160 |
| onion | 160 |
| chopped tomato | 180 |
| tomato | 180 |
| shredded cheese | 113 |
| cheese | 113 |
| peanut butter | 258 |

These values are used to convert volume measurements into grams. The conversion depends on the ingredient because different ingredients have different densities.

### 6.3 `GRAMS_PER_ITEM`

`GRAMS_PER_ITEM` is a dictionary containing estimated gram weights for individual food items.

| Ingredient | Grams per Item |
|---|---:|
| egg | 50 |
| large egg | 50 |
| medium egg | 44 |
| small egg | 38 |
| onion | 150 |
| garlic clove | 3 |
| clove garlic | 3 |
| tomato | 123 |
| medium tomato | 123 |
| lemon | 58 |
| lime | 67 |
| apple | 182 |
| banana | 118 |
| carrot | 61 |
| potato | 173 |
| slice bread | 30 |
| bread slice | 30 |

These values are used when an ingredient quantity is expressed as a count rather than a weight or volume.

### 6.4 `grams_per_cup_for(ingredient_name)`

Finds the grams-per-cup conversion value for an ingredient.

**Process:**
1. Tokenizes the ingredient name.
2. Normalizes the ingredient name.
3. Sorts the keys in `GRAMS_PER_CUP` by string length, from longest to shortest.
4. Checks whether each key appears in the normalized ingredient name.
5. Returns the corresponding gram value for the first matching key.
6. If no substring match is found, compares the ingredient's token set with the token sets of the dictionary keys.
7. Returns the value for an exact token-set match.
8. Returns `None` if no match is found.

Sorting the keys by length means more specific ingredient names are checked before shorter names.

### 6.5 `grams_per_item_for(ingredient_name)`

Finds the grams-per-item conversion value for an ingredient.

**Process:**
1. Normalizes the ingredient name.
2. Sorts the keys in `GRAMS_PER_ITEM` by string length, from longest to shortest.
3. Checks whether each key appears in the normalized ingredient name.
4. Returns the corresponding gram value for the first match.
5. Returns `None` if no match is found.

### 6.6 `convert_to_grams(quantity, unit, ingredient_name="")`

Converts an ingredient quantity and unit into grams.

**Parameters:**
- `quantity`: The numeric amount of the ingredient.
- `unit`: The measurement unit.
- `ingredient_name`: The ingredient name, used when a volume or item conversion requires ingredient-specific information.

**Process:**

1. Attempts to convert `quantity` to a float.
2. Returns `None` if the quantity cannot be converted or is negative.
3. Normalizes the unit.
4. Applies unit aliases:
   - `gram` and `grams` become `g`.
   - `kilogram` and `kilograms` become `kg`.
   - `milligram` and `milligrams` become `mg`.
   - `teaspoon` and `teaspoons` become `tsp`.
   - `tablespoon` and `tablespoons` become `tbsp`.
   - `cups` becomes `cup`.
   - `milliliter` and `milliliters` become `ml`.
   - `liter` and `liters` become `l`.
   - `ounce` and `ounces` become `oz`.
   - `pound` and `pounds` become `lb`.
5. Checks whether the unit is a direct weight conversion in `GRAMS_PER_UNIT`.
6. If the unit is `oz`, multiplies the quantity by `28.349523125`.
7. If the unit is `lb`, multiplies the quantity by `453.59237`.
8. If the unit is a volume measurement, retrieves the ingredient's grams-per-cup value using `grams_per_cup_for`.
9. Applies the appropriate volume conversion:
   - Cups: `quantity * grams_per_cup`
   - Tablespoons: `quantity * grams_per_cup / 16`
   - Teaspoons: `quantity * grams_per_cup / 48`
   - Milliliters: `quantity * grams_per_cup / 240`
   - Liters: `quantity * grams_per_cup * 1000 / 240`
10. If the unit is a count measurement (`item`, `items`, `piece`, `pieces`, `whole`, `egg`, or `eggs`), retrieves the ingredient's grams-per-item value using `grams_per_item_for`.
11. Multiplies the quantity by the grams-per-item value.
12. Returns `None` if the unit is unsupported or the required ingredient conversion value cannot be found.

The function does not assign guessed weights to unsupported units such as servings, slices, or scoops unless the unit is explicitly handled by the conversion logic.

---

## 7. Baseline Recipe Macro Calculation

### 7.1 `calculate_recipe_macros(recipe, foods=None)`

Calculates the total nutrient values for a recipe using locally stored USDA food records.

**Parameters:**
- `recipe`: A list of recipe ingredients. Each ingredient is expected to contain a `name`, `quantity`, and `unit`.
- `foods`: An optional DataFrame containing the loaded food records. If omitted, the function loads the local food data.

**Process:**

1. Loads the local food data if `foods` was not provided.
2. Initializes a total of `0.0` for every nutrient in `NUTRIENTS`.
3. Iterates through each ingredient in the recipe.
4. Creates an ingredient result containing:
   - `ingredient`
   - `quantity`
   - `unit`
   - `grams`
   - `matched_food`
   - `match_score`
   - `confidence`
   - `status`
   - `nutrients`
5. Checks whether the ingredient has a name.
   - If the name is missing, the ingredient is skipped with the status `Skipped: missing ingredient name`.
6. Converts the ingredient quantity into grams using `convert_to_grams`.
   - If the conversion cannot be performed, the ingredient is skipped with the status `Skipped: unsupported unit or unknown conversion`.
7. Searches the local food records using `find_best_food`.
   - This function uses the local dataset.
   - It does not perform an API search.
8. If no suitable food match is found, the ingredient is skipped with the status `Skipped: no suitable match found`.
9. Records the matched food and its score.
10. Assigns a confidence label using `confidence_label`.
11. Checks whether the match score is at least `0.60`.
    - If the score is below `0.60`, the ingredient is skipped with the status `Skipped: match confidence is too low for calculation`.
12. Checks whether every nutrient in `NUTRIENTS` has a value.
    - If any nutrient is missing, the ingredient is skipped with the status `Skipped: missing nutrient data for ` followed by the missing nutrient names.
13. If all checks pass, calculates the nutrient contribution of the ingredient.
14. Scales each nutrient value from a per-100-gram basis using:

    ```python
    ingredient_nutrient = nutrient_per_100g * (ingredient_grams / 100)
    ```

15. Adds the ingredient's nutrient values to the recipe totals.
16. Records the ingredient's calculated nutrient values and sets its status to `Included`.

**Return value:**

Returns a tuple containing:

```python
(totals, ingredient_results)
```

- `totals`: A dictionary containing the total value for each nutrient in the recipe.
- `ingredient_results`: A list containing the processing result for each ingredient.

**Important behavior:**

An ingredient must have a sufficiently confident match and complete nutrient data for all nutrients in `NUTRIENTS` to contribute to the recipe totals. If even one required nutrient is missing, the ingredient is skipped entirely rather than contributing only the nutrients that are available.

---

## 8. USDA FoodData Central API Functions

### 8.1 `search_usda_api(ingredient_name, page_size=10)`

Searches the USDA FoodData Central API for foods matching an ingredient name.

**Parameters:**
- `ingredient_name`: The ingredient name to search for.
- `page_size`: The maximum number of results to request. Defaults to `10`.

**Process:**

1. Retrieves the API key from the `API_KEY` environment variable.
2. Raises a `ValueError` with the message `Set the API_KEY environment variable.` if the API key is missing.
3. Sends a POST request to:

   ```text
   https://api.nal.usda.gov/fdc/v1/foods/search
   ```

4. Includes the API key as a request parameter.
5. Sends the ingredient name as the search query.
6. Includes the requested page size.
7. Restricts the search to these USDA data types:
   - Foundation
   - SR Legacy
   - Survey (FNDDS)
8. Uses a request timeout of 15 seconds.
9. Calls `raise_for_status()` to raise an exception for an unsuccessful HTTP response.
10. Returns the `foods` list from the JSON response.

**Return value:**

A list of food records returned by the USDA API.

### 8.2 `get_usda_food_details(fdc_id)`

Retrieves detailed USDA food information using a FoodData Central ID.

**Parameters:**
- `fdc_id`: The USDA FoodData Central ID of the food record.

**Process:**

1. Retrieves the API key from the `API_KEY` environment variable.
2. Raises a `ValueError` if the API key is missing.
3. Sends a GET request to:

   ```text
   https://api.nal.usda.gov/fdc/v1/food/{fdc_id}
   ```

4. Includes the API key as a request parameter.
5. Uses a request timeout of 15 seconds.
6. Calls `raise_for_status()` to raise an exception for an unsuccessful HTTP response.
7. Returns the JSON response containing the food details.

**Return value:**

A dictionary containing the detailed USDA food record.

---

## 9. USDA Nutrient Extraction

### 9.1 `USDA_NUTRIENT_IDS`

`USDA_NUTRIENT_IDS` maps the nutrients used by the project to their corresponding USDA nutrient IDs.

| Nutrient | USDA Nutrient IDs |
|---|---|
| calories_kcal | 1008, 2047, 2048 |
| protein_g | 1003 |
| fat_g | 1004 |
| carbs_g | 1005 |
| fiber_g | 1079 |
| sugars_g | 2000 |
| sodium_mg | 1093 |
| potassium_mg | 1092 |
| calcium_mg | 1087 |
| iron_mg | 1089 |

These IDs are used to identify nutrient values in USDA food detail responses.

### 9.2 `NUTRIENT_NAME_ALIASES`

`NUTRIENT_NAME_ALIASES` maps nutrient names and alternate USDA descriptions to the project's nutrient keys.

| Project Nutrient | Accepted USDA Names |
|---|---|
| calories_kcal | energy, energy kcal, metabolizable energy |
| protein_g | protein |
| fat_g | total lipid (fat), total lipid, fat |
| carbs_g | carbohydrate, by difference; carbohydrate |
| fiber_g | fiber, total dietary; total dietary fiber; dietary fiber |
| sugars_g | sugars, total including nlea; total sugars; sugars, total |
| sodium_mg | sodium, na; sodium |
| potassium_mg | potassium, k; potassium |
| calcium_mg | calcium, ca; calcium |
| iron_mg | iron, fe; iron |

These aliases allow the extraction function to identify nutrients using their names when the USDA nutrient ID does not provide a match.

### 9.3 `nutrients_from_usda_details(details)`

Extracts and normalizes nutrient values from a USDA food detail response.

**Parameters:**
- `details`: A dictionary containing the USDA food detail response.

**Process:**

1. Initializes a dictionary containing every nutrient in `NUTRIENTS`, with each value set to `None`.
2. Iterates through the `foodNutrients` list in the USDA response.
3. Reads the nutrient ID, nutrient name, unit, and amount.
   - The function also checks `value` as an alternative to `amount`.
4. Attempts to convert the nutrient amount to a float.
   - Missing or unconvertible values are ignored.
5. Checks whether the nutrient ID matches an ID in `USDA_NUTRIENT_IDS`.
6. If the ID does not match, checks whether the normalized nutrient name matches an alias in `NUTRIENT_NAME_ALIASES`.
7. For calories:
   - Ignores values expressed in kJ, kilojoule, or kilojoules.
   - Prefers values expressed in kcal, calorie, or calories.
   - If no preferred calorie unit is found, uses the first available candidate.
8. For other nutrients, uses the first matching candidate.
9. Returns the normalized nutrient dictionary.

**Return value:**

A dictionary containing the project's nutrient keys and their extracted values.

The function's documentation describes these values as being on a per-100-gram basis. Nutrients that cannot be found remain `None`.

---

## 10. API-Enabled Food Matching

### 10.1 `find_best_food_with_api(ingredient_name, foods=None)`

Attempts to find the best food match using the local USDA dataset and the USDA API.

**Parameters:**
- `ingredient_name`: The ingredient name to match.
- `foods`: An optional DataFrame containing the local food records.

**Process:**

1. If `foods` is provided, searches the local dataset using `find_best_food`.
2. If a local match exists with a score of at least `0.60`, returns that match immediately.
3. Otherwise, searches the USDA API using `search_usda_api`.
   - Requests up to 10 results.
4. Handles `requests.RequestException` and `ValueError`.
   - If an adequate local match exists, returns that local match.
   - Otherwise, returns `None`.
5. Ranks the API search results using `rank_food_candidates`.
6. If there are no candidates, or the best candidate has a score below `0.60`, returns the adequate local match if one exists.
   - Otherwise, returns `None`.
7. Retrieves the detailed USDA record for the best API candidate using `get_usda_food_details`.
8. Handles `requests.RequestException` and `ValueError` during the detail lookup.
   - If an adequate local match exists, returns that local match.
   - Otherwise, returns `None`.
9. Extracts the nutrient values from the detailed USDA response using `nutrients_from_usda_details`.
10. Stores the extracted nutrients in the API candidate's `nutrients` field.
11. If the detail response contains a description, replaces the candidate's description with that description.
12. Returns the API candidate.

**Return value:**

- A food candidate dictionary if an acceptable match is found.
- `None` if no acceptable match is available.

**Important behavior:**

The function uses a score threshold of `0.60` for:
- Returning a local match immediately.
- Accepting an API match.
- Falling back to a local match when the API search or detail retrieval fails.

Unlike `find_best_food`, this function can search the USDA API when a suitable local match is not available.

---

## 11. Retrieving FDC IDs for Recipe Ingredients

### 11.1 `get_recipe_fdc_ids(recipe, foods=None)`

Retrieves USDA FoodData Central IDs for the ingredients in a recipe.

**Parameters:**
- `recipe`: A list of recipe ingredients.
- `foods`: An optional DataFrame containing the local food records. If omitted, the function loads the local food data.

**Process:**

1. Loads the local food data if `foods` was not provided.
2. Initializes an empty list to store the FDC IDs.
3. Iterates through each ingredient in the recipe.
4. Retrieves the ingredient name.
5. Skips ingredients that do not have a name.
6. Calls `find_best_food_with_api` to find a matching food record.
   - This allows the function to use both local food records and USDA API search results.
7. If a match is found, retrieves its `fdc_id`.
8. Appends the FDC ID to the result list.
9. Returns the list of collected FDC IDs.

**Return value:**

A list of USDA FoodData Central IDs.

**Important behavior:**
- The function returns only FDC IDs.
- It does not return ingredient names, match scores, or confidence labels.
- Ingredients without a match are skipped.
- No placeholder value is added for an unmatched ingredient.
- Because it calls `find_best_food_with_api`, it can search the USDA API when a suitable local match is unavailable.

---

## 12. Preparing Recipe Ingredients for the Math Engine

### 12.1 `prepare_recipe_for_math_engine(recipe, foods=None, aliases_by_id=None)`

Prepares recipe ingredients in the format expected by the deterministic math engine.

**Parameters:**
- `recipe`: A list of recipe ingredients.
- `foods`: An optional DataFrame containing local food records. If omitted, the function loads the local food data.
- `aliases_by_id`: An optional argument accepted by the function. It is not used in the function's implementation.

**Process:**

1. Loads the local food data if `foods` was not provided.
2. Initializes an empty list to store the prepared ingredient records.
3. Iterates through each ingredient in the recipe.
4. Retrieves the ingredient name from `name` or `note`.
5. Retrieves any aliases associated with the ingredient.
   - If no aliases are provided, uses an empty list.
6. Creates a list of names to search:
   - The primary ingredient name.
   - Any provided aliases.
7. Calls `find_best_food_with_api` for each nonempty search name.
8. Compares the resulting matches and selects the match with the highest score.
9. Determines the ingredient weight in grams using the following priority:
   - `qty_g`
   - `amount_g`
   - Conversion using `convert_to_grams(quantity or qty, unit, name)`
10. If the ingredient weight cannot be determined, adds an unresolved record to the result list.

An unresolved record caused by an unknown weight contains:

```python
{
    "fdc_id": None,
    "amount_g": None,
    "nutrients_per_100g": {},
    "status": "unresolved",
    "reason": "Ingredient weight could not be determined",
    "ingredient_name": name
}
```

11. If the weight is available, converts it to a float.
12. Raises a `ValueError` if the weight is negative.
13. Checks whether a sufficiently confident food match was found.
    - A match must have a score of at least `0.60`.
14. If no match exists or the score is below `0.60`, adds an unresolved record.

An unresolved record caused by an unsuitable food match contains:

```python
{
    "fdc_id": None,
    "amount_g": amount_g,
    "nutrients_per_100g": {},
    "status": "unresolved",
    "reason": "No sufficiently confident food match",
    "ingredient_name": name
}
```

15. If a sufficiently confident match exists, adds a resolved record containing:

```python
{
    "fdc_id": best_match["fdc_id"],
    "amount_g": amount_g,
    "nutrients_per_100g": best_match["nutrients"],
    "status": "resolved",
    "ingredient_name": name,
    "matched_food": best_match["description"],
    "match_score": best_match["score"]
}
```

16. Returns the list of prepared ingredient records.

**Return value:**

A list of dictionaries, with each dictionary representing a resolved or unresolved recipe ingredient.

**Important behavior:**
- The function attempts to match both the primary ingredient name and its aliases.
- It selects the candidate with the highest matching score.
- It uses API-enabled matching through `find_best_food_with_api`.
- It prioritizes explicitly supplied gram amounts over unit conversions.
- It preserves unresolved ingredients in the output rather than removing them.
- `aliases_by_id` is accepted as a parameter but is not used by the function.

---

## 13. Main Execution Block

The script includes a main execution block that runs when the file is executed directly.

**Process:**

1. Loads the local USDA food dataset using `load_foods()`.
2. Prints the top food matches for:
   - `egg`
   - `onion`
   - `unsalted butter`
3. Defines a sample recipe containing:
   - 2 tablespoons of unsalted butter.
   - 1 cup of all-purpose flour.
   - 2 eggs.
4. Calls `calculate_recipe_macros` with the sample recipe and loaded food data.
5. Iterates through the ingredient results and prints:
   - Ingredient name.
   - Processing status.
   - Matched food description.
   - Confidence label.
   - Ingredient weight in grams.
6. Prints the total nutrient values for the recipe.
   - Each nutrient total is formatted to two decimal places.

**Important behavior:**

The main execution block calls `calculate_recipe_macros`, which uses `find_best_food` to search the local dataset. It does not use the API-enabled matching function for the sample recipe calculation.
