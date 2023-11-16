# Adapted

from datetime import datetime
from discord_logger.logger import LogRecord, LogLevel, format_payload_message


class TestFormatPayloadMessage:

    #  Formats a message string using fields from a log record
    def test_format_message_with_fields(self):
        ts = datetime.now()
        log_record = LogRecord(level=LogLevel.INFO, app_name="TestApp", message="Test message",
                               timestamp=ts, thread_name="Thread1", process_name="Process1",
                               line_number=10, func_name="test_func", module_name="test_module")
        message_fmt = ("Level: {level}, App Name: {app_name}, Message: {message}, Timestamp: {timestamp}, "
                       "Thread Name: {thread_name}, Process Name: {process_name}, Line Number: {line_number}, "
                       "Function Name: {func_name}, Module Name: {module_name}")
        expected_message = (f"Level: INFO, App Name: TestApp, Message: Test message, Timestamp: "
                            f"{ts.strftime('%Y-%m-%d %H:%M:%S')}, "
                            "Thread Name: Thread1, Process Name: Process1, Line Number: 10, "
                            "Function Name: test_func, Module Name: test_module")

        result = format_payload_message(log_record, message_fmt)

        assert result == expected_message
