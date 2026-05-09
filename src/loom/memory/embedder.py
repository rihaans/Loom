"""Embedding providers for the memory system."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loom.memory.models import MemoryConfig

logger = logging.getLogger(__name__)

# Embedding dimension for all-MiniLM-L6-v2
EMBEDDING_DIM = 384


class Embedder(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Return the embedding dimension."""
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        ...


class LocalEmbedder(Embedder):
    """Local embedding using sentence-transformers.

    Uses the all-MiniLM-L6-v2 model by default, which:
    - Has 22M parameters (~80MB on disk)
    - Produces 384-dim embeddings
    - Runs on CPU at ~1000 docs/sec
    - Works fully offline
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """Initialize the local embedder.

        Args:
            model_name: The sentence-transformers model to use.
        """
        self.model_name = model_name
        self._model = None

    def _ensure_model(self) -> None:
        """Lazy-load the model on first use."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                logger.info("Embedding model loaded successfully")
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install 'loom[memory]'"
                ) from e

    @property
    def dim(self) -> int:
        """Return the embedding dimension."""
        return EMBEDDING_DIM

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        self._ensure_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        self._ensure_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


class OpenAIEmbedder(Embedder):
    """OpenAI embedding provider.

    Uses text-embedding-3-small by default.
    """

    OPENAI_DIM = 1536

    def __init__(self, model_name: str = "text-embedding-3-small"):
        """Initialize the OpenAI embedder.

        Args:
            model_name: The OpenAI embedding model to use.
        """
        self.model_name = model_name
        self._client = None

    def _ensure_client(self) -> None:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                import openai

                self._client = openai.OpenAI()
            except ImportError as e:
                raise ImportError(
                    "openai is required for OpenAI embeddings. "
                    "Install with: pip install openai"
                ) from e

    @property
    def dim(self) -> int:
        """Return the embedding dimension."""
        return self.OPENAI_DIM

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        self._ensure_client()
        response = self._client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        self._ensure_client()
        response = self._client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]


def get_embedder(config: MemoryConfig) -> Embedder:
    """Get an embedder based on configuration.

    Args:
        config: Memory configuration.

    Returns:
        An Embedder instance.
    """
    if config.embedder == "openai":
        return OpenAIEmbedder(model_name=config.embedder_model)
    else:
        return LocalEmbedder(model_name=config.embedder_model)
