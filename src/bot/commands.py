from typing import Optional

import discord
from discord import app_commands

from ..core.i18n import i18n
from ..ui.embeds import (
    no_workflows_embed,
    workflow_detail_embed,
    workflow_list_embed,
    workflow_not_found_embed,
)


def forge_command(bot):
    """Create the forge command for txt2img generation"""

    @app_commands.command(
        name="forge",
        description=i18n.get("command.forge.description")
    )
    @app_commands.describe(
        prompt=i18n.get("command.forge.prompt_desc"),
        workflow=i18n.get("command.forge.workflow_desc"),
        settings=i18n.get("command.forge.settings_desc")
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
        description=i18n.get("command.reforge.description")
    )
    @app_commands.describe(
        image=i18n.get("command.reforge.image_desc"),
        prompt=i18n.get("command.reforge.prompt_desc"),
        workflow=i18n.get("command.reforge.workflow_desc"),
        settings=i18n.get("command.reforge.settings_desc")
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
        description=i18n.get("command.upscale.description")
    )
    @app_commands.describe(
        image=i18n.get("command.upscale.image_desc"),
        prompt=i18n.get("command.upscale.prompt_desc"),
        workflow=i18n.get("command.upscale.workflow_desc"),
        settings=i18n.get("command.upscale.settings_desc")
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
        description=i18n.get("command.workflows.description")
    )
    @app_commands.describe(
        type=i18n.get("command.workflows.type_desc"),
        name=i18n.get("command.workflows.name_desc")
    )
    async def workflows(
            interaction: discord.Interaction,
            type: Optional[str] = None,
            name: Optional[str] = None
    ):
        workflows = bot.workflow_manager.get_selectable_workflows(type)

        if not workflows:
            await interaction.response.send_message(embed=no_workflows_embed())
            return

        if name:
            if name not in workflows:
                await interaction.response.send_message(embed=workflow_not_found_embed(name))
                return

            embed = workflow_detail_embed(name, workflows[name])
        else:
            embed = workflow_list_embed(workflows, type_filter=type)

        await interaction.response.send_message(embed=embed)

    return workflows
