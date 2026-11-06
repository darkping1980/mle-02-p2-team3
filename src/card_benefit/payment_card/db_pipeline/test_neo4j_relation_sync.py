import pytest

from .neo4j_relation_sync import main


def test_legacy_relationship_sync_is_disabled():
    with pytest.raises(SystemExit, match="legacy relationship sync is disabled"):
        main()
