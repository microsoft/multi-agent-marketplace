"""Retrieve and rerank search results using lexical similarity.

The implementation roughly follows what is described here:
https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html.
"""

import re

from ...shared.models import BusinessAgentProfile


def shingle_overlap_score(
    query: str, doc: str, k: int = 4, normalize_length: bool = True
) -> float:
    """Compute the shingle overlap score between two strings.

    Args:
        query (str): The first string.
        doc (str): The second string.
        k (int): The shingle size.
        normalize_length (bool): Whether to normalize the score to the length of the query.

    Returns:
        float: The shingle overlap score between the two strings.

    """

    def normalize_text(s: str) -> str:
        # Lowercase and remove non-alphanumeric characters
        s = s.lower()
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def get_shingles(s: str, k: int) -> set[str]:
        if len(s) < k:
            s = s + " " * (k - len(s))
        return {s[i : i + k] for i in range(len(s) - k + 1)}

    shingles_query = get_shingles(" " + normalize_text(query) + " ", k)
    shingles_doc = get_shingles(" " + normalize_text(doc) + " ", k)

    intersection = shingles_query.intersection(shingles_doc)

    if normalize_length:
        if len(shingles_query) == 0:
            return 0.0
        return len(intersection) / len(
            shingles_query
        )  # How much of the query is covered by the doc
    else:
        return len(intersection)


def lexical_rank(
    query: str,
    businesses: list[BusinessAgentProfile],
    index_name: bool = True,
    index_menu_prices: bool = False,
    index_amenities: bool = False,
) -> list[BusinessAgentProfile]:
    """Rerank search results using lexical similarity.

    Args:
        query: The search query string
        businesses: List of business agent profiles to rank
        index_name (bool): Whether to include the business name in the searchable text.
        index_menu_prices (bool): Whether to include menu item prices in the searchable text.
        index_amenities (bool): Whether to include amenities in the searchable text.

    Returns:
        Ranked list of business agent profiles

    """
    # Create a dictionary for quick lookup of results by agent id
    results_dict: dict[str, BusinessAgentProfile] = {}
    for business in businesses:
        results_dict[business.id] = business

    # Compute shingle overlap scores
    shingle_score_tuples: list[tuple[str, float]] = []
    for business in businesses:
        searchable_text = business.business.get_searchable_text(
            index_name=index_name,
            index_menu_prices=index_menu_prices,
            index_amenities=index_amenities,
        )
        shingle_score = shingle_overlap_score(query, searchable_text)
        shingle_score_tuples.append((business.id, shingle_score))

    # Sort by shingle score (descending)
    shingle_score_tuples = sorted(
        shingle_score_tuples, key=lambda x: x[1], reverse=True
    )

    # Return the search results in ranked order
    ranked_results: list[BusinessAgentProfile] = []
    for business_id, _ in shingle_score_tuples:
        result = results_dict[business_id]
        ranked_results.append(result)

    return ranked_results
