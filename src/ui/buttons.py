import discord


class ImageButton(discord.ui.Button):
    """Custom button for image interactions"""

    def __init__(self, label: str, custom_id: str, emoji: str):
        super().__init__(
            label=label,
            custom_id=custom_id,
            style=discord.ButtonStyle.secondary,
            emoji=emoji
        )
