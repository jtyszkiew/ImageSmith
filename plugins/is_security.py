from typing import Optional

import discord

from src.bot.imagesmith import SecurityResult, logger
from src.core.plugin import Plugin
from src.core.security import SecurityManager


class SecurityPlugin(Plugin):
    """Plugin to handle security checks for workflows and settings"""
    def __init__(self, bot):
        super().__init__(bot)
        self.security_manager = SecurityManager(bot.workflow_manager.config)

    async def on_load(self):
        """Register hooks when plugin loads"""
        await super().on_load()
        self.bot.hook_manager.register_hook('security_check', self.check_security)

    async def check_security(self,
                             interaction: discord.Interaction,
                             workflow_name: str,
                             workflow_type: str,
                             prompt: str,
                             workflow_config: dict,
                             settings: Optional[str] = None) -> SecurityResult:
        """Check if user has permission to use the workflow and settings"""
        try:
            if not self.security_manager.check_workflow_access(interaction.user, workflow_name, workflow_config):
                return SecurityResult(False, f"You don't have permission to use the '{workflow_name}' workflow")

            if settings:
                valid, error_msg = self.security_manager.validate_settings_string(
                    interaction.user,
                    workflow_config,
                    settings
                )

                if not valid:
                    return SecurityResult(False, error_msg)

            return SecurityResult(True)

        except Exception as e:
            logger.error(f"Error in security check: {e}")
            return SecurityResult(False, "An error occurred while checking permissions")
