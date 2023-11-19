"""Discord logger module.
"""
import sys
import os
import dataclasses
import functools
import inspect
import multiprocessing
import signal
import threading
import warnings
from datetime import datetime, timezone
from enum import StrEnum, IntEnum
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Callable, Literal, Type, Sequence

from discord_webhook import DiscordWebhook, DiscordEmbed
from dotenv import load_dotenv

from discord_logger.__version__ import __version__

_ENV_URL_KEY = "DISCORDLOGGER_WEBHOOK_URL"

_sentinel = object()
_manager = _sentinel

_package_name = "Discord-Logger"

if sys.platform == "win32":
    _sig_to_handle = [signal.SIGINT]
else:
    _sig_to_handle = [signal.SIGINT, signal.SIGHUP]


def _get_webhook_url() -> str:
    dotenv_found = load_dotenv()
    if _ENV_URL_KEY in os.environ:
        return os.environ[_ENV_URL_KEY]

    raise EnvironmentError(f"Could not find {_ENV_URL_KEY} in environment."
                           f" The .env {'was' if dotenv_found else 'was not'} found."
                           f" Please set {_ENV_URL_KEY} with the url of the discord webhook to use"
                           f" in your environment or in a local .env file.")


class LogLevel(IntEnum):
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LevelColor(StrEnum):
    NOTSET = "000000"
    DEBUG = "D5EAD8"
    INFO = "1974D2"
    WARNING = "FFE135"
    ERROR = "C90913"
    CRITICAL = "C90913"


_optional_keys = ['thread_name', 'process_name', 'func_name', 'module_name', 'line_number']


@dataclass
class LogRecord:
    level: LogLevel
    app_name: str
    message: str
    timestamp: datetime
    thread_name: str | None
    process_name: str | None
    line_number: int | None
    func_name: str | None
    module_name: str | None

    def get_optional_fields(self) -> dict[str, str | int]:
        return {k: v for k, v in dataclasses.asdict(self).items() if k in _optional_keys and v is not None}

    def get_fields(self) -> dict[str, str | int]:
        return {k: v for k, v in dataclasses.asdict(self).items() if v is not None}


@dataclass
class LogPayload:
    payload: LogRecord
    url: str | Sequence[str]


_embedded_key_to_name = {
    'thread_name': 'Thread',
    'process_name': 'Process',
    'func_name': 'Function',
    'module_name': 'Module',
    'line_number': 'Line',
}


def format_payload_embedded(log_record: LogRecord) -> DiscordEmbed:
    """
    :param log_record: The log record object containing information about the log message.
    :return: The formatted Discord embed object containing the log message.

    This method takes a log_record object and formats it into a Discord embed object.
    It sets the title of the embed as the log level, the description as the log message,
    and the author as the application name.
    It also sets the footer text as the package name and version. The embed color is determined based on the log level.
    The timestamp is set using the log record's timestamp in UTC timezone.

    Example usage:
    ```python
    log_record = LogRecord(...)
    embed = format_payload_embedded(log_record)
    ```
    """
    level_color = LevelColor[log_record.level.name]
    e = DiscordEmbed(title=f"`{log_record.level.name}`", description=log_record.message)
    e.set_author(name=log_record.app_name)
    e.set_footer(text=f"{_package_name} {__version__}")
    e.set_color(level_color)
    e.set_timestamp(timestamp=log_record.timestamp.astimezone(tz=timezone.utc))
    for field_name, field_value in log_record.get_optional_fields().items():
        e.add_embed_field(name=_embedded_key_to_name[field_name], value=field_value)
    return e


def _find_caller() -> tuple[str, int, str]:
    """Find the stack frame of the caller so that we can note the source file name, line number and function name.

    :return: caller file name, line number and function name
    """
    cur_frame = inspect.currentframe()
    caller_frame = inspect.getouterframes(cur_frame, 1)[-2]
    return caller_frame.filename, caller_frame.lineno, caller_frame.function


