from typing import Optional
import discord

from logger import logger


class SecurityResult:

    def __init__(self, state: bool, message: str = ""):
        self.state = state
        self.message = message


class SecurityManager:
    """Manages security permissions for workflows and settings"""

    def _check_user_permissions(self, member: discord.Member, security_config: dict) -> bool:
        """Check if user has permission based on username or roles"""
        if not security_config.get('enabled', False):
            return True

        allowed_users = security_config.get('allowed_users', [])
        if member.name in allowed_users:
            return True

        allowed_roles = security_config.get('allowed_roles', [])
        member_roles = [role.name for role in member.roles]

        if any(role in allowed_roles for role in member_roles):
            return True

        return False

    def check_workflow_access(self,
                              member: discord.Member,
                              workflow_name: str,
                              workflow_config: dict) -> bool:
        """Check if user has access to the workflow"""
        security_config = workflow_config.get('security', {})
        return self._check_user_permissions(member, security_config)

    def check_setting_access(self,
                             member: discord.Member,
                             workflow_config: dict,
                             setting_name: str) -> bool:
        """Check if user has access to the setting"""
        if setting_name in ['__before', '__after']:
            return True  # System settings are always allowed

        settings = workflow_config.get('settings', [])
        setting_config = next((s for s in settings if s['name'] == setting_name), None)

        if not setting_config:
            return False

        security_config = setting_config.get('security', {})
        return self._check_user_permissions(member, security_config)

    def validate_settings_string(self,
                                 member: discord.Member,
                                 workflow_config: dict,
                                 settings_str: Optional[str]) -> tuple[bool, str]:
        """Validate all settings in a settings string"""
        if not settings_str:
            return True, ""

        settings_list = [s.strip() for s in settings_str.split(';') if s.strip()]

        for setting in settings_list:
            # Parse setting name (handle both simple and parameterized settings)
            setting_name = setting.split('(')[0].strip()

            if not self.check_setting_access(member, workflow_config, setting_name):
                return False, f"You don't have permission to use the '{setting_name}' setting"

        return True, ""


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
