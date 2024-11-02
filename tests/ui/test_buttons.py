import pytest
import discord
from src.ui.buttons import ImageButton

class TestImageButton:
    @pytest.fixture
    def button(self):
        return ImageButton("Test", "test_id", "🔄")

    def test_button_init(self, button):
        emoji = discord.PartialEmoji(animated=False, name='🔄', id=None)

        assert button.label == "Test"
        assert button.custom_id == "test_id"
        assert button.emoji == emoji
        assert button.style == discord.ButtonStyle.secondary
