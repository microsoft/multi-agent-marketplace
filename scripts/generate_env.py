"""Generate .env file from a template by filling values from OS environment variables.

This script reads a template .env file and generates a .env file by:
1. Checking if each key exists in the OS environment
2. Using the OS environment value if found
3. Falling back to the template default if not found
4. Stripping any leading "export " from values
"""

import os
import sys
from pathlib import Path


def parse_env_line(line: str) -> tuple[str | None, str | None, str]:
    """Parse a line from an env file.

    Returns:
        (key, value, original_line) tuple
        - key and value are None if line is comment or empty
        - original_line is the original line for passthrough

    """
    line = line.strip()

    # Skip empty lines and comments
    if not line or line.startswith("#"):
        return None, None, line

    # Split on first '=' sign
    if "=" not in line:
        return None, None, line

    key, value = line.split("=", 1)

    # Remove leading 'export ' from key
    key = key.strip().removeprefix("export ")

    return key, value, line


def generate_env(template_path: str, output_path: str = ".env") -> None:
    """Generate .env file from template.

    Args:
        template_path: Path to the template .env file
        output_path: Path to the output .env file (default: .env)

    """
    template_file = Path(template_path)

    if not template_file.exists():
        print(f"Error: Template file '{template_path}' not found.", file=sys.stderr)
        sys.exit(1)

    output_lines = []

    with open(template_file) as f:
        for line in f:
            key, template_value, original_line = parse_env_line(line)

            # Pass through comments and empty lines as-is
            if key is None:
                output_lines.append(original_line)
                continue

            # Check if key exists in OS environment
            env_value = os.environ.get(key)

            if env_value is not None:
                # Use environment value, stripping any leading export
                output_lines.append(f"{key}={env_value}")
                print(f"  {key}: Using value from OS environment")
            else:
                # Use template default
                output_lines.append(f"{key}={template_value}")
                print(f"  {key}: Using template default")

    # Write output file
    output_file = Path(output_path)
    with open(output_file, "w") as f:
        f.write("\n".join(output_lines))
        if output_lines and output_lines[-1] != "":
            f.write("\n")

    print(f"\n  Generated {output_path} from {template_path}")


def main():
    """Generate the .env file."""
    if len(sys.argv) < 2:
        print("Usage: python generate_env.py <template_file> [output_file]")
        print("\nExample:")
        print("  python generate_env.py .env.template")
        print("  python generate_env.py .env.template .env")
        sys.exit(1)

    template_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else ".env"

    generate_env(template_path, output_path)


if __name__ == "__main__":
    main()
