# Scripts for synthetic data generation 

This folder contains scripts for synthetic data generation. Generate a synthetic dataset by running the following command:

```bash
python generate_customers_and_businesses.py <path_to_output_directory>
```

See, 
```bash
python generate_customers_and_businesses.py --help
```
for more details on the arguments.


### Validation
You can validate the generated data by running the following command:

```bash
python validate.py <path_to_input_directory>
```


### Extras

Feature files have already been generated and stored in the `features` folder. If you would like to regenerate them, run the following command:

```bash
python generate_items.py <path_to_output_file: e.g. features/items.yaml>
```

```bash
python generate_people.py <path_to_output_file: e.g. features/people.yaml>
```

### Contractors Dataset

For generating items
```bash
python generate_item_contractors.py <path_to_output_file>
```

For generating business and customer YAML files
```bash
python generate_customers_and_business_contractors.py -f <path_to_features_directory> -c <number_of_customers> <output_dir>
```

