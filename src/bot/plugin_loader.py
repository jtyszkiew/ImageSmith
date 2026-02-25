import importlib
import inspect
import traceback
from pathlib import Path

from logger import logger
from ..core.plugin import Plugin


class PluginLoader:
    """Loads plugins from a directory"""

    def __init__(self, plugins_path: str):
        self.plugins_path = plugins_path

    async def load_all(self, bot) -> list[Plugin]:
        """Load all plugins from the plugins directory and return instantiated plugin list"""
        plugins_dir = Path(self.plugins_path)
        if not plugins_dir.exists():
            logger.warning("No plugins directory found")
            return []

        import sys
        sys.path.append(str(Path.cwd()))

        plugins = []
        plugin_files = [f for f in plugins_dir.glob("*.py") if f.name != "__init__.py"]

        for plugin_file in plugin_files:
            logger.info(f"Loading plugin: {plugin_file}")

            module = self._load_module(plugin_file)
            if module is None:
                continue

            for plugin_class in self._find_plugin_classes(module):
                try:
                    plugin_instance = plugin_class(bot)
                    logger.debug("Running on_load...")
                    await plugin_instance.on_load()
                    logger.debug("on_load completed")
                    plugins.append(plugin_instance)
                    logger.info(f"Successfully loaded and registered plugin: {plugin_class.__name__}")
                except Exception as e:
                    logger.error(f"Error instantiating plugin {plugin_class.__name__}: {e}")
                    traceback.print_exc()

        logger.info(f"Loaded {len(plugins)} plugins:")
        for plugin in plugins:
            logger.info(f"- {plugin.__class__.__name__}")

        return plugins

    def _load_module(self, plugin_file: Path):
        """Load a module from a plugin file, returns None on failure"""
        try:
            spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
            if spec is None:
                logger.warning(f"Failed to get spec for {plugin_file}")
                return None

            module = importlib.util.module_from_spec(spec)
            if spec.loader is None:
                logger.warning(f"Failed to get loader for {plugin_file}")
                return None

            spec.loader.exec_module(module)
            logger.debug(f"Successfully loaded module: {module.__name__}")
            return module
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_file}: {e}")
            traceback.print_exc()
            return None

    def _find_plugin_classes(self, module) -> list[type]:
        """Find all Plugin subclasses in a module"""
        classes = []
        for item_name in dir(module):
            if item_name.startswith('__'):
                continue

            try:
                obj = getattr(module, item_name)
                if inspect.isclass(obj) and issubclass(obj, Plugin) and obj is not Plugin:
                    classes.append(obj)
            except Exception as e:
                logger.error(f"Error processing item {item_name}: {e}")

        return classes
