# `ui`: Launch a marketplace UI

Launches a marketplace visualizer in the browser, defaults to [http://localhost:5000/](http://localhost:5000/). You can use this UI to explore customer and business conversations after an experiment has finished or while an experiment is running.

<img src="/ui.png" style="border: 2px solid #F6F6F7; border-radius: 10px;">

**Usage:**

```bash
magentic-marketplace ui my_experiment
```

**Common arguments:**

`experiment_name` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Experiment name (PostgreSQL schema name).

`--db-type` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Type of database: `sqlite` or `postgres` (default: `postgres`). For postgres, the experiment name is the name of a schema in the database. For sqlite, it is the path to a database file.
