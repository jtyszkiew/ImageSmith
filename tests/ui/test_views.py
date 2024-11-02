import asyncio

import discord
import pytest
from src.ui.views import ImageView

class TestImageView:
    @pytest.fixture
    def event_loop(self):
        """Create and set an event loop for each test case."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
        loop.close()

    @pytest.mark.asyncio
    async def test_view_init_with_upscaler(self, event_loop):
        view = ImageView("test_prompt_id", has_upscaler=True)
        assert len(view.children) == 3  # Upscale, Regenerate, Use as Input

        button_labels = [child.label for child in view.children]
        assert "Upscale" in button_labels
        assert "Regenerate" in button_labels
        assert "Use as Input" in button_labels

    @pytest.mark.asyncio
    async def test_view_init_without_upscaler(self, event_loop):
        view = ImageView("test_prompt_id", has_upscaler=False)
        assert len(view.children) == 2  # Regenerate, Use as Input

        button_labels = [child.label for child in view.children]
        assert "Upscale" not in button_labels
        assert "Regenerate" in button_labels
        assert "Use as Input" in button_labels

    @pytest.mark.asyncio
    async def test_button_custom_ids(self, event_loop):
        prompt_id = "test_prompt_id"
        view = ImageView(prompt_id, has_upscaler=True)

        expected_ids = {
            f"upscale_{prompt_id}",
            f"regenerate_{prompt_id}",
            f"img2img_{prompt_id}"
        }

        actual_ids = {child.custom_id for child in view.children}
        assert actual_ids == expected_ids

    @pytest.mark.asyncio
    async def test_button_emojis(self, event_loop):
        view = ImageView("test_prompt_id", has_upscaler=True)

        expected_emojis = {
            discord.PartialEmoji(animated=False, name='✨', id=None),
            discord.PartialEmoji(animated=False, name='🔄', id=None),
            discord.PartialEmoji(animated=False, name='🖼', id=None),
        }

        actual_emojis = {child.emoji for child in view.children}
        assert actual_emojis == expected_emojis
