import discord

from .buttons import ImageButton


class ImageView(discord.ui.View):
    """Custom view for image interaction buttons"""

    def __init__(self, prompt_id: str, has_upscaler: bool = False):
        super().__init__(timeout=None)

        if has_upscaler:
            self.add_item(ImageButton("Upscale", f"upscale_{prompt_id}", "✨"))

        self.add_item(ImageButton("Regenerate", f"regenerate_{prompt_id}", "🔄"))
        self.add_item(ImageButton("Use as Input", f"img2img_{prompt_id}", "🖼"))
