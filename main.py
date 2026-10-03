#!/usr/bin/env python3

from bot import KoruxaBot
from config import Config


def main():
    config = Config.from_environment()

    application = KoruxaBot(config)

    application.run()


if __name__ == "__main__":
    main()

