import json, pandas as pd
df = pd.read_csv("cleanedData/clean_usda_foods.csv").set_index("fdc_id")
data = json.load(open("data/recipes_normalized.json"))["recipes"]
seen = {}
for r in data:
    for l in r["ingredients"]:
        if l.get("fdc_id") and l["ingredient_id"] not in seen:
            seen[l["ingredient_id"]] = int(l["fdc_id"])
print(f'{"ingredient":<20}{"fdc_id":<9}{"kcal":>7}{"P":>7}{"F":>7}{"C":>7}{"implied":>9}  description')
for name, i in sorted(seen.items()):
    r = df.loc[i]
    k, p, f, c = (float(r[x]) for x in ("calories_kcal", "protein_g", "fat_g", "carbs_g"))
    implied = 4 * p + 4 * c + 9 * f
    flag = "<-- CHECK" if implied > 20 and (k == 0 or abs(k - implied) / implied > 0.25) else ""
    print(f"{name:<20}{i:<9}{k:>7.0f}{p:>7.1f}{f:>7.1f}{c:>7.1f}{implied:>9.0f}  {str(r['description'])[:34]} {flag}")
