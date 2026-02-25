import discord

from ..core.i18n import i18n
from .buttons import ImageButton


class ImageView(discord.ui.View):
    """Custom view for image interaction buttons"""

    def __init__(self, prompt_id: str, has_upscaler: bool = False):
        super().__init__(timeout=None)

        if has_upscaler:
            self.add_item(ImageButton(i18n.get("button.upscale"), f"upscale_{prompt_id}", "✨"))

        self.add_item(ImageButton(i18n.get("button.regenerate"), f"regenerate_{prompt_id}", "🔄"))
        self.add_item(ImageButton(i18n.get("button.use_as_input"), f"img2img_{prompt_id}", "🖼"))
