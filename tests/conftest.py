import os

import pytest


@pytest.fixture
def dummy_webhook_url():
    os.environ['DISCORDLOGGER_WEBHOOK_URL'] = "https://dummy.com"
    yield
    del os.environ['DISCORDLOGGER_WEBHOOK_URL']
