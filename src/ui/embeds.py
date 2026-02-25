from typing import Optional

import discord

from src.core.i18n import i18n

COLOR_DEFAULT = 0x2F3136
COLOR_ERROR = 0xFF0000


def error_embed(description: str) -> discord.Embed:
    return discord.Embed(title=i18n.get("embed.titles.error"), description=description, color=COLOR_ERROR)


def generation_status_embed(
    status: str,
    creator_mention: str,
    workflow_name: str,
    prompt: Optional[str] = None,
    settings: Optional[str] = None,
) -> discord.Embed:
    embed = discord.Embed(title=i18n.get("embed.titles.forge"), color=COLOR_DEFAULT)
    embed.add_field(name=i18n.get("embed.fields.status"), value=status, inline=False)
    embed.add_field(name=i18n.get("embed.fields.creator"), value=creator_mention, inline=True)
    embed.add_field(name=i18n.get("embed.fields.workflow"), value=workflow_name, inline=True)
    if prompt:
        embed.add_field(
            name=i18n.get("embed.fields.prompt"),
            value=prompt[:1021] + "..." if len(prompt) > 1024 else prompt,
            inline=False,
        )
    if settings:
        embed.add_field(name=i18n.get("embed.fields.settings"), value=f"```{settings}```", inline=False)
    return embed


def generation_error_embed(
    error: str,
    creator_mention: str,
    workflow_name: str,
) -> discord.Embed:
    embed = discord.Embed(title=i18n.get("embed.titles.forge"), color=COLOR_ERROR)
    embed.add_field(name=i18n.get("embed.fields.status"), value=i18n.get("embed.messages.error_status", error=error), inline=False)
    embed.add_field(name=i18n.get("embed.fields.creator"), value=creator_mention, inline=True)
    embed.add_field(name=i18n.get("embed.fields.workflow"), value=workflow_name, inline=True)
    return embed


def update_status_field(embed: discord.Embed, new_status: str) -> discord.Embed:
    status_label = i18n.get("embed.fields.status")
    new_embed = embed.copy()
    for i, field in enumerate(new_embed.fields):
        if field.name == status_label:
            new_embed.set_field_at(i, name=status_label, value=new_status, inline=False)
            break
    return new_embed


def no_workflows_embed() -> discord.Embed:
    return discord.Embed(
        title=i18n.get("embed.titles.available_workflows"),
        description=i18n.get("embed.messages.no_workflows"),
        color=COLOR_DEFAULT,
    )


def workflow_not_found_embed(name: str) -> discord.Embed:
    return discord.Embed(
        title=i18n.get("embed.titles.workflow_not_found"),
        description=i18n.get("embed.messages.workflow_not_found_desc", name=name),
        color=COLOR_ERROR,
    )


def workflow_detail_embed(name: str, workflow: dict) -> discord.Embed:
    no_desc = i18n.get("embed.messages.no_description")
    embed = discord.Embed(title=i18n.get("embed.titles.workflow_detail", name=name), color=COLOR_DEFAULT)

    embed.description = (
        f"**Type:** {workflow.get('type', 'txt2img')}\n"
        f"**Description:** {workflow.get('description', no_desc)}"
    )

    if 'form' in workflow:
        form_description = [i18n.get("embed.sections.form_fields")]
        required_indicator = i18n.get("embed.indicators.required")
        optional_indicator = i18n.get("embed.indicators.optional")
        for field in workflow['form']:
            emoji = required_indicator if field.get('required', True) else optional_indicator
            field_info = [
                f"├─ {emoji} `{field['name']}`",
                f"│  ├─ Type: `{field['type']}`",
                f"│  └─ {field.get('description', no_desc)}",
            ]
            form_description.extend(field_info)

        if len(form_description) > 1:
            form_description[-3] = form_description[-3].replace("├─", "└─")
            embed.add_field(
                name="\u200b",
                value="\n".join(form_description),
                inline=False,
            )

    if 'settings' in workflow:
        settings_description = [i18n.get("embed.sections.settings_header")]
        required_indicator = i18n.get("embed.indicators.required")
        optional_indicator = i18n.get("embed.indicators.optional")
        regular_settings = [
            s for s in workflow['settings'] if not s.get('name', '').startswith('__')
        ]

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
                settings_description.append(f"{cont_prefix}└─ {i18n.get('embed.sections.accepts')}")

                for j, arg in enumerate(setting['args']):
                    is_last_arg = j == len(setting['args']) - 1
                    arg_prefix = "   " if is_last_setting else "│  "
                    arg_branch = "└─" if is_last_arg else "├─"

                    required = required_indicator if arg.get('required', True) else optional_indicator
                    arg_info = [
                        f"{arg_prefix}   {arg_branch} {required} `{arg['name']}` ({arg['type']})",
                        f"{arg_prefix}   {'   ' if is_last_arg else '│  '}└─ {arg.get('description', no_desc)}",
                    ]
                    settings_description.extend(arg_info)

        if len(settings_description) > 1:
            embed.add_field(
                name="\u200b",
                value="\n".join(settings_description),
                inline=False,
            )

    embed.set_footer(text=i18n.get("embed.indicators.footer_legend"))
    return embed


def workflow_list_embed(
    workflows: dict,
    type_filter: Optional[str] = None,
) -> discord.Embed:
    no_desc = i18n.get("embed.messages.no_description")
    embed = discord.Embed(title=i18n.get("embed.titles.available_workflows"), color=COLOR_DEFAULT)

    if type_filter:
        embed.description = i18n.get("embed.messages.workflow_type_filter", type_filter=type_filter) + "\n\n"

    workflow_types = {}
    for workflow_name, workflow_data in workflows.items():
        wf_type = workflow_data.get('type', 'txt2img')
        if wf_type not in workflow_types:
            workflow_types[wf_type] = []
        workflow_types[wf_type].append((workflow_name, workflow_data))

    for wf_type, wf_list in workflow_types.items():
        type_emoji = i18n.get(f"embed.workflow_types.{wf_type}")
        # If key wasn't found (returns the key path), use default
        if type_emoji == f"embed.workflow_types.{wf_type}":
            type_emoji = i18n.get("embed.workflow_types.default")

        workflows_text = []
        for i, (wf_name, wf_data) in enumerate(sorted(wf_list)):
            is_last = i == len(wf_list) - 1
            prefix = "└─" if is_last else "├─"
            description = wf_data.get('description', no_desc)
            workflows_text.append(
                f"{prefix} **{wf_name}**\n{'   ' if is_last else '│  '}└─ {description}"
            )

        embed.add_field(
            name=i18n.get("embed.workflow_type_header", emoji=type_emoji, type=wf_type.upper()),
            value="\n".join(workflows_text),
            inline=False,
        )

    embed.set_footer(text=i18n.get("embed.messages.workflow_list_footer"))
    return embed
