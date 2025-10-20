# pyright: reportUnknownMemberType=none, reportUnknownParameterType=none, reportUnknownVariableType=none, reportMissingParameterType=none, reportUnknownArgumentType=none
"""Create search limit welfare plots from CSV data."""

from argparse import ArgumentParser

from search_plot_utils import create_search_limit_plots

if __name__ == "__main__":
    # Take in the files to plot as an argument using argparse
    parser = ArgumentParser(
        description="Create search limit welfare plots from CSV files."
    )
    parser.add_argument("--files-to-plot", nargs="+", help="List of CSV files to plot.")
    parser.add_argument(
        "--plot-key",
        type=str,
        help="The column to plot from the CSV (e.g., Welfare), enclosed in quotes.",
    )

    args = parser.parse_args()

    input_files = args.files_to_plot
    plot_key = args.plot_key

    create_search_limit_plots(input_files, welfare_type="customer", plot_key=plot_key)
