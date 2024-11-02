import discord


class GenerationState:
    """Manages state for a single image generation"""

    def __init__(self, interaction: discord.Interaction, workflow_name: str, prompt: str, settings: str):
        self.interaction = interaction
        self.workflow_name = workflow_name
        self.prompt = prompt
        self.settings = settings
        self.message = None
        self.current_status = "Starting generation..."
        self.image_file = None

    def get_embed(self) -> discord.Embed:
        """Create embed for the current state"""
        embed = discord.Embed(title="🔨 ImageSmith Forge", color=0x2F3136)
        embed.add_field(name="Creator", value=self.interaction.user.mention, inline=True)
        embed.add_field(name="Workflow", value=self.workflow_name, inline=True)
        if self.prompt:
            embed.add_field(name="Prompt", value=self.prompt, inline=False)
        if self.settings:
            embed.add_field(name="Settings", value=f"```{self.settings}```", inline=False)
        embed.add_field(name="Status", value=self.current_status, inline=False)
        return embed
