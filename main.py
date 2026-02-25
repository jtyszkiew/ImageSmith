import asyncio
import os
import sys

from logger import logger
from src.bot.imagesmith import ImageSmith

async def main():
    bot = ImageSmith()

    logger.info("Starting bot...")
    try:
        await bot.start(os.getenv('DISCORD_TOKEN') or bot.workflow_manager.config['discord']['token'])
    except KeyboardInterrupt:
        print("\nShutting down...")
        await bot.cleanup()
    except Exception as e:
        print(f"Fatal error: {e}")
        await bot.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
