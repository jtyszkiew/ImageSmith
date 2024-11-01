# plugin_base.py
class Plugin:
    """Base class for bot plugins"""
    def __init__(self, bot):
        print(f"[{self.__class__.__name__}] Initializing...")
        self.bot = bot
        print(f"[{self.__class__.__name__}] Initialized")

    async def on_load(self):
        """Called when the plugin is loaded"""
        print(f"[{self.__class__.__name__}] Loading...")
        print(f"[{self.__class__.__name__}] Loaded")

    async def on_unload(self):
        """Called when the plugin is unloaded"""
        print(f"[{self.__class__.__name__}] Unloading...")
        print(f"[{self.__class__.__name__}] Unloaded")