def _parse_level_to_int(level: int | str | LogLevel) -> int:
    """Return the log level as int

    :param level: Log level
    :return: Int log level
    """
    if isinstance(level, LogLevel):
        return level.value
    elif isinstance(level, int):
        return level
    else:
        return LogLevel[level].value


def _parse_level(level: int | str | LogLevel) -> LogLevel:
    """Parse the log level as an instance of `LogLevel`, can be a string, an int or LogLevel

    :param level: Log level
    :return: Parsed log level
    """
    if isinstance(level, LogLevel):
        return level
    elif isinstance(level, int):
        return LogLevel(level)
    else:
        return LogLevel[level]


class _Dispatcher(threading.Thread):
    def __init__(self):
        """ Basic (daemon) threaded class that dispatches logged messages to the registered URL.
        This class should not be used directly and only a single instance should be created in this module.
        """
        super().__init__(name="DiscordLoggerDispatcher", daemon=True)

        # Handle signals
        for s in _sig_to_handle:
            signal.signal(s, self._sig_handler)

        self._queue: Queue[LogPayload] = Queue()
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(block=True, timeout=1)
                self._dispatch(payload)
            except Empty:
                pass

        self._stop()

    def _sig_handler(self, _, __):
        self._stop_event.set()
        self._stop()

    @staticmethod
    def _dispatch(payload: LogPayload):
        """ Dispatch the payload to the registered webhook.

        :param payload: Payload to dispatch
        :return:
        """
        webhooks = [DiscordWebhook(url=u) for u in payload.url]
        e = format_payload_embedded(payload.payload)
        for webhook in webhooks:
            webhook.add_embed(e)

        for webhook in webhooks:
            response = webhook.execute(remove_embeds=True)
            if response.status_code != 200:
                warnings.warn(f"Failed to log message to {webhook.url}, status code: {response.status_code}")

    def _stop(self):
        if not self._queue.empty():
            warnings.warn("Dispatcher queue not empty")

    def stop(self):
        self._stop_event.set()


