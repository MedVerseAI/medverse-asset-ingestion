import os

import pytest

from medverse import settings


@pytest.fixture(autouse=True)
def _clean_settings_state():
    """configure() exports --mode/--config to the environment; never let that leak between tests."""
    def wipe():
        for var in (settings.ENV_MODE, settings.ENV_CONFIG):
            os.environ.pop(var, None)
        settings.configure(None, None)
    wipe()
    yield
    wipe()
