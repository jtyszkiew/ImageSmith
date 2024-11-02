# tests/bot/test_commands.py
import pytest
import discord
from unittest.mock import Mock, AsyncMock

from src.bot.commands import forge_command, reforge_command, workflows_command


class TestImageCommands:
    @pytest.fixture
    def mock_bot(self):
        bot = AsyncMock()
        # Simulate the handle_generation method
        async def handle_generation(interaction, *args, **kwargs):
            await interaction.response.send_message("Generation complete")

        bot.handle_generation = AsyncMock(side_effect=handle_generation)
        bot.workflow_manager = Mock()
        bot.workflow_manager.get_workflow.return_value = {
            'type': 'txt2img',
            'workflow': 'test.json'
        }
        bot.workflow_manager.get_default_workflow.return_value = 'default_workflow'
        bot.workflow_manager.get_selectable_workflows.return_value = {}
        return bot

    @pytest.fixture
    def mock_interaction(self):
        interaction = AsyncMock()
        interaction.user = Mock()
        interaction.user.mention = "@test_user"
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_forge_command(self, mock_bot, mock_interaction):
        command = forge_command(mock_bot)
        await command.callback(
            mock_interaction,
            prompt="test prompt",
            workflow=None,
            settings=None
        )

        # Verify that the response send_message was called
        mock_interaction.response.send_message.assert_called()

        # Verify handle_generation was called with correct parameters
        mock_bot.handle_generation.assert_called_once_with(
            mock_interaction, 'txt2img', "test prompt", None, None
        )

    @pytest.mark.asyncio
    async def test_reforge_command(self, mock_bot, mock_interaction):
        command = reforge_command(mock_bot)
        mock_attachment = Mock(spec=discord.Attachment)
        mock_attachment.filename = "test.png"
        mock_attachment.read = AsyncMock(return_value=b"fake_image_data")

        await command.callback(
            mock_interaction,
            image=mock_attachment,
            prompt="test prompt",
            workflow=None,
            settings=None
        )

        # Verify that the response send_message was called
        mock_interaction.response.send_message.assert_called()

        # Verify handle_generation was called with correct parameters
        mock_bot.handle_generation.assert_called_once_with(
            mock_interaction, 'img2img', "test prompt", None, None, mock_attachment
        )

    @pytest.mark.asyncio
    async def test_workflows_command(self, mock_bot, mock_interaction):
        # Mock the get_selectable_workflows method
        mock_bot.workflow_manager.get_selectable_workflows.return_value = {
            'workflow1': {'type': 'txt2img', 'description': 'Test workflow'}
        }

        command = workflows_command(mock_bot)
        await command.callback(
            mock_interaction,
            type=None
        )

        # Verify that the response send_message was called
        mock_interaction.response.send_message.assert_called()

        # Extract the embed from the send_message call arguments
        embed = mock_interaction.response.send_message.call_args[1]['embed']
        assert isinstance(embed, discord.Embed)
        assert "workflow1" in embed.fields[0].name
