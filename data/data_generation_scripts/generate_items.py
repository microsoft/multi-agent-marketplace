"""Generate a list of fictional Mexican/Tex-Mex restaurant menu items using an LLM, ensuring uniqueness."""

import argparse
import json
import sys

import yaml
from utils import find_similar, llm_json_query


def write_to_yaml(menu_items: dict[str, float], filename: str) -> None:
    """Write the menu items to a YAML file in the desired format."""
    formatted_items: list[dict[str, str | float]] = []
    for item, price in menu_items.items():
        formatted_items.append(
            {
                "name": item,
                "mean_price": round(price, 2),
                "price_stddev": round(
                    0.5 * price / 4.0, 4
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
I am trying to populate a menu for a fictional Mexican or Tex-Mex restaurant.
Please generate a list of 20 menu item names, and corresponding prices (implicitly in USD).
The names should be moderaely generic, but not overly so.

Names like "Guacamole Galore", and "Stuffed Poblano Pepper Bliss" are over-the-top.
Names like "Taco", "Burrito", and "Quesadilla" are too generic.
Names like "Cheesy Jalapeno Poppers", "Cinnamon Sugar Churros", and "Salted Caramel Margarita" are good examples of the style I'm looking for.

The menu items can cover a variety of categories, such as appetizers, main courses, desserts, and drinks, breakfast items, etc.
The format of the response MUST be a valid JSON dictionary, where the keys are the item names and the values are the prices.
As an example, a valid dictionary could be:

{
"Firecracker Shrimp Tacos": 12.99,
"Churro Sundae": 6.49,
"Spicy Mango Margarita": 8.99
...
}
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
