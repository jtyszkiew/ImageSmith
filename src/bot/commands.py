from typing import Optional

import discord
from discord import app_commands


def forge_command(bot):
    """Create the forge command for txt2img generation"""

    @app_commands.command(
        name="forge",
        description="Forge an image using text-to-image"
    )
    @app_commands.describe(
        prompt="Description of the image you want to create",
        workflow="The workflow to use (optional)",
        settings="Additional settings (optional)"
    )
    async def forge(
            interaction: discord.Interaction,
            prompt: str,
            workflow: Optional[str] = None,
            settings: Optional[str] = None
    ):
        await bot.handle_generation(interaction, 'txt2img', prompt, workflow, settings)

    return forge


def reforge_command(bot):
    """Create the reforge command for img2img generation"""

    @app_commands.command(
        name="reforge",
        description="Reforge an existing image using image-to-image"
    )
    @app_commands.describe(
        image="The image to reforge",
        prompt="Description of the changes you want to make",
        workflow="The workflow to use (optional)",
        settings="Additional settings (optional)"
    )
    async def reforge(
            interaction: discord.Interaction,
            image: discord.Attachment,
            prompt: str,
            workflow: Optional[str] = None,
            settings: Optional[str] = None
    ):
        await bot.handle_generation(interaction, 'img2img', prompt, workflow, settings, image)

    return reforge


def upscale_command(bot):
    """Create the upscale command"""

    @app_commands.command(
        name="upscale",
        description="Upscale an existing image"
    )
    @app_commands.describe(
        image="The image to upscale",
        prompt="Description of the changes you want to make",
        workflow="The workflow to use (optional)",
        settings="Additional settings (optional)"
    )
    async def upscale(
            interaction: discord.Interaction,
            image: discord.Attachment,
            prompt: str,
            workflow: Optional[str] = None,
            settings: Optional[str] = None
    ):
        await bot.handle_generation(interaction, 'upscale', prompt, workflow, settings, image)

    return upscale


def workflows_command(bot):
    """Create the workflows command"""

    @app_commands.command(
        name="workflows",
        description="List available workflows"
    )
    @app_commands.describe(
        type="Type of workflows to list (txt2img, img2img, upscale)"
    )
    async def workflows(
            interaction: discord.Interaction,
            type: Optional[str] = None
    ):
        workflows = bot.workflow_manager.get_selectable_workflows(type)

        embed = discord.Embed(
            title="🔨 Available Forge Workflows",
            color=0x2F3136
        )

        if type:
            embed.description = f"Showing {type} workflows"

        for name, workflow in workflows.items():
            workflow_type = workflow.get('type', 'txt2img')
            description = workflow.get('description', 'No description')
            embed.add_field(
                name=f"{name} ({workflow_type})",
                value=description,
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    return workflows