class DiscordLogger:
    _level: LogLevel
    _webhook: DiscordWebhook
    _message_fmt: str
    _dispatcher: Callable[[LogRecord], None]

    def __init__(self, name: str,
                 *,
                 webhook_url: str | None = None,
                 level: int | str | LogLevel = LogLevel.INFO,
                 embed_process_name: bool = False,
                 embed_thread_name: bool = False,
                 embed_line_number: bool = False,
                 embed_func_name: bool = False,
                 embed_module_name: bool = False,
                 embed_all: bool = False,
                 **discord_webhook_kwargs
                 ):
        """Logger class that send logged messages to Discord through webhook.
        The logged messages are dispatched either as a Discord Embedded (default) or plain message.

        Offer the same basic functionality as the `logging` module (`info`, `warning`, `error`, `critical`, `debug`),
        and filter the dispatched message by level.

        To use a logger in your application, use the factory method `get_logger(name)` that will create a new logger
        with the passed name (usually the application name or just `__name__`). If a logger is registered with that
        name, it will be returned.

        The logs can embed optional fields (all deactivate by default):
            - `embed_process_name`: name of the thread
            - `embed_thread_name`: name of the process
            - `embed_func_name`: name of the function
            - `embed_module_name`: name of the module
            - `embed_line_number`: line number
        Use `embed_all` to embed everything.

        Example:

        .. code-block:: python
            _logger = discord_logger.get_logger("MyAwesomApplication", level="INFO", embed_all=True)
            _logger.set_level(DEBUG)  # You can also set the logging level on an instance

            def any_function():
                _logger.info("Hello World!")
                _logger.debug("I need some bananas!")


        :param name: Name of this logger (usually the App name, or just __name__)
        :param level: log level. Default is INFO
        :param embed_process_name: Should log messages embed the process name. Default is False
        :param embed_thread_name: Should log messages embed the thread name. Default is False
        :param embed_line_number: Should log messages embed the line number. Default is False
        :param embed_func_name: Should log messages embed the function name. Default is False
        :param embed_module_name: Should log messages embed the module name. Default is False
        :param embed_all: Should log messages embed everything. Default is False
        """
        if not webhook_url:
            webhook_url = _get_webhook_url()
        self._app_name = name
        self._webhook = DiscordWebhook(url=webhook_url, **discord_webhook_kwargs)

        if embed_all:
            self._optional_fields = {k: True for k in _optional_keys}
        else:
            self._optional_fields = {
                'thread_name': embed_thread_name,
                'process_name': embed_process_name,
                'module_name': embed_module_name,
                'func_name': embed_func_name,
                'line_number': embed_line_number
            }

        self._set_log_level(level)

    def _dispatch_embed(self, log_record: LogRecord):
        embed = format_payload_embedded(log_record)
        self._webhook.add_embed(embed)

    def _set_log_level(self, level: LogLevel | int | str):
        if isinstance(level, LogLevel):
            self._level = level
        elif isinstance(level, int):
            self._level = LogLevel(level)
        else:
            self._level = LogLevel[level]

    @property
    def level(self) -> LogLevel:
        return self._level

    @level.setter
    def level(self, value: LogLevel | int | str):
        self._set_log_level(value)

    @property
    def embed_module_name(self) -> bool:
        return self._optional_fields['module_name']

    @embed_module_name.setter
    def embed_module_name(self, value: bool):
        self._optional_fields['module_name'] = value

    @property
    def embed_func_name(self) -> bool:
        return self._optional_fields['func_name']

    @embed_func_name.setter
    def embed_func_name(self, value: bool):
        self._optional_fields['func_name'] = value

    @property
    def embed_line_number(self) -> bool:
        return self._optional_fields['line_number']

    @embed_line_number.setter
    def embed_line_number(self, value: bool):
        self._optional_fields['line_number'] = value

    @property
    def embed_thread_name(self) -> bool:
        return self._optional_fields['thread_name']

    @embed_thread_name.setter
    def embed_thread_name(self, value: bool):
        self._optional_fields['thread_name'] = value

    @property
    def embed_process_name(self) -> bool:
        return self._optional_fields['process_name']

    @embed_process_name.setter
    def embed_process_name(self, value: bool):
        self._optional_fields['process_name'] = value

    def log(self, level: int | str | LogLevel, message: str) -> None:
        """Send a message to the Discord channel. The level acts as a filter by comparing it to the object log level.

        :param level: Log level
        :param message: The message to send
        """
        log_timestamp = datetime.now()
        level_int = _parse_level_to_int(level)
        if level_int < self._level.value:
            return
        log_level = _parse_level(level)
        fields = self.get_fields()
        log_record = LogRecord(
            level=log_level,
            app_name=self._app_name,
            timestamp=log_timestamp,
            message=message,
            thread_name=fields.get("thread_name", None),
            process_name=fields.get("process_name", None),
            line_number=fields.get("line_number", None),
            func_name=fields.get("func_name", None),
            module_name=fields.get("module_name", None),
        )
        self._dispatch_embed(log_record)
        response = self._webhook.execute(remove_embeds=True)
        if response.status_code != 200:
            warnings.warn(f"Failed to send log. Status code: {response.status_code}")

    def get_fields(self) -> dict[str, str | int]:
        """Returns the fields to be embedded into the message.

        :return: Embedded fields
        """
        fields = {}
        if any([self._optional_fields[k] for k in _optional_keys]):
            caller_path, caller_lineno, caller_func = _find_caller()
            caller_module_name = caller_path.split("/")[-1]
            # caller_package_name = caller_path.split("/")[-2]
            if self._optional_fields["func_name"]:
                fields["func_name"] = caller_func
            if self._optional_fields["module_name"]:
                fields["module_name"] = caller_module_name
            if self._optional_fields["line_number"]:
                fields["line_number"] = caller_lineno
        if self._optional_fields["thread_name"]:
            fields["thread_name"] = threading.current_thread().name
        if self._optional_fields["process_name"]:
            process_name = multiprocessing.current_process().name
            fields["process_name"] = process_name
        return fields

    info = functools.partialmethod(log, LogLevel.INFO.value)
    warning = functools.partialmethod(log, LogLevel.WARNING.value)
    error = functools.partialmethod(log, LogLevel.ERROR.value)
    critical = functools.partialmethod(log, LogLevel.CRITICAL.value)
    debug = functools.partialmethod(log, LogLevel.DEBUG.value)

    def get_log_record(self, log_level: LogLevel, message: str, timestamp: datetime) -> LogRecord:
        """Returns a LogRecord object with the passed level, message and timestamp.

        :param log_level: The to be logged level
        :param message: The message to be logged message
        :param timestamp: The to be logged timestamp
        :return: LogRecord object
        """
        optional_fields = self.get_fields()
        log_record = LogRecord(level=log_level, message=message, timestamp=timestamp, app_name=self._app_name,
                               **optional_fields)
        return log_record


