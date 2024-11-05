from pathlib import Path
import json
from datetime import datetime

from logger import logger
from src.core.plugin import Plugin

class PromptLoggerPlugin(Plugin):
    """Plugin to log all prompts and their results"""
    def __init__(self, bot):
        super().__init__(bot)
        self.log_dir = Path("logs/prompts")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def on_load(self):
        """Register hooks when plugin loads"""
        await super().on_load()

        self.bot.hook_manager.register_hook('pre_generate', self.log_prompt)
        self.bot.hook_manager.register_hook('generation_complete', self.log_result)

    async def log_prompt(self, workflow_json: dict, prompt: str):
        """Log the prompt before generation"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_data = {
                'timestamp': timestamp,
                'prompt': prompt,
                'workflow': workflow_json
            }

            log_file = self.log_dir / f"prompt_{timestamp}.json"
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
            logger.debug(f"[PromptLoggerPlugin] Logged prompt to: {log_file}")
        except Exception as e:
            logger.error(f"[PromptLoggerPlugin] Error logging prompt: {e}")

    async def log_result(self, prompt: str, image_url: str, success: bool):
        """Log the generation result"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_data = {
                'timestamp': timestamp,
                'prompt': prompt,
                'image_url': image_url,
                'success': success
            }

            log_file = self.log_dir / f"result_{timestamp}.json"
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
            logger.debug(f"[PromptLoggerPlugin] Logged result to: {log_file}")
        except Exception as e:
            logger.error(f"[PromptLoggerPlugin] Error logging result: {e}")
