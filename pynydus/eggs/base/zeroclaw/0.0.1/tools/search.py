"""Sample ZeroClaw tool module bundled in the base egg for layout testing.

Exposes a minimal ``search`` callable used as a stand-in for real tool code
when validating spawn/hatch round-trips.
"""


def search(query: str) -> str:
    """Search for information across available knowledge sources.

    Args:
        query: The search query string.

    Returns:
        Search results as a formatted string.
    """
    return f"Results for: {query}"
