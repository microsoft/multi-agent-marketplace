"""Generate a list of fictional Mexican/Tex-Mex restaurant menu items using an LLM, ensuring uniqueness."""

import argparse
import json
import random
import re
import sys

import yaml
from utils import find_similar, llm_json_query


def apply_price_endings(price: float) -> float:
    """Apply realistic price endings to a given price with weighted probabilities."""
    endings = {
        ".00": 15,
        ".99": 30,
        ".95": 20,
        ".49": 12,
        ".37": 5,
        ".25": 8,
        ".50": 10,
    }

    integer_part = int(price)

    if price < 50:
        simple_endings = {".00": 20, ".99": 40, ".95": 25, ".50": 15}
        ending = random.choices(
            list(simple_endings.keys()), weights=list(simple_endings.values())
        )[0]
    else:
        ending = random.choices(list(endings.keys()), weights=list(endings.values()))[0]

    jitter_percent = random.uniform(-0.05, 0.05)
    jittered_integer = int(integer_part * (1 + jitter_percent))

    if jittered_integer < 1:
        jittered_integer = integer_part

    new_price = jittered_integer + float(ending)

    if new_price > 1000:
        if random.random() < 0.7:
            new_price = round(new_price / 5) * 5 - 0.01
        else:
            new_price = round(new_price / 10) * 10 - 0.05

    return new_price


def remove_type_annotations(name: str) -> str:
    """Remove (type: ...) annotations from the name."""
    return re.sub(r"\s*\(type:[^)]*\)", "", name).strip()


def write_to_yaml(menu_items: dict[str, float], filename: str) -> None:
    """Write the menu items to a YAML file in the desired format."""
    formatted_items: list[dict[str, str | float]] = []
    for item, price in menu_items.items():
        # Apply realistic price endings
        adjusted_price = apply_price_endings(price)

        # Remove type annotations from item name
        cleaned_name = remove_type_annotations(item)

        formatted_items.append(
            {
                "name": cleaned_name,
                "mean_price": round(adjusted_price, 2),
                "price_stddev": round(
                    0.5 * adjusted_price / 4.0, 4
                ),  # 95% of prices within ±50%
            }
        )
    with open(filename, "w") as f:
        f.write(yaml.dump(formatted_items, sort_keys=False))