class LoggerManager:
    _instance = None
    _lock: threading.Lock = threading.Lock()

    _registry: dict[str, Type[DiscordLogger]]
    _factory: Type[DiscordLogger]

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._registry = {}
                cls._instance._factory = DiscordLogger

        return cls._instance

    def __init__(self):
        """Very basic class that acts as a registry and manager for logger objects. Very roughly based on the
        Python logging module.

        This class should not be used directly and, in normal circumstances, there should be only one
        manager instanced in a process.

        Implemented as a singleton class (should be thread-safe).
        """
        dispatcher = _Dispatcher()

    def get_logger(self, name: str, **kwargs) -> DiscordLogger:
        """ Returns a logger with the given name. If there is none registered, a new one is created with the passed
        keyword arguments.

        :param name:
        :param kwargs: Keyword arguments to pass to the DiscordLogger instance
        :return:
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be a string. Got {type(name)}")
        if name not in self._registry:
            self._registry[name] = self._factory(name, **kwargs)
        return self._registry[name]


manager = LoggerManager()


def get_logger(name: str,
               *,
               webhook_url: str | None = None,
               embed_process_name: bool = False,
               embed_thread_name: bool = False,
               embed_line_number: bool = False,
               embed_func_name: bool = False,
               embed_module_name: bool = False,
               embed_all: bool = False) -> DiscordLogger:
    """Factory method for creating a DiscordLogger object. If a logger with the given name already exists, returns
    the existing logger.
    It allows customization of the logger's settings
    such as the webhook URL, embedding of caller information, and the payload message type.

    Example usage:
    .. code-block:: python
        logger = get_logger("AwesomeApp", webhook_url="https://discord.com/my/wehbhook", embed_process_name=True)
        logger.level = logging.DEBUG
        logger.info("Hello World!")

    :param name: Logger name (usually the application name or just __name__)
    :param webhook_url: Discord webhook URL
    :param embed_process_name: Add caller process name to the logs (default: False)
    :param embed_thread_name: Add caller thread name to the logs (default: False)
    :param embed_line_number: Add caller line number to the logs (default: False)
    :param embed_func_name:  Add caller function name to the logs (default: False)
    :param embed_module_name: Add caller module name to the logs (default: False)
    :param embed_all: Add all caller information
    :raise TypeError: If name is not a string
    :raise TypeError: If payload_type is not an instance of PayloadType enum or a string
    :raise ValueError: If payload_type is a string and not 'EMBEDDED' nor 'MESSAGE'
    :return: The logged `DiscordLogger` object
    """

    if not isinstance(name, str):
        raise TypeError(f"name must be a string. Got {type(name)}")

    return manager.get_logger(name,
                              webhook_url=webhook_url,
                              embed_process_name=embed_process_name,
                              embed_thread_name=embed_thread_name,
                              embed_line_number=embed_line_number,
                              embed_func_name=embed_func_name,
                              embed_module_name=embed_module_name,
                              embed_all=embed_all,)
