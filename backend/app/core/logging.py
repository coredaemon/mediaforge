from loguru import logger


def configure_logging() -> None:
    logger.disable("aiosqlite")
