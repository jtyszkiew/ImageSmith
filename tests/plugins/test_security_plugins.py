from unittest.mock import Mock

import pytest
from plugins.is_security import SecurityPlugin

class TestSecurityPlugin:
    @pytest.fixture
    def mock_bot(self):
        class MockHookManager:
            def __init__(self):
                self.hooks = {}

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        class MockBot:
            def __init__(self):
                self.hook_manager = MockHookManager()
                self.workflow_manager = Mock()
                self.workflow_manager.config = {
                    'security': {
                        'enabled': True,
                        'allowed_roles': ['Admin', 'Smith'],
                        'allowed_users': ['TestUser']
                    }
                }

        return MockBot()

    @pytest.fixture
    def security_plugin(self, mock_bot):
        return SecurityPlugin(mock_bot)

    @pytest.fixture
    def mock_interaction(self):
        class MockMember:
            def __init__(self):
                mock_role = Mock()
                mock_role.name = "Smith"
                self.name = "TestUser"
                self.roles = [mock_role]

        class MockInteraction:
            def __init__(self):
                self.user = MockMember()
                self.response = Mock()

        return MockInteraction()

    @pytest.mark.asyncio
    async def test_plugin_initialization(self, security_plugin):
        await security_plugin.on_load()
        assert 'is.security' in security_plugin.bot.hook_manager.hooks

    @pytest.mark.asyncio
    async def test_security_check_allowed_user(self, security_plugin, mock_interaction):
        workflow_config = {
            'security': {
                'enabled': True,
                'allowed_users': ['TestUser']
            }
        }

        result = await security_plugin.check_security(
            mock_interaction,
            'test_workflow',
            'txt2img',
            'test prompt',
            workflow_config
        )
        assert result.state == True

    @pytest.mark.asyncio
    async def test_security_check_allowed_role(self, security_plugin, mock_interaction):
        workflow_config = {
            'security': {
                'enabled': True,
                'allowed_roles': ['Smith']
            }
        }

        result = await security_plugin.check_security(
            mock_interaction,
            'test_workflow',
            'txt2img',
            'test prompt',
            workflow_config
        )
        assert result.state == True

    @pytest.mark.asyncio
    async def test_security_check_denied(self, security_plugin, mock_interaction):
        mock_interaction.user.name = "UnauthorizedUser"
        mock_interaction.user.roles = [Mock(name="UnauthorizedRole")]

        workflow_config = {
            'security': {
                'enabled': True,
                'allowed_users': ['TestUser'],
                'allowed_roles': ['Smith']
            }
        }

        result = await security_plugin.check_security(
            mock_interaction,
            'test_workflow',
            'txt2img',
            'test prompt',
            workflow_config
        )
        assert result.state == False
