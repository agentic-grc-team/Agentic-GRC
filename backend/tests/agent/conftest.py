import pytest

from app.agent.knowledge import load_kb
from tests.agent.helpers import KB_PATH


@pytest.fixture
def kb():
    return load_kb(KB_PATH)
