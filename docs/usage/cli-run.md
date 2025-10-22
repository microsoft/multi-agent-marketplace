# `run`: Run a marketplace experiment

Run a marketplace simulation using YAML configuration files. You must provide the path to a directory with `/businesses` and `/customers` subdirectories that contain YAML files. See the [data](https://github.com/microsoft/multi-agent-marketplace/tree/main/data) folder in our repo for examples.

**Usage:**

```bash
magentic-marketplace run data/mexican_3_9 --experiment-name my_experiment
```

**Common arguments:**

`data_dir` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Path to the data directory containing `businesses/` and `customers/` subdirectories

`--experiment-name` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Name for this experiment. If not provided, a unique name will be generated.

`--override-db` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Override the experiment with this name if it exists.

`--search-algorithm` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Search algorithm for customer agents (default: `lexical`).

`--search-bandwidth` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Search bandwidth for customer agents (default: `10`).

`--customer-max-steps` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Maximum number of steps a customer agent can take before stopping (default: `100`).

**Additional options:** See additional arguments with `magentic-marketplace run --help`.
