import os
from collections import defaultdict
from typing import Any, Optional

import yaml

from logger import logger


class _SafeFormatDict(defaultdict):
    """Dict subclass that returns '{key}' for missing format variables instead of raising."""

    def __missing__(self, key):
        logger.warning(f"Missing format variable '{key}' in string template")
        return f"{{{key}}}"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class I18n:
    def __init__(self):
        self._data: dict = {}
        self.env: str = "prod"

    def load(self, defaults_path: str = "i18n.yml", overrides: Optional[dict] = None, language: Optional[str] = None, env: str = "prod"):
        """Load string layers: defaults -> language file -> user overrides."""
        self.env = env

        # Layer 1: defaults
        self._data = self._load_yaml(defaults_path)

        # Layer 2: language file
        if language:
            defaults_dir = os.path.dirname(os.path.abspath(defaults_path))
            base_name = os.path.basename(defaults_path)
            lang_parts = os.path.splitext(base_name)
            lang_file = os.path.join(defaults_dir, f"{lang_parts[0]}.{language}{lang_parts[1]}")
            logger.info(f"Loading language file: {lang_file}")
            lang_data = self._load_yaml(lang_file)
            if lang_data:
                self._data = _deep_merge(self._data, lang_data)
                logger.info(f"Language '{language}' loaded successfully")
            else:
                logger.warning(f"Language '{language}' file was empty or not found")

        # Layer 3: user overrides from configuration.yml
        if overrides and isinstance(overrides, dict):
            self._data = _deep_merge(self._data, overrides)

    def _load_yaml(self, path: str) -> dict:
        """Load a YAML file, returning empty dict on any failure."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            logger.warning(f"Strings file not found: '{path}'")
            return {}
        except Exception as e:
            logger.warning(f"Failed to load strings file '{path}': {e}")
            return {}

    def _resolve(self, key: str) -> Any:
        """Walk nested dict by dot-separated path."""
        parts = key.split('.')
        current = self._data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def get(self, key: str, **kwargs) -> str:
        """Get a string by dot-path key, with optional variable substitution."""
        value = self._resolve(key)
        if value is None or not isinstance(value, str):
            if value is None:
                logger.warning(f"Missing string key: '{key}'")
            return key

        if kwargs:
            safe_dict = _SafeFormatDict(str)
            safe_dict.update(kwargs)
            return value.format_map(safe_dict)

        return value

    def raw(self, key: str) -> Optional[str]:
        """Get a raw template string without substitution. Returns None if missing."""
        value = self._resolve(key)
        if isinstance(value, str):
            return value
        return None

    def sanitize_error(self, raw_error: str) -> str:
        """Return raw error in dev mode, generic message in prod."""
        if self.env == "dev":
            return raw_error
        return self.get("error.generic_message")


i18n = I18n()
