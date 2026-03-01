import asyncio
import logging

from app.db.session import init_db


logger = logging.getLogger("tgmocks.bootstrap_db")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    logger.info("database schema checked/created successfully")


if __name__ == "__main__":
    asyncio.run(main())

