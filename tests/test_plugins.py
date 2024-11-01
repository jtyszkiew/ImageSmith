import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import json
from plugin_base import Plugin
from plugins.prompt_logger import PromptLoggerPlugin

@pytest.mark.asyncio
async def test_prompt_logger_plugin(tmp_path):
    """Test PromptLoggerPlugin"""
    # Setup
    mock_bot = MagicMock()
    mock_bot.hook_manager = MagicMock()
    mock_bot.hook_manager.register_hook = MagicMock()

    # Create log directory
    log_dir = tmp_path / "logs" / "prompts"
    log_dir.mkdir(parents=True)

    # Create plugin with mocked log directory
    plugin = PromptLoggerPlugin(mock_bot)
    plugin.log_dir = log_dir

    # Test initialization
    assert plugin.bot == mock_bot
    assert plugin.log_dir.exists()

    # Test on_load
    await plugin.on_load()

    # Verify hook registration (should be called exactly twice)
    assert mock_bot.hook_manager.register_hook.call_count == 2

    # Test logging functionality
    workflow_json = {"test": "workflow"}
    test_prompt = "test prompt"

    await plugin.log_prompt(workflow_json, test_prompt)

    # Check that log file was created
    log_files = list(log_dir.glob("prompt_*.json"))
    assert len(log_files) == 1

    # Verify log contents
    with open(log_files[0]) as f:
        log_data = json.load(f)
        assert log_data["prompt"] == test_prompt
        assert log_data["workflow"] == workflow_json
