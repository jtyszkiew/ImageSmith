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
        type="Type of workflows to list (txt2img, img2img, upscale)",
        name="Name of the workflow to show details for"
    )
    async def workflows(
            interaction: discord.Interaction,
            type: Optional[str] = None,
            name: Optional[str] = None
    ):
        workflows = bot.workflow_manager.get_selectable_workflows(type)

        if not workflows:
            embed = discord.Embed(
                title="🔨 Available Forge Workflows",
                description="No workflows available",
                color=0x2F3136
            )
            await interaction.response.send_message(embed=embed)
            return

        # If a specific workflow is requested
        if name:
            if name not in workflows:
                embed = discord.Embed(
                    title="❌ Workflow Not Found",
                    description=f"No workflow found with name: `{name}`",
                    color=0xFF0000
                )
                await interaction.response.send_message(embed=embed)
                return

            workflow = workflows[name]
            embed = discord.Embed(
                title=f"🔨 Workflow: {name}",
                color=0x2F3136
            )

            # Add type and description in the main description
            embed.description = (
                f"**Type:** {workflow.get('type', 'txt2img')}\n"
                f"**Description:** {workflow.get('description', 'No description')}"
            )

            # Form fields
            if 'form' in workflow:
                form_description = ["📝 **Form Fields**"]
                for field in workflow['form']:
                    emoji = "🔴" if field.get('required', True) else "⚪"
                    field_info = [
                        f"├─ {emoji} `{field['name']}`",
                        f"│  ├─ Type: `{field['type']}`",
                        f"│  └─ {field.get('description', 'No description')}"
                    ]
                    form_description.extend(field_info)

                if len(form_description) > 1:  # If we have any fields
                    form_description[-3] = form_description[-3].replace("├─", "└─")  # Fix last item
                    embed.add_field(
                        name="\u200b",  # Zero-width space for clean separation
                        value="\n".join(form_description),
                        inline=False
                    )

            # Settings (excluding __before and __after)
            if 'settings' in workflow:
                settings_description = ["⚙️ **Settings**"]
                regular_settings = [s for s in workflow['settings'] if not s.get('name', '').startswith('__')]

                for i, setting in enumerate(regular_settings):
                    is_last_setting = i == len(regular_settings) - 1
                    prefix = "└─" if is_last_setting else "├─"

                    setting_name = setting.get('name', '')
                    settings_description.append(f"{prefix} `{setting_name}`")

                    if 'description' in setting:
                        cont_prefix = "   " if is_last_setting else "│  "
                        settings_description.append(f"{cont_prefix}└─ {setting['description']}")

                    if 'args' in setting:
                        cont_prefix = "   " if is_last_setting else "│  "
                        settings_description.append(f"{cont_prefix}└─ **Accepts:**")

                        for j, arg in enumerate(setting['args']):
                            is_last_arg = j == len(setting['args']) - 1
                            arg_prefix = "   " if is_last_setting else "│  "
                            arg_branch = "└─" if is_last_arg else "├─"

                            required = "🔴" if arg.get('required', True) else "⚪"
                            arg_info = [
                                f"{arg_prefix}   {arg_branch} {required} `{arg['name']}` ({arg['type']})",
                                f"{arg_prefix}   {'   ' if is_last_arg else '│  '}└─ {arg.get('description', 'No description')}"
                            ]
                            settings_description.extend(arg_info)

                if len(settings_description) > 1:  # If we have any settings
                    embed.add_field(
                        name="\u200b",  # Zero-width space for clean separation
                        value="\n".join(settings_description),
                        inline=False
                    )

            embed.set_footer(text="🔴 Required | ⚪ Optional")

        # List all workflows
        else:
            embed = discord.Embed(
                title="🔨 Available Forge Workflows",
                color=0x2F3136
            )

            if type:
                embed.description = f"Showing {type} workflows\n\n"

            # Group workflows by type
            workflow_types = {}
            for workflow_name, workflow_data in workflows.items():
                wf_type = workflow_data.get('type', 'txt2img')
                if wf_type not in workflow_types:
                    workflow_types[wf_type] = []
                workflow_types[wf_type].append((workflow_name, workflow_data))

            # Add fields for each type
            for wf_type, wf_list in workflow_types.items():
                type_emojis = {
                    'txt2img': '✍️',
                    'img2img': '🖼️',
                    'upscale': '🔍'
                }
                type_emoji = type_emojis.get(wf_type, '⚡')

                workflows_text = []
                for i, (wf_name, wf_data) in enumerate(sorted(wf_list)):
                    is_last = i == len(wf_list) - 1
                    prefix = "└─" if is_last else "├─"
                    description = wf_data.get('description', 'No description')
                    workflows_text.append(f"{prefix} **{wf_name}**\n{'   ' if is_last else '│  '}└─ {description}")

                embed.add_field(
                    name=f"{type_emoji} {wf_type.upper()} Workflows",
                    value="\n".join(workflows_text),
                    inline=False
                )

            embed.set_footer(text="Use /workflows name:<workflow> for detailed information")

        await interaction.response.send_message(embed=embed)

    return workflows
