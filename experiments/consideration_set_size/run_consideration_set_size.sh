#!/usr/bin/env bash

# This script runs the consideration set size experiments.

DATASET="data/mexican_3_9"
SEARCH_LIMITS=(1 2 3)
RUNS=5
MODEL="gpt-4o"

# Default model provider dict per model 
model_provider_for() {
  case "$1" in
    gpt-4o|gpt-4.1|gpt-5) echo "openai" ;;
    gemini-2.5-flash)     echo "gemini" ;;
    claude-sonnet-4-20250514) echo "anthropic" ;;
    *) echo "openai" ;;
  esac
}

# Read the model, search limits, and dataset from command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --runs) RUNS=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --model-provider) MODEL_PROVIDER=$2; shift 2 ;;
    --dataset) DATASET=$2; shift 2 ;;
    --search-limits) SEARCH_LIMITS=($2); shift 2 ;;
    --help|-h)
      echo "run_consideration_set_size.sh --runs N [--config-dir DIR | --config-zip ZIP] [options]"
      echo "Runs magentic-marketplace N times for a given configuration"
      exit 0 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

MODEL_PROVIDER=$(model_provider_for "$MODEL")
export LLM_MODEL="$MODEL"
export LLM_PROVIDER="$MODEL_PROVIDER"

echo "======================================"
echo "Running consideration set size experiments with the following parameters:"
echo "Dataset: $DATASET"
echo "Model: $MODEL"
echo "Model Provider: $MODEL_PROVIDER"
echo "Search Limits: ${SEARCH_LIMITS[*]}"
echo "Runs per setting: $RUNS"

# run from the root directory so the dataset path resolves correctly. 
for SEARCH_LIMIT in "${SEARCH_LIMITS[@]}"; do
    echo -e "\n======================================"
    echo "Running with search limit: $SEARCH_LIMIT"
    for i in $(seq 1 $RUNS); do
        echo -e "\n"
        echo "Run $i/$RUNS"

        MODEL_CLEAN="${MODEL//[-.]/}"
        
        # Replace data/ in the dataset with nothing
        DATASET_CLEAN="${DATASET#data/}"
        DATASET_CLEAN="${DATASET_CLEAN//\//_}"

        EXPERIMENT_NAME="search_limit_${MODEL_CLEAN}_${DATASET_CLEAN}_limit_${SEARCH_LIMIT}_run_${i}"

        echo "Experiment Name: $EXPERIMENT_NAME"

        magentic-marketplace run "../../$DATASET" --experiment-name "$EXPERIMENT_NAME" --search-algorithm lexical --search-bandwidth "$SEARCH_LIMIT"
        magentic-marketplace analyze "$EXPERIMENT_NAME"

        mv "analytics_results_search_limit_${MODEL_CLEAN}_${DATASET_CLEAN}_limit_${SEARCH_LIMIT}_run_${i}.json" "analytics_results_search_limit_${MODEL}_${DATASET_CLEAN}_limit_${SEARCH_LIMIT}_run_${i}.json"
    done
done
