import pytest
from unittest.mock import MagicMock, AsyncMock
import discord
import yaml
import json
import asyncio


class AsyncContextManagerMock:
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockField:
    """Mock for discord.Embed field"""
    def __init__(self, name: str, value: str, inline: bool = False):
        self.name = name
        self.value = value
        self.inline = inline

class MockEmbed:
    """Mock for discord.Embed"""
    def __init__(self, **kwargs):
        print(f"Creating MockEmbed with kwargs: {kwargs}")  # Debug print
        self.title = kwargs.get('title')
        self.description = kwargs.get('description')
        self.color = kwargs.get('color')
        self.fields = []
        self._field_dict = {}

    def add_field(self, *, name: str, value: str, inline: bool = False):
        """Add a field to the embed"""
        print(f"Adding field: name='{name}', value='{value}'")  # Debug print
        field = MockField(name=name, value=value, inline=inline)
        self.fields.append(field)
        self._field_dict[name] = field
        return self

    def set_field_at(self, index: int, *, name: str, value: str, inline: bool = False):
        """Set a field at a specific index"""
        if 0 <= index < len(self.fields):
            self.fields[index] = MockField(name=name, value=value, inline=inline)
            self._field_dict[name] = self.fields[index]
        return self

    def copy(self):
        """Create a copy of this embed"""
        new_embed = MockEmbed(
            title=self.title,
            description=self.description,
            color=self.color
        )
        for field in self.fields:
            new_embed.add_field(
                name=field.name,
                value=field.value,
                inline=field.inline
            )
        return new_embed

    def to_dict(self):
        """Convert embed to dictionary for debugging"""
        return {
            'title': self.title,
            'description': self.description,
            'color': self.color,
            'fields': [
                {
                    'name': f.name,
                    'value': f.value,
                    'inline': f.inline
                }
                for f in self.fields
            ]
        }

class MockMessage:
    """Mock for discord.Message"""
    def __init__(self):
        self.embeds = []
        self.last_embed = None
        self.fields = []  # Store fields separately for easier testing
        self.edit = AsyncMock()

        async def edit_mock(*args, **kwargs):
            print(f"Message edit called with kwargs: {kwargs}")  # Debug print
            if 'embed' in kwargs:
                embed = kwargs['embed']
                self.last_embed = embed
                self.embeds = [embed]
                # Store fields for testing
                self.fields = embed.fields
                print("Fields after edit:")
                for field in self.fields:
                    print(f"  {field.name}: {field.value}")
            return self

        self.edit.side_effect = edit_mock

@pytest.fixture
def mock_discord_interaction():
    """Mock Discord interaction"""
    interaction = AsyncMock(spec=discord.Interaction)

    # Create message
    message = MockMessage()

    # Create response
    response = AsyncMock()

    async def send_message_mock(*args, **kwargs):
        print(f"Send message called with kwargs: {kwargs}")  # Debug print
        if 'embed' in kwargs:
            # Important: Store the embed exactly as it is
            embed = kwargs['embed']
            message.last_embed = embed
            message.embeds = [embed]
            # Print embed fields for debugging
            print("Embed fields after send_message:")
            for field in embed.fields:
                print(f"  {field.name}: {field.value}")
            # Store the fields in the message for later verification
            message.fields = embed.fields
        return message

    response.send_message = AsyncMock(side_effect=send_message_mock)
    interaction.response = response

    # Mock original_response to return our message with the stored embed
    async def original_response_mock():
        return message

    interaction.original_response = AsyncMock(side_effect=original_response_mock)

    # Mock user
    user = MagicMock()
    user.mention = "<@123456789>"
    interaction.user = user

    return interaction

@pytest.fixture
def mock_comfyui_client():
    """Mock ComfyUI client"""
    client = AsyncMock()
    client.generate = AsyncMock(return_value={"prompt_id": "test_prompt_id"})

    async def mock_listen(prompt_id, callback):
        await callback("Starting generation...")
        await callback("Processing...", None)
        await callback("Generation complete!", None)

    client.listen_for_updates = AsyncMock(side_effect=mock_listen)
    client.process_generation = AsyncMock()

    return client

@pytest.fixture(autouse=True)
def mock_discord_embed(monkeypatch):
    """Replace discord.Embed with MockEmbed"""
    def embed_factory(*args, **kwargs):
        return MockEmbed(*args, **kwargs)
    monkeypatch.setattr('discord.Embed', embed_factory)
    return MockEmbed


@pytest.fixture
def mock_workflow_manager(config_file):
    """Mock WorkflowManager"""
    manager = MagicMock()
    manager.default_workflow = "test_workflow"
    manager.get_workflow.return_value = {
        'description': 'Test Workflow',
        'workflow': './test_workflow.json',
        'text_prompt_node_id': 27,
        'selectable': True
    }
    return manager


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory with all necessary files"""
    # Create directories
    config_dir = tmp_path / "config"
    workflows_dir = config_dir / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create test workflow file
    workflow_file = workflows_dir / "test_workflow.json"
    workflow_data = {
        "27": {
            "inputs": {
                "text": "default prompt",
                "steps": 20
            }
        }
    }
    with open(workflow_file, "w") as f:
        json.dump(workflow_data, f)

    # Create config file
    config_file = config_dir / "configuration.yml"
    config_data = {
        'discord': {
            'token': 'test_token'
        },
        'comfyui': {
            'url': 'http://localhost:8188'
        },
        'default_workflow': 'test_workflow',
        'workflows': {
            'test_workflow': {
                'description': 'Test Workflow',
                'workflow': str(workflow_file),
                'text_prompt_node_id': 27,
                'selectable': True,
                'settings': [
                    {
                        'name': '__before',
                        'description': 'Default settings',
                        'code': 'def __before(workflowjson):\n    workflowjson["27"]["inputs"]["steps"] = 20'
                    },
                    {
                        'name': 'change_steps',
                        'description': 'Change steps',
                        'code': 'def change_steps(workflowjson, value):\n    workflowjson["27"]["inputs"]["steps"] = int(value)'
                    }
                ]
            }
        }
    }
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    return config_dir


@pytest.fixture
def config_file(config_dir):
    """Return path to config file"""
    return config_dir / "configuration.yml"


@pytest.fixture
def mock_discord_message():
    """Mock Discord message"""
    message = AsyncMock(spec=discord.Message)
    message.edit = AsyncMock()

    # Create mock embed
    embed = AsyncMock(spec=discord.Embed)
    embed.fields = []
    status_field = MagicMock()
    status_field.name = "Status"
    status_field.value = "test status"
    status_field.copy = MagicMock(return_value=status_field)
    embed.fields.append(status_field)

    message.embeds[0] = embed
    return message


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
