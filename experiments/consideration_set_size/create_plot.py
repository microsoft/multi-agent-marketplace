"""Create search limit welfare plots from CSV data."""

from argparse import ArgumentParser

from search_plot_utils import create_search_limit_plots

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Create search limit welfare plots from CSV files."
    )
    parser.add_argument(
        "--files-to-plot", nargs="+", required=True, help="List of CSV files to plot."
    )
    parser.add_argument(
        "--plot-key",
        type=str,
        required=True,
        help="The column to plot from the CSV (e.g., Welfare), enclosed in quotes.",
    )
    parser.add_argument(
        "--plot-label",
        type=str,
        required=True,
        help="The label to use for the plot (e.g., 'Customer Welfare'), enclosed in quotes.",
    )
    parser.add_argument(
        "--hide-legend",
        action="store_true",
        help="Whether to hide the legend in the plot.",
    )
    args = parser.parse_args()

    input_files = args.files_to_plot
    plot_key = args.plot_key

    create_search_limit_plots(
        input_files,
        welfare_type="customer",
        plot_key=plot_key,
        plot_label=args.plot_label,
        hide_legend=args.hide_legend,
    )
