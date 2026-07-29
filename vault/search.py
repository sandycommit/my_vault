"""PostgreSQL full-text search over vault items.

Uses the GIN-indexed `search_vector` column (see vault/models.py) instead of
`content__icontains`, so lookups stay fast as the table grows into the
hundreds of thousands of rows.
"""
from django.contrib.postgres.search import SearchQuery, SearchRank

from .models import VaultItem


def search_items(user, query_text):
    """Return a ranked queryset of the user's non-deleted items. Callers paginate
    the result themselves (see views.search_view)."""
    query_text = (query_text or "").strip()
    if not query_text:
        return VaultItem.objects.none()

    search_query = SearchQuery(query_text, config="english")
    return (
        VaultItem.objects.filter(user=user, is_deleted=False, search_vector=search_query)
        .annotate(rank=SearchRank("search_vector", search_query))
        .order_by("-rank", "-updated_at", "-created_at")
    )
