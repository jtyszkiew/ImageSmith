from logger import logger


class Plugin:
    """Base class for bot plugins"""

    def __init__(self, bot):
        logger.debug(f"[{self.__class__.__name__}] Initializing...")
        self.bot = bot
        logger.debug(f"[{self.__class__.__name__}] Initialized")

    async def on_load(self):
        """Called when the plugin is loaded"""
        logger.debug(f"[{self.__class__.__name__}] Loading...")
        logger.debug(f"[{self.__class__.__name__}] Loaded")

    async def on_unload(self):
        """Called when the plugin is unloaded"""
        logger.debug(f"[{self.__class__.__name__}] Unloading...")
        logger.debug(f"[{self.__class__.__name__}] Unloaded")
