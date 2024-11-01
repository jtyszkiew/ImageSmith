import asyncio
from unittest.mock import AsyncMock

import pytest

from imagesmith import ComfyUIBot


@pytest.mark.asyncio
async def test_bot_initialization(config_file):
    """Test bot initialization"""
    bot = ComfyUIBot()
    assert bot.workflow_manager is not None
    assert bot.hook_manager is not None
    assert bot.generation_queue is not None


@pytest.mark.asyncio
async def test_forge_command(
        mock_discord_interaction,
        mock_comfyui_client,
        config_file
):
    """Test forge command"""
    bot = ComfyUIBot()
    bot.comfy_client = mock_comfyui_client

    # Execute command
    command = bot.forge_command()
    forge_callback = command._callback

    print("\n=== Starting forge command test ===")

    await forge_callback(
        interaction=mock_discord_interaction,
        prompt="test prompt",
        workflow="test_workflow"
    )

    # Verify initial response
    assert mock_discord_interaction.response.send_message.called, "send_message was not called"

    call_args = mock_discord_interaction.response.send_message.call_args
    print("\nSend message call args:", call_args)

    kwargs = call_args[1]
    print("\nSend message kwargs:", kwargs)

    embed = kwargs.get('embed')
    assert embed is not None, "No embed found in send_message kwargs"

    print("\nEmbed object:", embed)
    print("Embed fields:", embed.fields)
    print("\nField details:")
    for i, field in enumerate(embed.fields):
        print(f"Field {i}:")
        print(f"  Name: '{field.name}'")
        print(f"  Value: '{field.value}'")
        print(f"  Inline: {field.inline}")

    # Verify initial embed contents
    found_status = False
    found_creator = False
    found_prompt = False

    for field in embed.fields:
        if field.name == "Status":
            found_status = True
        elif field.name == "Creator":
            found_creator = True
        elif field.name == "Prompt" and field.value == "test prompt":
            found_prompt = True

    assert found_status, "Status field missing"
    assert found_creator, "Creator field missing"
    assert found_prompt, "Prompt field incorrect"

    print("\n=== Test completed ===")

@pytest.mark.asyncio
async def test_forge_command_with_queue(
        mock_discord_interaction,
        mock_comfyui_client,
        config_file
):
    """Test forge command with queue"""
    print("\n=== Starting forge command with queue test ===")

    bot = ComfyUIBot()
    bot.comfy_client = mock_comfyui_client

    # Add a dummy task to queue and verify it's added
    async def dummy_task():
        await asyncio.sleep(0.1)
    await bot.generation_queue.add_to_queue(dummy_task)

    queue_size = bot.generation_queue.get_queue_position()
    print(f"\nQueue size before test: {queue_size}")
    assert queue_size > 0, "Queue is empty when it should contain our dummy task"

    # Execute command
    command = bot.forge_command()
    forge_callback = command._callback

    await forge_callback(
        interaction=mock_discord_interaction,
        prompt="test prompt",
        workflow="test_workflow"
    )

    # Verify response
    assert mock_discord_interaction.response.send_message.called, "send_message was not called"

    call_args = mock_discord_interaction.response.send_message.call_args
    print("\nSend message call args:", call_args)

    kwargs = call_args[1]
    embed = kwargs.get('embed')
    assert embed is not None, "No embed found in send_message kwargs"

    print("\nEmbed fields:")
    for i, field in enumerate(embed.fields):
        print(f"Field {i}:")
        print(f"  Name: '{field.name}'")
        print(f"  Value: '{field.value}'")

    # Look for status field with queue information
    status_field = None
    for field in embed.fields:
        print(f"Checking field: {field.name} = {field.value}")
        if field.name == "Status":
            status_field = field
            break

    assert status_field is not None, "Status field missing"
    assert "queue" in status_field.value.lower(), f"Queue not mentioned in status: {status_field.value}"

    print("\n=== Test completed ===")

@pytest.mark.asyncio
async def test_forge_command_with_error(
        mock_discord_interaction,
        mock_comfyui_client,
        config_file
):
    """Test forge command with error"""
    print("\n=== Starting forge command with error test ===")

    bot = ComfyUIBot()

    # Setup error
    error_message = "Test error"
    mock_comfyui_client.generate = AsyncMock(side_effect=Exception(error_message))
    bot.comfy_client = mock_comfyui_client

    # Execute command
    command = bot.forge_command()
    forge_callback = command._callback

    await forge_callback(
        interaction=mock_discord_interaction,
        prompt="test prompt",
        workflow="test_workflow"
    )

    # Verify error handling
    message = await mock_discord_interaction.original_response()
    assert message.edit.called, "Message edit was not called"

    print("\nMessage edit calls:", message.edit.mock_calls)

    # Get last edit call
    call_args = message.edit.call_args
    assert call_args is not None, "No edit call args found"

    kwargs = call_args[1]
    error_embed = kwargs.get('embed')
    assert error_embed is not None, "No embed found in edit kwargs"

    print("\nError embed fields:")
    for i, field in enumerate(error_embed.fields):
        print(f"Field {i}:")
        print(f"  Name: '{field.name}'")
        print(f"  Value: '{field.value}'")

    # Verify error message
    error_found = False
    for field in error_embed.fields:
        if "error" in field.value.lower() and error_message in field.value:
            error_found = True
            break

    assert error_found, f"Error message '{error_message}' not found in embed fields"

    print("\n=== Test completed ===")

@pytest.mark.asyncio
async def test_generation_queue():
    """Test generation queue"""
    bot = ComfyUIBot()

    # Create mock generation function
    mock_func = AsyncMock()

    # Add to queue
    await bot.generation_queue.add_to_queue(mock_func)

    # Check queue size
    assert bot.generation_queue.get_queue_position() == 1

    # Wait for processing
    await asyncio.sleep(0.1)

    # Check function was called
    assert mock_func.called


@pytest.mark.asyncio
async def test_process_generation(
        mock_discord_message,
        mock_comfyui_client,
        config_file
):
    """Test generation processing"""
    bot = ComfyUIBot()
    bot.comfy_client = mock_comfyui_client

    workflow_json = {
        "27": {
            "inputs": {
                "text": "test prompt"
            }
        }
    }

    # Setup mock response
    mock_comfyui_client.generate.return_value = {"prompt_id": "test_id"}
    mock_comfyui_client.listen_for_updates.return_value = None

    await bot.process_generation(
        workflow_json,
        "test prompt",
        mock_discord_message
    )

    # Check ComfyUI client calls
    assert mock_comfyui_client.generate.called
    mock_comfyui_client.generate.assert_called_with(workflow_json)
    assert mock_comfyui_client.listen_for_updates.called
