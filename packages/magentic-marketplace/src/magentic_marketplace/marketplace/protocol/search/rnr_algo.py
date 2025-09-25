"""Retrieve and rerank search results.

The implementation roughly follows what is described here:
 https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html.
"""

import json
import logging

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer, util

from magentic_marketplace.platform.database.models import AgentRow

from ...shared.models import Business, SearchConstraints

logger = logging.getLogger(__name__)


class RetrieveAndRerank:
    """Implements search result retrieval and reranking for marketplace queries."""

    def __init__(self):
        """Initialize the RetrieveAndRerank class."""
        device = "cpu"  # Work on any device

        # Use the Bi-Encoder to encode all business and documents

        # https://www.sbert.net/docs/sentence_transformer/pretrained_models.html
        self.bi_encoder = SentenceTransformer(
            "multi-qa-MiniLM-L6-cos-v1", device=device
        )

        self.top_k = 32  # number of results we want to retrieve with the bi-encoder

        # Use the cross_encoder for re-ranking
        self.cross_encoder = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L6-v2", device=device
        )

        # Save the list of formatted business documents for later use in search queries
        self.business_docs: list[str] = []

    def _format_business_metadata_for_ranking(
        self,
        business: Business,
        index_name: bool = True,
        index_menu_prices: bool = False,
        index_amenities: bool = False,
    ) -> str:
        """Format the business metadata for ranking.

        Args:
            business: The Business model to format
            index_name: Whether to include the business name in the formatted output.
            index_menu_prices: Whether to include menu item prices in the formatted output.
            index_amenities: Whether to include amenities in the formatted output.

        Returns:
            str: The formatted business metadata.

        """
        if index_name:
            formatted_business = f"{business.name}, "
        else:
            formatted_business = ""

        formatted_business += f"{business.description}"

        # Add in menu item descriptors
        for item, price in business.menu_features.items():
            if index_menu_prices:
                formatted_business += f"({item}: {price}), "
            else:
                formatted_business += f"{item}, "

        if index_amenities:
            # Add in amenities
            for feature, value in business.amenity_features.items():
                if value:
                    formatted_business += f"{feature}, "

        logger.info(f"formatted_business: {formatted_business}")
        return formatted_business

    def compute_business_embeddings_as_bytes(
        self, agent_rows: list[AgentRow]
    ) -> list[tuple[str, bytes]]:
        """Compute embeddings for a list of business agent rows."""
        logger.info(
            f"\nComputing embeddings for {len(agent_rows)} business documents..."
        )

        # Collect formatted business documents
        result_docs: list[str] = []
        valid_agent_ids: list[str] = []

        for agent_row in agent_rows:
            try:
                # Extract business data from agent
                business_data = getattr(agent_row.data, "business", None)
                if business_data:
                    business = Business.model_validate(business_data)
                    formatted_business = self._format_business_metadata_for_ranking(
                        business
                    )
                    result_docs.append(formatted_business)
                    self.business_docs.append(formatted_business)
                    valid_agent_ids.append(agent_row.id)
            except (json.JSONDecodeError, ValueError) as e:
                logger.info(f"Error processing agent {agent_row.id}: {e}")
                continue

        if not result_docs:
            return []

        embeddings = self.bi_encoder.encode(result_docs, convert_to_tensor=True)  # type: ignore

        # Convert to blobs to keep tensor code in this class
        # Move tensors to CPU before converting to numpy
        if hasattr(embeddings, "cpu"):
            # Handle single tensor
            cpu_embeddings = embeddings.cpu()
            embedding_blobs = [
                cpu_embeddings[i].numpy().astype(np.float32).tobytes()  # pyright: ignore[reportUnknownMemberType]
                for i in range(len(cpu_embeddings))
            ]
        else:
            # Handle list of tensors
            embedding_blobs = [
                (embedding.cpu() if hasattr(embedding, "cpu") else embedding)
                .numpy()  # pyright: ignore[reportUnknownMemberType]
                .astype(np.float32)
                .tobytes()
                for embedding in embeddings
            ]

        if len(embedding_blobs) != len(valid_agent_ids):
            raise ValueError(
                f"Number of embedding blobs does not match number of agent IDs: {len(embedding_blobs)}, {len(valid_agent_ids)}"
            )

        return list(zip(valid_agent_ids, embedding_blobs, strict=True))

    def rank_search_results(
        self,
        query: str,
        constraints: SearchConstraints | None,
        agent_rows: list[AgentRow],
    ) -> list[AgentRow]:
        """Rank search results based on relevance to the query."""
        logger.debug(f"\nRanking search results for query: {query}")

        # Encode the query
        question_embedding: torch.Tensor = self.bi_encoder.encode(  # type: ignore
            query, convert_to_tensor=True
        )

        # Get business embeddings from agent rows
        business_embeddings_list: list[np.ndarray] = []  # pyright: ignore[reportMissingTypeArgument, reportUnknownVariableType]
        valid_indices: list[int] = []

        for i, agent_row in enumerate(agent_rows):
            if agent_row.agent_embedding is not None:
                embedding_array = np.frombuffer(
                    agent_row.agent_embedding, dtype=np.float32
                )
                business_embeddings_list.append(embedding_array)  # pyright: ignore[reportUnknownMemberType]
                valid_indices.append(i)

        if not business_embeddings_list:
            logger.warning("No embeddings found for agents")
            return []

        business_embeddings = torch.tensor(np.array(business_embeddings_list))  # pyright: ignore[reportUnknownArgumentType]

        # Ensure tensors are on the same device for semantic search
        if question_embedding.device != business_embeddings.device:
            business_embeddings = business_embeddings.to(question_embedding.device)

        # Perform semantic search using the bi-encoder to find relevant businesses
        hits = util.semantic_search(
            question_embedding,
            business_embeddings,
            top_k=min(self.top_k, len(business_embeddings)),
        )
        hits = hits[0]  # Get the hits for the first query

        # Get the corresponding business docs (need to build this from agent data)
        business_docs_for_hits: list[str] = []
        for hit in hits:
            corpus_id = hit["corpus_id"]
            if corpus_id < len(valid_indices):
                agent_idx = valid_indices[int(corpus_id)]
                agent_row = agent_rows[agent_idx]
                business_data = agent_row.data.metadata.get("business")
                if business_data:
                    business = Business.model_validate(business_data)
                    formatted_business = self._format_business_metadata_for_ranking(
                        business
                    )
                    business_docs_for_hits.append(formatted_business)
                else:
                    business_docs_for_hits.append("")
            else:
                business_docs_for_hits.append("")

        # Score all retrieved hits with the cross-encoder
        cross_inp = [[query, business_docs_for_hits[idx]] for idx in range(len(hits))]
        cross_scores: torch.Tensor = self.cross_encoder.predict(  # type: ignore
            cross_inp, convert_to_tensor=True
        )

        # Sort results by the cross-encoder scores
        for idx in range(len(cross_scores)):
            # Ensure we can convert CUDA tensors to float
            score_value = cross_scores[idx]
            if hasattr(score_value, "cpu"):
                score_value = score_value.cpu()
            hits[idx]["cross-score"] = float(score_value)

        # Build a mapping from corpus_id to cross-score
        cross_score_map = {int(hit["corpus_id"]): hit["cross-score"] for hit in hits}

        # Sort agent rows by cross-score (descending)
        # Map corpus_id to actual agent row indices
        scored_agent_rows: list[tuple[float, AgentRow]] = []
        for i, agent_row in enumerate(agent_rows):
            if i in valid_indices:
                corpus_id = valid_indices.index(i)
                score = cross_score_map.get(corpus_id, float("-inf"))
                scored_agent_rows.append((score, agent_row))
            else:
                scored_agent_rows.append((float("-inf"), agent_row))

        # Sort by score descending
        scored_agent_rows.sort(key=lambda x: x[0], reverse=True)

        sorted_results = [agent_row for _, agent_row in scored_agent_rows]

        logger.info("\nSorted results based on cross-encoder scores: ")
        for idx, (score, agent_row) in enumerate(scored_agent_rows[:10]):  # Show top 10
            business_data = agent_row.data.metadata.get("business")
            business_name = "Unknown"
            if business_data:
                try:
                    business = Business.model_validate(business_data)
                    business_name = business.name
                except (json.JSONDecodeError, ValueError):
                    pass
            logger.info(
                f"Rank {idx + 1}: Name: {business_name}, Agent ID: {agent_row.id}, Score: {score:.4f}"
            )

        return sorted_results
