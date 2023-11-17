import os

import discord_logger.logger
import pytest


@pytest.fixture
def dummy_webhook_url():
    os.environ['DISCORDLOGGER_WEBHOOK_URL'] = "https://dummy.com"
    yield
    del os.environ['DISCORDLOGGER_WEBHOOK_URL']


@pytest.fixture
def reinit_manager():
    discord_logger.logger.manager._registry.clear()
    return
