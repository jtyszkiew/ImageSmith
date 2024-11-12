from pyexpat.errors import messages
from textwrap import indent
from typing import Optional
import discord

from logger import logger


class SecurityResult:

    def __init__(self, state: bool, message: str = ""):
        self.state = state
        self.message = message


class SecurityManager:
    """Manages security permissions for workflows and settings"""

    def _check_user_permissions(self, interaction: discord.Interaction, security_config: dict) -> SecurityResult:
        """Check if user has permission based on username or roles"""
        member = interaction.user

        if not security_config.get('enabled', False):
            return SecurityResult(True)

        allowed_users = security_config.get('allowed_users', [])
        if len(allowed_users) > 0 and member.name not in allowed_users:
            return SecurityResult(False, f"You don't have permission to use this workflow.")

        allowed_roles = security_config.get('allowed_roles', [])
        member_roles = [role.name for role in member.roles]

        if len(allowed_roles) > 0 and not any(role in allowed_roles for role in member_roles):
            return SecurityResult(False, f"You don't have required roles to use this workflow.")

        allowed_channels = security_config.get('allowed_channels', [])
        if len(allowed_channels) > 0 and interaction.channel.name not in allowed_channels:
            return SecurityResult(False, f"This workflow is not allowed on this channel.")

        return SecurityResult(True)

    def check_workflow_access(self,
                              interaction: discord.Interaction,
                              workflow_name: str,
                              workflow_config: dict) -> SecurityResult:
        """Check if user has access to the workflow"""
        security_config = workflow_config.get('security', {})
        return self._check_user_permissions(interaction, security_config)

    def check_setting_access(self,
                             interaction: discord.Interaction,
                             workflow_config: dict,
                             setting_name: str) -> SecurityResult:
        """Check if user has access to the setting"""
        if setting_name in ['__before', '__after']:
            return SecurityResult(True)  # System settings are always allowed

        settings = workflow_config.get('settings', [])
        setting_config = next((s for s in settings if s['name'] == setting_name), None)

        if not setting_config:
            return SecurityResult(False, f"You don't have permission to use the '{setting_name}' setting")

        security_config = setting_config.get('security', {})
        return self._check_user_permissions(interaction, security_config)

    def validate_settings_string(self,
                                 interaction: discord.Interaction,
                                 workflow_config: dict,
                                 settings_str: Optional[str]) -> SecurityResult:
        """Validate all settings in a settings string"""
        if not settings_str:
            return SecurityResult(True)

        settings_list = [s.strip() for s in settings_str.split(';') if s.strip()]

        for setting in settings_list:
            # Parse setting name (handle both simple and parameterized settings)
            setting_name = setting.split('(')[0].strip()

            if not self.check_setting_access(interaction, workflow_config, setting_name).state:
                return SecurityResult(False, f"You don't have permission to use the '{setting_name}' setting")

        return SecurityResult(True)


class BasicSecurity:
    def __init__(self, bot):
        self.security_manager = bot.security_manager

        bot.hook_manager.register_hook('is.security', self.check_security)

    async def check_security(self,
                             interaction: discord.Interaction,
                             workflow_name: str,
                             workflow_type: str,
                             prompt: str,
                             workflow_config: dict,
                             settings: Optional[str] = None) -> SecurityResult:
        """Check if user has permission to use the workflow and settings"""
        try:
            result = self.security_manager.check_workflow_access(interaction, workflow_name, workflow_config)
            if not result.state:
                return SecurityResult(result.state, result.message)

            if settings:
                result = self.security_manager.validate_settings_string(
                    interaction.user,
                    workflow_config,
                    settings
                )

                if not result:
                    return SecurityResult(result.state, result.message)

            return SecurityResult(True)

        except Exception as e:
            logger.error(f"Error in security check: {e}")
            return SecurityResult(False, "An error occurred while checking permissions")
