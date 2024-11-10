import pytest
from unittest.mock import Mock, patch
import discord

from src.core.security import SecurityManager, BasicSecurity, SecurityResult

@pytest.fixture
def mock_member():
    member = Mock(spec=discord.Member)
    member.name = "test_user"

    # Create roles with properly mocked name property
    role1 = Mock(spec=discord.Role)
    role1.name = "role1"  # Directly set the name property

    role2 = Mock(spec=discord.Role)
    role2.name = "role2"  # Directly set the name property

    member.roles = [role1, role2]
    return member

@pytest.fixture
def security_manager():
    return SecurityManager()

@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.security_manager = SecurityManager()
    bot.hook_manager = Mock()
    return bot

@pytest.fixture
def basic_security(mock_bot):
    return BasicSecurity(mock_bot)

class TestSecurityManager:
    def test_check_user_permissions_disabled_security(self, security_manager, mock_member):
        security_config = {"enabled": False}
        assert security_manager._check_user_permissions(mock_member, security_config) is True

    def test_check_user_permissions_allowed_user(self, security_manager, mock_member):
        security_config = {
            "enabled": True,
            "allowed_users": ["test_user"]
        }
        assert security_manager._check_user_permissions(mock_member, security_config) is True

    def test_check_user_permissions_allowed_role(self, security_manager, mock_member):
        security_config = {
            "enabled": True,
            "allowed_roles": ["role1"]
        }
        assert security_manager._check_user_permissions(mock_member, security_config) is True

    def test_check_user_permissions_denied(self, security_manager, mock_member):
        security_config = {
            "enabled": True,
            "allowed_users": ["other_user"],
            "allowed_roles": ["other_role"]
        }
        assert security_manager._check_user_permissions(mock_member, security_config) is False

    def test_check_workflow_access(self, security_manager, mock_member):
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["test_user"]
            }
        }
        assert security_manager.check_workflow_access(mock_member, "test_workflow", workflow_config) is True

    def test_check_setting_access_system_settings(self, security_manager, mock_member):
        workflow_config = {}
        assert security_manager.check_setting_access(mock_member, workflow_config, "__before") is True
        assert security_manager.check_setting_access(mock_member, workflow_config, "__after") is True

    def test_check_setting_access_nonexistent_setting(self, security_manager, mock_member):
        workflow_config = {"settings": []}
        assert security_manager.check_setting_access(mock_member, workflow_config, "nonexistent") is False

    def test_check_setting_access_allowed(self, security_manager, mock_member):
        workflow_config = {
            "settings": [{
                "name": "test_setting",
                "security": {
                    "enabled": True,
                    "allowed_users": ["test_user"]
                }
            }]
        }
        assert security_manager.check_setting_access(mock_member, workflow_config, "test_setting") is True

    def test_validate_settings_string_empty(self, security_manager, mock_member):
        workflow_config = {}
        valid, msg = security_manager.validate_settings_string(mock_member, workflow_config, None)
        assert valid is True
        assert msg == ""

    def test_validate_settings_string_allowed(self, security_manager, mock_member):
        workflow_config = {
            "settings": [{
                "name": "setting1",
                "security": {
                    "enabled": True,
                    "allowed_users": ["test_user"]
                }
            }]
        }
        valid, msg = security_manager.validate_settings_string(mock_member, workflow_config, "setting1")
        assert valid is True
        assert msg == ""

    def test_validate_settings_string_denied(self, security_manager, mock_member):
        workflow_config = {
            "settings": [{
                "name": "setting1",
                "security": {
                    "enabled": True,
                    "allowed_users": ["other_user"]
                }
            }]
        }
        valid, msg = security_manager.validate_settings_string(mock_member, workflow_config, "setting1")
        assert valid is False
        assert "permission" in msg

class TestBasicSecurity:
    @pytest.mark.asyncio
    async def test_check_security_workflow_denied(self, basic_security):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["other_user"]
            }
        }

        result = await basic_security.check_security(
            interaction=interaction,
            workflow_name="test_workflow",
            workflow_type="test",
            prompt="test prompt",
            workflow_config=workflow_config
        )

        assert isinstance(result, SecurityResult)
        assert result.state is False
        assert "permission" in result.message

    @pytest.mark.asyncio
    async def test_check_security_settings_denied(self, basic_security):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["test_user"]
            },
            "settings": [{
                "name": "setting1",
                "security": {
                    "enabled": True,
                    "allowed_users": ["other_user"]
                }
            }]
        }

        result = await basic_security.check_security(
            interaction=interaction,
            workflow_name="test_workflow",
            workflow_type="test",
            prompt="test prompt",
            workflow_config=workflow_config,
            settings="setting1"
        )

        assert isinstance(result, SecurityResult)
        assert result.state is False
        assert "permission" in result.message

    @pytest.mark.asyncio
    async def test_check_security_error_handling(self, basic_security):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        interaction.user.name = "test_user"

        # Simulate an error by passing invalid workflow_config
        result = await basic_security.check_security(
            interaction=interaction,
            workflow_name="test_workflow",
            workflow_type="test",
            prompt="test prompt",
            workflow_config=None
        )

        assert isinstance(result, SecurityResult)
        assert result.state is False
        assert "error occurred" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_security_success(self, basic_security):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        interaction.user.name = "test_user"
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["test_user"]
            }
        }

        result = await basic_security.check_security(
            interaction=interaction,
            workflow_name="test_workflow",
            workflow_type="test",
            prompt="test prompt",
            workflow_config=workflow_config
        )

        assert isinstance(result, SecurityResult)
        assert result.state is True
        assert result.message == ""
