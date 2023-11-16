# Generated by CodiumAI
# Adapted
import multiprocessing
import os
import threading

import pytest

from discord_logger import DiscordLogger
from discord_logger.logger import _find_caller, _get_webhook_url


def test_env_variable_not_set(mocker):
    mocker.patch.dict(os.environ, clear=True)
    with pytest.raises(EnvironmentError) as e:
        _get_webhook_url()


class TestDiscordLogger:

    #  DiscordLogger can be instantiated with a name and a webhook URL
    def test_instantiation(self):
        logger = DiscordLogger("MyApp", webhook_url="https://discord.com/webhook")
        assert logger._app_name == "MyApp"
        assert logger._webhook.url == "https://discord.com/webhook"

    #  DiscordLogger can log messages with different log levels (debug, info, warning, error, critical)
    def test_logging(self, mocker):
        logger = DiscordLogger("MyApp", webhook_url="https://discord.com/webhook")
        mocker.patch.object(logger._webhook, 'execute', return_value=mocker.Mock(status_code=200))
        logger.debug("This is a debug message")
        logger.info("This is an info message")
        logger.warning("This is a warning message")
        logger.error("This is an error message")
        logger.critical("This is a critical message")

    #  DiscordLogger can format log messages with optional fields
    #  (thread name, process name, function name, module name, line number)
    def test_formatting(self):
        logger = DiscordLogger("MyApp", webhook_url="https://discord.com/webhook", embed_all=True)
        fields = logger.get_fields()
        assert fields['thread_name'] == threading.current_thread().name
        assert fields['process_name'] == multiprocessing.current_process().name
        (caller_path, caller_lineno, caller_func) = _find_caller()
        caller_module_name = caller_path.split('/')[-1]
        assert fields['module_name'] == caller_module_name
        assert fields['func_name'] == caller_func
        assert fields['line_number'] == caller_lineno

    #  DiscordLogger raises an error if an unknown payload type is set
    def test_unknown_payload_type(self):
        with pytest.raises(ValueError):
            logger = DiscordLogger("MyApp", webhook_url="https://discord.com/webhook", payload_type=2)

    #  DiscordLogger raises an error if the webhook URL is not provided and cannot be found in the environment
    def test_missing_webhook_url(self):
        with pytest.raises(EnvironmentError):
            logger = DiscordLogger("MyApp")

    #  DiscordLogger warns if the log message fails to send to the webhook
    def test_failed_log_send(self, mocker):
        logger = DiscordLogger("MyApp", webhook_url="https://discord.com/webhook")
        mocker.patch.object(logger._webhook, 'execute', return_value=mocker.Mock(status_code=400))
        with pytest.warns(UserWarning):
            logger.info("This is an info message")
