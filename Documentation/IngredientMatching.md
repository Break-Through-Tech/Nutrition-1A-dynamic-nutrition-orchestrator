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
