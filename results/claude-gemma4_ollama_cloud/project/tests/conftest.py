import os

import pytest


@pytest.fixture(scope="session")
def django_config() -> None:
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["DEBUG"] = "True"
    os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1"