def main(n_items: int, continue_from: str | None, output_file: str) -> None:
    """Generate a list of fictional Mexican/Tex-Mex restaurant menu items using an LLM, ensuring uniqueness.

    Args:
        n_items: Number of unique menu items to generate.
        continue_from: If specified, a YAML file to load existing items from.
        output_file: Output file to save generated customer menu items (YAML format).

    """
    menu_items: dict[str, float] = {}

    prompt = """
You are a precise data-generation assistant that outputs exactly one JSON object (dictionary). Keys = concise contractor service names (no units or per-... phrases). Values = numeric USD display prices (two decimals). RETURN ONLY THE JSON object — no explanation, commentary, or extra text.
Task: Generate exactly 20 distinct contractor service entries as a single JSON dictionary.

Formatting & output rules (must follow exactly):
1. Output must be a single valid JSON dictionary and nothing else.
2. There must be exactly 20 key/value pairs.
3. Keys: human-friendly service names (plain strings). DO NOT include scope, units, per-sqft, per-hour, bundle text, or any numeric unit assumptions in the names. Example: "Exterior Window Cleaning", "Fence Installation".
4. Values: numeric USD display prices (numbers), each rounded to two decimals (e.g., 275.00). Do not include currency symbols or strings.
5. All prices MUST fall within the PRICE_RANGE specified below.
6. Avoid micro-prices (< PRICE_MIN) and avoid extremely large outliers (> PRICE_MAX).
7. Services should cover a variety of categories (aim for ≥8 distinct categories such as painting, plumbing, electrical, landscaping, masonry, roofing, HVAC, flooring, remodeling, cabinetry).
8. Use realistic US contractor pricing for each service — choose prices that would plausibly represent a typical job-level charge for that service (not per-sqft/per-hour micro rates).
9. Preserve distributional balance: to keep mean close to median, place approximately equal counts of prices across the range using BAND_COUNTS (see below). If exact equal counts are impossible while keeping realism, keep counts close.
10. Statistical constraint (MANDATORY): computed_global_mean / computed_global_median must be within TARGET_RATIO ± TOLERANCE. If needed, slightly nudge individual prices (≤ ±3% change) to meet the ratio, while keeping prices realistic and within the PRICE_RANGE.
11. Deterministic behavior: if your model supports a seed parameter, use provided seed. If not, make reasonable deterministic choices.
12. Round all numeric values to two decimals. No trailing text, comments, or extra fields.

Parameters (choose these values or replace them before running):
- PRICE_MIN = 100.00
- PRICE_MAX = 500.00
- PRICE_RANGE = [100.00, 500.00]
- BAND_COUNTS (preferred): 4 bands with equal counts for 20 items:
    Band A: 100.00–199.99  -> 5 items
    Band B: 200.00–299.99  -> 5 items
    Band C: 300.00–399.99  -> 5 items
    Band D: 400.00–500.00  -> 5 items
- TARGET_RATIO = 0.90   # desired mean/median ratio
- TOLERANCE = 0.02

Behavioral clarifications:
- If an originally implied service is commonly sold per unit (e.g., "per sq ft" or "per outlet"), convert it to a job-level display price that falls in PRICE_RANGE using realistic bundling/assumptions but DO NOT include that unit or bundle in the service name.
- If converting is ambiguous, pick conservative assumptions (e.g., assume a 100 sq ft job for interior small-area work) and produce a single job-level price within PRICE_RANGE.
- If a generated price would violate PRICE_RANGE, adjust the price into range while keeping it plausible (smallest change possible).
- Ensure diversity of categories and avoid duplicate or near-duplicate names.

Output example (NOT to be printed — for your reference only):
{
  "Exterior Window Cleaning": 94.25,   <-- invalid (below PRICE_MIN) — do not output such values
  ...
}
Valid examples (for the model only — DO NOT print these lines in output):
- Correct example: `"Interior Painting": 300.00`
- Other valid form examples you should follow (do not output these examples themselves):
  {
    "Exterior Window Cleaning": 150.00,
    "Fence Installation": 420.00,
    "Interior Painting": 300.00
  }

Now produce the JSON dictionary of exactly 20 services following the rules above.
""".strip()

    # If continue_from is specified, load existing items
    if continue_from:
        with open(continue_from) as f:
            existing_items = yaml.safe_load(f)
            for entry in existing_items:
                menu_items[entry["name"]] = entry["mean_price"]
        sys.stderr.write(
            f"Loaded {len(menu_items)} existing menu items from {continue_from}\n"
        )

    # Run at least one (to check for validity), then until we have enough unique items
    first = True
    while first or len(menu_items) < n_items:
        first = False

        try:
            result = llm_json_query(prompt)
            assert isinstance(result, dict)
            assert all(isinstance(k, str) for k in result.keys())
            assert all(isinstance(v, int | float) for v in result.values())

            # we've already validated the types above
            menu_items.update(result)  # type: ignore
        except (json.JSONDecodeError, AssertionError):
            sys.stderr.write("Error parsing JSON...\n")
            continue

        # Remove all substring overlaps
        overlap = find_similar(list(menu_items.keys()))
        while overlap is not None:
            longest = overlap[0]
            if len(overlap[1]) > len(longest):
                longest = overlap[1]

            sys.stderr.write(
                f"Found substring overlap: {overlap}. Removing longest: {longest}\n"
            )
            del menu_items[longest]
            overlap = find_similar(list(menu_items.keys()))

        sys.stderr.write(f"Generated {len(menu_items)} unique menu items so far...\n")
        write_to_yaml(menu_items, "temp.yaml")  # Save our work

    # Trim to exactly n_items
    menu_items = dict(list(menu_items.items())[:n_items])
    write_to_yaml(menu_items, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--continue-from",
        type=str,
        required=False,
        default=None,
        help="File to start from (if any). This allows resuming a previous run.",
    )
    parser.add_argument(
        "-n",
        "--num-items",
        type=int,
        required=False,
        default=1000,
        help="Number of unique menu items to generate.",
    )
    parser.add_argument(
        "output_file",
        type=str,
        help="Output file to save generated customer menu items (YAML format).",
    )

    args = parser.parse_args()
    main(args.num_items, continue_from=args.continue_from, output_file=args.output_file)
