import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from datetime import datetime
from typing import Dict

from src.core.form import (
    FormField,
    FormDefinition,
    FormFieldHandler,
    TextFieldHandler,
    ResolutionFieldHandler,
    SelectFieldHandler,
    FormModal,
    FormButton,
    FormView,
    DynamicFormManager
)

@pytest.fixture
def sample_workflow_config():
    return {
        'form': [
            {
                'name': 'seed',
                'type': 'number',
                'required': False,
                'description': 'Seed for the model',
                'message': 'Provide a seed you would like to use',
                'on_submit': '''
def on_submit(workflowjson, value):
    workflowjson["65"]["inputs"]["seed"] = value
''',
                'on_default': '''
def on_default(workflowjson):
    import random
    seed_value = random.randint(0, 2**32 - 1)
    workflowjson["65"]["inputs"]["seed"] = seed_value
'''
            },
            {
                'name': 'resolution',
                'type': 'resolution',
                'required': True,
                'description': 'Resolution for the image',
                'message': 'Provide the resolution',
                'on_submit': '''
def on_submit(workflowjson, width, height):
    workflowjson["5"]["inputs"]["width"] = width
    workflowjson["5"]["inputs"]["height"] = height
'''
            }
        ]
    }

@pytest.fixture
def sample_workflow_json():
    return {
        "5": {"inputs": {"width": 512, "height": 512}},
        "65": {"inputs": {"seed": 1234}}
    }

@pytest.fixture
def mock_interaction():
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 12345
    interaction.response = AsyncMock()
    interaction.client = MagicMock()
    interaction.client.wait_for = AsyncMock()

    # Add form_data dict
    interaction.client.form_data = {}

    return interaction

@pytest.fixture
def mock_message():
    message = MagicMock(spec=discord.Message)
    message.edit = AsyncMock()

    # Create a status field that will persist
    class MockField:
        def __init__(self, name, value, inline=False):
            self.name = name
            self.value = value
            self.inline = inline

    status_field = MockField("Status", "Initial Status", False)

    # Create a proper mock for the embed
    class MockEmbed:
        def __init__(self, fields):
            self.fields = fields

        def set_field_at(self, index, *, name, value, inline=False):
            self.fields[index] = MockField(name, value, inline)
            return self

        def copy(self):
            return MockEmbed([
                MockField(f.name, f.value, f.inline)
                for f in self.fields
            ])

    embed = MockEmbed([status_field])
    message.embeds = [embed]
    return message

class TestFormField:
    def test_from_dict(self):
        field_data = {
            'name': 'test',
            'type': 'number',
            'description': 'Test field',
            'message': 'Enter value',
            'on_submit': 'def on_submit(): pass',
            'required': False
        }

        field = FormField.from_dict(field_data)

        assert field.name == 'test'
        assert field.type == 'number'
        assert field.description == 'Test field'
        assert field.message == 'Enter value'
        assert field.on_submit == 'def on_submit(): pass'
        assert field.required is False

class TestFormDefinition:
    def test_from_yaml(self, sample_workflow_config):
        form_def = FormDefinition.from_yaml(sample_workflow_config)

        assert len(form_def.fields) == 2
        assert form_def.fields[0].name == 'seed'
        assert form_def.fields[1].name == 'resolution'
        assert form_def.fields[0].required is False
        assert form_def.fields[1].required is True

class TestNumberFieldHandler:
    @pytest.mark.asyncio
    async def test_process_value_valid(self):
        handler = TextFieldHandler()
        result = await handler.process_value(MagicMock(), "123")
        assert result == 123

    @pytest.mark.asyncio
    async def test_process_value_invalid(self):
        handler = TextFieldHandler()
        with pytest.raises(ValueError):
            await handler.process_value(MagicMock(), "invalid")

class TestResolutionFieldHandler:
    @pytest.mark.asyncio
    async def test_process_value_valid(self):
        handler = ResolutionFieldHandler()
        result = await handler.process_value(MagicMock(), ["512x512", "1024x1024"])
        assert result == ['512', '512']

    @pytest.mark.asyncio
    async def test_process_value_invalid(self):
        handler = ResolutionFieldHandler()
        with pytest.raises(ValueError):
            await handler.process_value(MagicMock(), "invalid")

