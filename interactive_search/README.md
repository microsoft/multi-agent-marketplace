# Script for Working with the Marketplace Search API

This directory provides convenience scripts for interacting with the search API of the
Marketplace, and for running basic evaluations. 

### Interactive Search

To run the interactive search script, use the following command:

```bash
python interactive_search.py --data-dir ../data/mexican_3_9
```

### Evaluation

Evaluation is done by randomly sampling a menu item from EACH restaurant in the dataset,
and for each item, determining the rank of the FIRST restaurant that contains that item.

From these ranks we compute [mean reciprocal rank](https://en.wikipedia.org/wiki/Mean_reciprocal_rank) (MRR) as the evaluation metric.

Values closer to 1.0 are better, with 1.0 being perfect.

To run the evaluation script, use the following command:
```
python menu_mrr.py --data-dir ../data/mexican_3_9       
```