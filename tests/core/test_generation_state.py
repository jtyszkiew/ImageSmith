import pytest
import discord
from src.core.generation_state import GenerationState

class TestGenerationState:
    @pytest.fixture
    def mock_interaction(self):
        class MockUser:
            def __init__(self):
                self.mention = "@test_user"

        class MockInteraction:
            def __init__(self):
                self.user = MockUser()

        return MockInteraction()

    @pytest.fixture
    def generation_state(self, mock_interaction):
        return GenerationState(
            interaction=mock_interaction,
            workflow_name="test_workflow",
            prompt="test prompt",
            settings="test settings"
        )

    def test_generation_state_init(self, generation_state, mock_interaction):
        assert generation_state.interaction == mock_interaction
        assert generation_state.workflow_name == "test_workflow"
        assert generation_state.prompt == "test prompt"
        assert generation_state.settings == "test settings"
        assert generation_state.current_status == "Starting generation..."
        assert generation_state.image_file is None

    def test_get_embed(self, generation_state):
        embed = generation_state.get_embed()

        assert isinstance(embed, discord.Embed)
        assert embed.title == "🔨 ImageSmith Forge"
        assert len(embed.fields) == 5  # Creator, Workflow, Prompt, Settings, Status fields


        field_names = [field.name for field in embed.fields]
        assert "Creator" in field_names
        assert "Workflow" in field_names
        assert "Prompt" in field_names
        assert "Settings" in field_names
        assert "Status" in field_names