class TestDynamicFormManager:
    @pytest.fixture
    def form_manager(self):
        return DynamicFormManager()

    def test_register_field_handler(self, form_manager):
        class CustomHandler(FormFieldHandler):
            def create_component(self, field): pass
            async def process_value(self, interaction, value): pass
            def requires_modal(self): return True

        handler = CustomHandler()
        form_manager.register_field_handler('custom', handler)
        assert form_manager.field_handlers['custom'] == handler

    @pytest.mark.asyncio
    async def test_apply_form_data_with_submit(self, form_manager, sample_workflow_json):
        form_data = {
            'field_definitions': [
                FormField.from_dict({
                    'name': 'seed',
                    'type': 'number',
                    'description': 'Test',
                    'message': 'Test',
                    'on_submit': '''
def on_submit(workflowjson, value):
    workflowjson["65"]["inputs"]["seed"] = value
'''
                })
            ],
            'seed': 42
        }

        result = form_manager.apply_form_data_to_workflow(form_data, sample_workflow_json)
        assert result["65"]["inputs"]["seed"] == 42

    @pytest.mark.asyncio
    async def test_apply_form_data_with_default(self, form_manager, sample_workflow_json):
        form_data = {
            'field_definitions': [
                FormField.from_dict({
                    'name': 'seed',
                    'type': 'number',
                    'required': False,
                    'description': 'Test',
                    'message': 'Test',
                    'on_default': '''
def on_default(workflowjson):
    workflowjson["65"]["inputs"]["seed"] = 999
'''
                })
            ]
        }

        result = form_manager.apply_form_data_to_workflow(form_data, sample_workflow_json)
        assert result["65"]["inputs"]["seed"] == 999

    @pytest.mark.asyncio
    async def test_process_workflow_form_timeout(
            self, form_manager, mock_interaction, mock_message, sample_workflow_config, sample_workflow_json
    ):
        # Simulate timeout by making wait_for raise TimeoutError
        mock_interaction.client.wait_for.side_effect = TimeoutError()

        result = await form_manager.process_workflow_form(
            mock_interaction,
            sample_workflow_config,
            sample_workflow_json,
            mock_message
        )

        assert result is None
        assert mock_message.edit.called

        # Get the embed from the last edit call
        last_call_kwargs = mock_message.edit.call_args[1]
        embed = last_call_kwargs['embed']

        # Print debug information
        print("\nFields in embed:")
        for field in embed.fields:
            print(f"Name: {field.name}, Value: {field.value}")

        # Check the status field directly
        status_field = next((field for field in embed.fields if field.name == "Status"), None)
        assert status_field is not None, "Status field not found in embed"
        assert "❌ Form timed out" in str(status_field.value), \
            f"Expected timeout message in status field, got: {status_field.value}"

    @pytest.mark.asyncio
    async def test_full_form_submission_flow(
            self, form_manager, mock_interaction, mock_message, sample_workflow_config, sample_workflow_json
    ):
        submission_count = 0

        async def simulate_interactions(*args, **kwargs):
            nonlocal submission_count
            mock_int = AsyncMock(spec=discord.Interaction)
            mock_int.user = mock_interaction.user
            mock_int.response = AsyncMock()
            mock_int.client = mock_interaction.client

            if submission_count == 0:
                # First interaction: Modal opening
                mock_int.data = {
                    'custom_id': 'form_button_resolution'
                }
            elif submission_count == 1:
                # Second interaction: Modal submission
                mock_int.data = {
                    'custom_id': 'form_field_resolution',
                    'components': [{'components': [{'value': '1024x1024'}]}]
                }
                # Store the form data
                if not hasattr(mock_int.client, 'form_data'):
                    mock_int.client.form_data = {}
                mock_int.client.form_data['field_definitions'] = sample_workflow_config['form']
                mock_int.client.form_data['resolution'] = (1024, 1024)
            elif submission_count == 2:
                # Third interaction: Form submission
                mock_int.data = {
                    'custom_id': 'form_submit'
                }
                # Set submitted flag
                for item in mock_message.edit.call_args[1]['view'].children:
                    if hasattr(item, 'form_view'):
                        item.form_view.submitted = True
                        break

            submission_count += 1
            return mock_int

        mock_interaction.client.wait_for.side_effect = simulate_interactions

        # Process the form
        result = await form_manager.process_workflow_form(
            mock_interaction,
            sample_workflow_config,
            sample_workflow_json,
            mock_message
        )

        # Verify the workflow was modified correctly
        assert result is not None
        assert result["5"]["inputs"]["width"] == 1024, f"Expected width 1024, got {result['5']['inputs']['width']}"
        assert result["5"]["inputs"]["height"] == 1024, f"Expected height 1024, got {result['5']['inputs']['height']}"
        assert "seed" in result["65"]["inputs"]  # Should have a default seed value
