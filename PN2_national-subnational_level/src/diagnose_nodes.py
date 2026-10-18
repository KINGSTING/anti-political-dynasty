import pandas as pd

FINAL_CSV = (
    r"PN2_national-subnational_level\data\national+subnational_edges_FINAL.csv"
)
df = pd.read_csv(FINAL_CSV, dtype=str, keep_default_na=False)

print("=== COLUMNS IN FINAL.CSV ===")
print(list(df.columns))

print("\n=== FIRST 2 ROWS ===")
for i, row in df.head(2).iterrows():
  print(dict(row))