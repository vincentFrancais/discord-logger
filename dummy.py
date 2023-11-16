from discord_logger import get_logger

_URL = r"https://discordapp.com/api/webhooks/1174043546957905982/0C67JBlZQWFhZbOYxJK9ehh6aq8Xv1U2IXLNwU0Mf3KbZ9KBVHeZ2qVO-rT_YKz_3o0h"

_logger = get_logger("TESTAPP", webhook_url=_URL)


def main():
    _logger.info("this a test message")


if __name__ == "__main__":
    main()
