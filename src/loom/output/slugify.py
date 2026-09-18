"""Safe path and slug generation utilities."""

import re
import unicodedata
from pathlib import Path


def slugify(text: str, max_length: int = 40) -> str:
    """Convert text to a valid kebab-case slug.

    Args:
        text: Input text to slugify
        max_length: Maximum slug length

    Returns:
        Kebab-case slug (e.g., "my-project-name")
    """
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    text = text.lower()

    # Replace spaces and underscores with hyphens
    text = re.sub(r"[\s_]+", "-", text)

    # Remove non-alphanumeric characters except hyphens
    text = re.sub(r"[^a-z0-9-]", "", text)

    # Remove consecutive hyphens
    text = re.sub(r"-+", "-", text)

    # Remove leading/trailing hyphens
    text = text.strip("-")

    # Truncate to max length (break at hyphen if possible)
    if len(text) > max_length:
        text = text[:max_length]
        # Try to break at last hyphen
        last_hyphen = text.rfind("-")
        if last_hyphen > max_length // 2:
            text = text[:last_hyphen]

    return text


def safe_path(path: str) -> Path:
    """Convert a path string to a safe Path object.

    Ensures the path doesn't contain unsafe patterns like:
    - Leading slashes (absolute paths)
    - Parent directory references (..)
    - Null bytes

    Args:
        path: Input path string

    Returns:
        Safe Path object

    Raises:
        ValueError: If path contains unsafe patterns
    """
    # Check for null bytes
    if "\x00" in path:
        raise ValueError("Path contains null byte")

    # Normalize path separators
    normalized = path.replace("\\", "/")

    # Check for absolute path
    if normalized.startswith("/"):
        raise ValueError(f"Absolute paths not allowed: {path}")

    # Check for parent directory reference
    if ".." in normalized:
        raise ValueError(f"Parent directory references not allowed: {path}")

    # Create Path object
    result = Path(normalized)

    # Double-check resolved path doesn't escape
    try:
        # If any component is .., resolve will handle it
        parts = result.parts
        if ".." in parts:
            raise ValueError(f"Parent directory references not allowed: {path}")
    except Exception as e:
        raise ValueError(f"Invalid path: {path}") from e

    return result


def ensure_directory(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Path to the directory
    """
    path.mkdir(parents=True, exist_ok=True)


def is_safe_filename(filename: str) -> bool:
    """Check if a filename is safe (no path separators or special chars).

    Args:
        filename: Filename to check

    Returns:
        True if safe, False otherwise
    """
    # Check for path separators
    if "/" in filename or "\\" in filename:
        return False

    # Check for special patterns
    if filename in {".", "..", ""}:
        return False

    # Check for null bytes
    if "\x00" in filename:
        return False

    return True
