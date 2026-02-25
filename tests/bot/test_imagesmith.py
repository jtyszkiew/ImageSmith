import pytest
import pytest_asyncio
import yaml
from unittest.mock import Mock, AsyncMock, patch

from src.bot.imagesmith import ImageSmith, SecurityResult


class TestImageSmith:
    @pytest.fixture
    def mock_config(self, tmp_path):
        config = {
            'comfyui': {
                'instances': [{
                    'url': 'http://localhost:8188'
                }]
            },
            'workflows': {
                'test_workflow': {
                    'type': 'txt2img',
                    'workflow': 'test.json',
                    'default': True
                }
            }
        }
        config_file = tmp_path / "configuration.yml"
        with open(config_file, 'w') as f:
            yaml.dump(config, f)
        return str(config_file)

    @pytest_asyncio.fixture
    async def bot(self, mock_config, tmp_path):
        """Create a bot instance with mocked parent class and dependencies"""
        with patch('src.comfy.workflow_manager.WorkflowManager._load_config') as mock_wm:
            mock_wm.return_value = {
                'comfyui': {
                    'instances': [{
                        'url': 'http://localhost:8188'
                    }]
                },
                'workflows': {
                    'test_workflow': {
                        'type': 'txt2img',
                        'workflow': 'test.json',
                        'default': True
                    }
                }
            }
            # mock_get_default_workflow.return_value = "test_workflow"

            # Create bot instance
            bot = ImageSmith(plugins_path=f"{tmp_path}/plugins")

            try:
                yield bot
            finally:
                await bot.cleanup()

    @pytest.mark.asyncio
    async def test_bot_initialization(self, bot):
        """Test bot initialization and intents configuration"""


        # Basic attribute checks
        assert bot.workflow_manager is not None
        assert bot.hook_manager is not None
        assert isinstance(bot.plugins, list)
        assert isinstance(bot.active_generations, dict)
        assert bot.generation_queue is not None
        assert bot.form_manager is not None

    @pytest.mark.asyncio
    async def test_setup_hook(self, bot):
        """Test setup hook functionality"""


        # Create mock ComfyUIClient
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()

        # Patch necessary components
        with patch('src.bot.imagesmith.ComfyUIClient', return_value=mock_client) as mock_client_class, \
                patch.object(bot, 'load_plugins', new_callable=AsyncMock) as mock_load_plugins, \
                patch.object(bot.tree, 'add_command') as mock_add_command, \
                patch.object(bot.tree, 'sync') as mock_add_command, \
                patch('sys.exit') as mock_exit:
            await bot.setup_hook()

            # Verify operations
            mock_load_plugins.assert_called_once()
            mock_client.connect.assert_called_once()

            # Verify command registration
            assert bot.tree.add_command.call_count == 4

            # Get command names from registration calls
            command_calls = bot.tree.add_command.call_args_list
            registered_commands = [call.args[0].name for call in command_calls]

            # Verify all expected commands were registered
            assert set(registered_commands) == {'forge', 'reforge', 'upscale', 'workflows'}

            # Verify sync was called and exit wasn't
            assert bot.tree.sync.called
            mock_exit.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_hook_comfy_connection_failure(self, bot):
        """Test setup hook handling ComfyUI connection failure"""


        mock_client = AsyncMock()
        mock_client.connect.side_effect = Exception("Connection failed")

        with patch('src.bot.imagesmith.ComfyUIClient', return_value=mock_client) as mock_client_class, \
                patch.object(bot, 'cleanup', new_callable=AsyncMock) as mock_cleanup, \
                patch('sys.exit') as mock_exit:
            await bot.setup_hook()

            mock_client.connect.assert_called_once()
            mock_cleanup.assert_called()
            mock_exit.assert_called()

    @pytest.mark.asyncio
    async def test_setup_hook_command_sync_failure(self, bot):
        """Test setup hook handling command sync failure"""


        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()

        with patch('src.bot.imagesmith.ComfyUIClient', return_value=mock_client) as mock_client_class, \
                patch.object(bot, 'load_plugins', new_callable=AsyncMock) as mock_load_plugins, \
                patch.object(bot.tree, 'sync', side_effect=Exception("Sync failed")), \
                patch.object(bot, 'cleanup', new_callable=AsyncMock) as mock_cleanup, \
                patch('sys.exit') as mock_exit:
            await bot.setup_hook()

            mock_cleanup.assert_called_once()
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_load_plugins(self, bot, tmp_path):

        # Create temporary plugin
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a test plugin file
        plugin_content = """
from src.core.plugin import Plugin
class TestPlugin(Plugin):
    async def on_load(self):
        await super().on_load()
        """

        plugin_file = plugins_dir / "test_plugin.py"
        plugin_file.write_text(plugin_content)

        # Mock plugin path
        await bot.load_plugins()
        # Verify plugin was loaded
        assert len(bot.plugins) > 0

    @pytest.mark.asyncio
    async def test_handle_generation(self, bot):
        import discord

        # Mock interaction
        interaction = AsyncMock()
        interaction.user = Mock()
        interaction.user.mention = "@test_user"

        # Mock the message returned by original_response with a real embed
        embed = discord.Embed(title="Test")
        embed.add_field(name="Status", value="Starting...", inline=False)
        message = AsyncMock()
        message.embeds = [embed]
        interaction.original_response.return_value = message

        # Mock workflow preparation and form processing (called before queueing)
        with patch.object(bot.workflow_manager, 'prepare_workflow', return_value={'test': 'workflow'}):
            bot.form_manager = AsyncMock()
            bot.form_manager.process_workflow_form.return_value = {'test': 'modified_workflow'}

            await bot.handle_generation(
                interaction=interaction,
                workflow_type='txt2img',
                prompt="test prompt"
            )

        assert interaction.response.send_message.called
        assert bot.generation_queue.get_queue_position() >= 0

    @pytest.mark.asyncio
    async def test_handle_generation_security_failure(self, bot):

        # Mock interaction
        interaction = AsyncMock()

        # Mock security check failure
        with patch('src.core.hook_manager.HookManager.execute_hook') as mock_execute_hook:
            mock_execute_hook.return_value = [
                SecurityResult(False, "Access denied")
            ]

            await bot.handle_generation(
                interaction=interaction,
                workflow_type='txt2img',
                prompt="test prompt"
            )

            # Verify error message was sent
            assert interaction.response.send_message.called
            args = interaction.response.send_message.call_args
            embed = args[1]['embed']
            assert "Access denied" in embed.description

    @pytest.mark.asyncio
    async def test_handle_generation_with_image(self, bot):

        # Mock interaction and attachment
        interaction = AsyncMock()
        interaction.user = Mock()
        interaction.user.mention = "@test_user"

        mock_attachment = AsyncMock()
        mock_attachment.filename = "test.png"
        mock_attachment.read.return_value = b"fake_image_data"

        await bot.handle_generation(
            interaction=interaction,
            workflow_type='img2img',
            prompt="test prompt",
            input_image=mock_attachment
        )

        assert interaction.response.send_message.called
        assert bot.generation_queue.get_queue_position() >= 0

    @pytest.mark.asyncio
    async def test_handle_invalid_workflow(self, bot):

        # Mock interaction
        interaction = AsyncMock()

        await bot.handle_generation(
            interaction=interaction,
            workflow_type='txt2img',
            prompt="test prompt",
            workflow="nonexistent_workflow"
        )

        # Verify error message
        assert interaction.response.send_message.called
        args = interaction.response.send_message.call_args
        embed = args[1]['embed']
        assert "not found" in embed.description

    @pytest.mark.asyncio
    async def test_handle_workflow_type_mismatch(self, bot):

        # Mock interaction
        interaction = AsyncMock()

        await bot.handle_generation(
            interaction=interaction,
            workflow='test_workflow',
            workflow_type='img2img',  # Mismatched type
            prompt="test prompt"
        )

        # Verify error message
        assert interaction.response.send_message.called
        args = interaction.response.send_message.call_args
        embed = args[1]['embed']
        assert "not a img2img workflow" in embed.description

    @pytest.mark.asyncio
    async def test_cleanup(self, bot):

        # Mock ComfyUI client
        bot.comfy_client = AsyncMock()

        await bot.cleanup()

        assert bot.comfy_client.close.called
