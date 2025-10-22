# `analyze`: Analyze experiment results

After an experiment finishes, you can analyze the results with this command. By default it will print out analytics and save them to a json file.

**Usage:**

```bash
magentic-marketplace analyze my_experiment
```

**Common arguments:**

`experiment-name` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Experiment name (PostgreSQL schema name).

`--db-type` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Type of database: `sqlite` or `postgres` (default: `postgres`). For postgres, the experiment name is the name of a schema in the database. For sqlite, it is the path to a database file.

`--no-save-json` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Disable saving analytics to JSON file
