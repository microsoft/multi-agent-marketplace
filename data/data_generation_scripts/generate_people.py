"""Generate a list of unique fictional people names using an LLM."""

import argparse
import json
import sys

import yaml
from utils import find_similar, llm_json_query


def write_to_yaml(names: list[str], filename: str) -> None:
    """Write the list of names to a YAML file."""
    assert isinstance(names, list)
    with open(filename, "w") as f:
        f.write(yaml.dump(names, sort_keys=False))


def main(n_names: int, continue_from: str | None, output_file: str) -> None:
    """Generate a list of unique fictional people names."""
    people_names: list[str] = []

    prompt = """
I am trying to populate a list of fictional people who are patrons to fictional restaurant.
Please generate a list of 20 normal-sounding, common first and last names. Avoid names that are too similar to each other (e.g., John Smith and Jon Smith). Avoid names that are too similar to common celebrities or well-known people alive, or in history (e.g., Tom Cruise, Albert Einstein, etc.). Names can be diverse, not just American or English names.

Output the result as a JSON object with the following format:
{
  "names": [
  "Robert Johnson",
  "Emily Davis",
  "Michael Brown",
  "Sophia Martinez",
   ...
  ]
}
""".strip()

    # If continue_from is specified, load existing items
    if continue_from:
        with open(continue_from) as f:
            people_names = yaml.safe_load(f)
            assert isinstance(people_names, list)
            assert all(isinstance(name, str) for name in people_names)

    # Run at least one (to check for validity), then until we have enough unique items
    first = True
    while first or len(people_names) < n_names:
        first = False

        try:
            result = llm_json_query(prompt)
            assert isinstance(result, dict)
            assert "names" in result
            assert isinstance(result["names"], list)
            assert all(isinstance(name, str) for name in result["names"])

            # We've already validated the types, above
            people_names.extend(result["names"])  # type: ignore

        except (json.JSONDecodeError, AssertionError):
            sys.stderr.write("Error parsing JSON...\n")
            continue

        # Remove all substring overlaps
        overlap = find_similar(people_names)
        while overlap is not None:
            longest = overlap[0]
            if len(overlap[1]) > len(longest):
                longest = overlap[1]

            sys.stderr.write(
                f"Found substring overlap: {overlap}. Removing longest: {longest}\n"
            )
            people_names.remove(longest)
            overlap = find_similar(people_names)

        sys.stderr.write(f"Generated {len(people_names)} unique names so far...\n")
        write_to_yaml(people_names, "temp.yaml")  # Save our work

    # Trim to exactly n_names
    people_names = people_names[:n_names]
    write_to_yaml(people_names, output_file)


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
        "--num-names",
        type=int,
        required=False,
        default=1000,
        help="Number of unique people names to generate.",
    )
    parser.add_argument(
        "output_file",
        type=str,
        help="Output file to save generated people names (YAML format).",
    )

    args = parser.parse_args()
    main(args.num_names, continue_from=args.continue_from, output_file=args.output_file)
