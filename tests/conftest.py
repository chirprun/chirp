import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    return None
