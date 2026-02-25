import pytest
from unittest.mock import Mock, patch
import discord

from src.core.security import SecurityManager, BasicSecurity, SecurityResult
from src.core.i18n import i18n

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
def mock_channel():
    channel = Mock()
    channel.name = "test_channel"
    return channel


@pytest.fixture
def mock_interaction(mock_member, mock_channel):
    interaction = Mock(spec=discord.Interaction)
    interaction.user = mock_member
    interaction.channel = mock_channel
    return interaction


@pytest.fixture
def security_manager():
    return SecurityManager()


class TestSecurityManager:
    def test_check_user_permissions_disabled_security(self, security_manager, mock_interaction):
        security_config = {"enabled": False}
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is True

    def test_check_user_permissions_allowed_user(self, security_manager, mock_interaction):
        security_config = {
            "enabled": True,
            "allowed_users": ["test_user"]
        }
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is True

    def test_check_user_permissions_allowed_role(self, security_manager, mock_interaction):
        security_config = {
            "enabled": True,
            "allowed_roles": ["role1"]
        }
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is True

    def test_check_user_permissions_denied(self, security_manager, mock_interaction):
        security_config = {
            "enabled": True,
            "allowed_users": ["other_user"],
            "allowed_roles": ["other_role"]
        }
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is False

    def test_check_workflow_access(self, security_manager, mock_interaction):
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["test_user"]
            }
        }
        assert security_manager.check_workflow_access(mock_interaction, "test_workflow", workflow_config).state is True

    def test_check_setting_access_system_settings(self, security_manager, mock_interaction):
        workflow_config = {}
        assert security_manager.check_setting_access(mock_interaction, workflow_config, "__before").state is True
        assert security_manager.check_setting_access(mock_interaction, workflow_config, "__after").state is True

    def test_check_setting_access_nonexistent_setting(self, security_manager, mock_interaction):
        workflow_config = {"settings": []}
        assert security_manager.check_setting_access(mock_interaction, workflow_config, "nonexistent").state is False

    def test_check_setting_access_allowed(self, security_manager, mock_interaction):
        workflow_config = {
            "settings": [{
                "name": "test_setting",
                "security": {
                    "enabled": True,
                    "allowed_users": ["test_user"]
                }
            }]
        }
        assert security_manager.check_setting_access(mock_interaction, workflow_config, "test_setting").state is True

    def test_validate_settings_string_empty(self, security_manager, mock_interaction):
        workflow_config = {}
        result = security_manager.validate_settings_string(mock_interaction, workflow_config, None)
        assert result.state is True
        assert result.message == ""

    def test_validate_settings_string_allowed(self, security_manager, mock_interaction):
        workflow_config = {
            "settings": [{
                "name": "setting1",
                "security": {
                    "enabled": True,
                    "allowed_users": ["test_user"]
                }
            }]
        }
        result = security_manager.validate_settings_string(mock_interaction, workflow_config, "setting1")
        assert result.state is True
        assert result.message == ""

    def test_validate_settings_string_denied(self, security_manager, mock_interaction):
        workflow_config = {
            "settings": [{
                "name": "setting1",
                "security": {
                    "enabled": True,
                    "allowed_users": ["other_user"]
                }
            }]
        }
        result = security_manager.validate_settings_string(mock_interaction, workflow_config, "setting1")
        assert result.state is False
        assert "permission" in result.message

    def test_check_channel_permissions_allowed_role(self, security_manager, mock_interaction):
        security_config = {
            "enabled": True,
            "allowed_channels": ["test_channel"]
        }
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is True

    def test_check_channel_permissions_not_allowed_role(self, security_manager, mock_interaction):
        security_config = {
            "enabled": True,
            "allowed_channels": ["other_channel"]
        }
        assert security_manager._check_user_permissions(mock_interaction, security_config).state is False


class TestSecurityManagerCheckSecurity:
    @pytest.fixture
    def security_manager(self):
        return SecurityManager()

    @pytest.mark.asyncio
    async def test_check_security_workflow_denied(self, security_manager):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["other_user"]
            }
        }

        result = await security_manager.check_security(
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
    async def test_check_security_settings_denied(self, security_manager):
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

        result = await security_manager.check_security(
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
    async def test_check_security_error_handling(self, security_manager):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock(spec=discord.Member)
        interaction.user.name = "test_user"

        # Simulate an error by passing invalid workflow_config
        result = await security_manager.check_security(
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
    async def test_check_security_success(self, security_manager, mock_interaction):
        workflow_config = {
            "security": {
                "enabled": True,
                "allowed_users": ["test_user"]
            }
        }

        result = await security_manager.check_security(
            interaction=mock_interaction,
            workflow_name="test_workflow",
            workflow_type="test",
            prompt="test prompt",
            workflow_config=workflow_config
        )

        assert isinstance(result, SecurityResult)
        assert result.state is True
        assert result.message == ""

    @pytest.mark.asyncio
    async def test_hook_registration(self):
        """Test that SecurityManager registers its check_security hook when hook_manager is provided"""
        mock_hook_manager = Mock()
        sm = SecurityManager(hook_manager=mock_hook_manager)
        mock_hook_manager.register_hook.assert_called_once_with('is.security', sm.check_security)
