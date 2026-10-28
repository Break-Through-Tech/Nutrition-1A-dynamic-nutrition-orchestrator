
from math import isclose

from scripts import ingredient_matching as im
from nutrition_engine import math_engine


def main():
    foods = im.load_foods()

    # Use gram quantities so this test focuses on integration,
    # rather than unit conversion.
    recipe = [
        {"name": "unsalted butter", "qty_g": 28.375},
        {"name": "all purpose flour", "qty_g": 120.0},
        {"name": "egg", "qty_g": 100.0},
    ]

    # Disable API fallback for this test. We want to test the
    # local CSV -> preparation -> math engine pipeline.
    original_matcher = im.find_best_food_with_api

    try:
        im.find_best_food_with_api = (
            lambda name, available_foods=None:
            im.find_best_food(name, available_foods)
        )

        prepared = im.prepare_recipe_for_math_engine(
            recipe,
            foods=foods,
        )
    finally:
        im.find_best_food_with_api = original_matcher

    print("\n=== Prepared Ingredients ===")
    for ingredient in prepared:
        print(
            f"{ingredient['ingredient_name']}: "
            f"status={ingredient['status']}, "
            f"food={ingredient.get('matched_food', 'UNMATCHED')}, "
            f"weight={ingredient['amount_g']} g"
        )

    # Adapt the matcher's ingredient_name field to the math engine's
    # expected name field.
    calculator_input = [
        {
            **ingredient,
            "name": ingredient["ingredient_name"],
        }
        for ingredient in prepared
    ]

    result = math_engine.calculate_recipe(
        calculator_input,
        servings=2,
    )

    print("\n=== Math Engine Results ===")
    print("Recipe status:", result["status"])
    print("Complete:", result["complete"])
    print("Coverage:", result["coverage"])

    print("\nBatch totals:")
    for nutrient, value in result["batch_totals"].items():
        print(f"  {nutrient}: {value}")

    print("\nPer-serving totals:")
    for nutrient, value in result["per_serving_totals"].items():
        print(f"  {nutrient}: {value}")

    print("\nIngredient contributions:")
    for ingredient in result["ingredients"]:
        print(
            f"\n{ingredient['name']}: "
            f"{ingredient['status']}"
        )
        for nutrient, value in ingredient["nutrients"].items():
            print(f"  {nutrient}: {value}")

    # Integration checks.
    assert len(prepared) == 3, "Expected three prepared ingredients"
    assert result["coverage"]["ingredient_count"] == 3
    assert isclose(
        result["coverage"]["total_weight_g"],
        248.375,
        abs_tol=1e-6,
    ), "Total ingredient weight is incorrect"

    # Any known per-serving total must equal the batch total / 2.
    for nutrient, batch_value in result["batch_totals"].items():
        serving_value = result["per_serving_totals"][nutrient]

        if batch_value is not None:
            assert isclose(
                serving_value,
                batch_value / 2,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ), f"Per-serving calculation failed for {nutrient}"
        else:
            assert serving_value is None, (
                f"{nutrient} should remain unknown per serving"
            )

    # A failed match must not be silently treated as a resolved food.
    for ingredient in prepared:
        if ingredient["status"] == "unresolved":
            assert ingredient["fdc_id"] is None

    print("\nIntegration smoke test passed!")


if __name__ == "__main__":
    main()
