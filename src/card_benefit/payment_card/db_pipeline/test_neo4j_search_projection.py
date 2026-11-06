import pytest

from .neo4j_search_projection_sync import main


def test_legacy_projection_sync_is_disabled():
    with pytest.raises(SystemExit, match="legacy projection sync is disabled"):
        main()
