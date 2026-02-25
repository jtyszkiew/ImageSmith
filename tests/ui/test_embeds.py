import discord
import pytest

from src.core.i18n import i18n
from src.ui.embeds import (
    COLOR_DEFAULT,
    COLOR_ERROR,
    error_embed,
    generation_error_embed,
    generation_status_embed,
    no_workflows_embed,
    update_status_field,
    workflow_detail_embed,
    workflow_list_embed,
    workflow_not_found_embed,
)


class TestErrorEmbed:
    def test_basic(self):
        embed = error_embed("Something went wrong")
        assert embed.title == i18n.get("embed.titles.error")
        assert embed.description == "Something went wrong"
        assert embed.color.value == COLOR_ERROR

    def test_empty_description(self):
        embed = error_embed("")
        assert embed.description == ""


class TestGenerationStatusEmbed:
    def test_minimal(self):
        embed = generation_status_embed("Starting...", "@user", "workflow1")
        assert embed.title == i18n.get("embed.titles.forge")
        assert embed.color.value == COLOR_DEFAULT
        assert len(embed.fields) == 3
        assert embed.fields[0].name == i18n.get("embed.fields.status")
        assert embed.fields[0].value == "Starting..."
        assert embed.fields[1].name == i18n.get("embed.fields.creator")
        assert embed.fields[1].value == "@user"
        assert embed.fields[2].name == i18n.get("embed.fields.workflow")
        assert embed.fields[2].value == "workflow1"

    def test_with_prompt_and_settings(self):
        embed = generation_status_embed(
            "Queued", "@user", "wf", prompt="a cat", settings="steps=20"
        )
        assert len(embed.fields) == 5
        assert embed.fields[3].name == i18n.get("embed.fields.prompt")
        assert embed.fields[3].value == "a cat"
        assert embed.fields[4].name == i18n.get("embed.fields.settings")
        assert "steps=20" in embed.fields[4].value

    def test_long_prompt_is_truncated(self):
        long_prompt = "x" * 2000
        embed = generation_status_embed("s", "@u", "w", prompt=long_prompt)
        assert embed.fields[3].value.endswith("...")
        assert len(embed.fields[3].value) == 1024


class TestGenerationErrorEmbed:
    def test_basic(self):
        embed = generation_error_embed("timeout", "@user", "wf")
        assert embed.color.value == COLOR_ERROR
        assert embed.fields[0].value == i18n.get("embed.messages.error_status", error="timeout")
        assert embed.fields[1].value == "@user"
        assert embed.fields[2].value == "wf"


class TestUpdateStatusField:
    def test_updates_status(self):
        original = generation_status_embed("old", "@u", "w")
        updated = update_status_field(original, "new status")
        assert updated.fields[0].value == "new status"

    def test_no_status_field(self):
        embed = discord.Embed(title="test")
        embed.add_field(name="Other", value="val")
        result = update_status_field(embed, "x")
        assert result.fields[0].value == "val"


class TestNoWorkflowsEmbed:
    def test_basic(self):
        embed = no_workflows_embed()
        assert embed.title == i18n.get("embed.titles.available_workflows")
        assert embed.description == i18n.get("embed.messages.no_workflows")
        assert embed.color.value == COLOR_DEFAULT


class TestWorkflowNotFoundEmbed:
    def test_basic(self):
        embed = workflow_not_found_embed("missing_wf")
        assert embed.title == i18n.get("embed.titles.workflow_not_found")
        assert "`missing_wf`" in embed.description
        assert embed.color.value == COLOR_ERROR


class TestWorkflowDetailEmbed:
    def test_minimal(self):
        wf = {"type": "txt2img", "description": "A test workflow"}
        embed = workflow_detail_embed("my_wf", wf)
        assert embed.title == i18n.get("embed.titles.workflow_detail", name="my_wf")
        assert "txt2img" in embed.description
        assert "A test workflow" in embed.description
        assert embed.footer.text == i18n.get("embed.indicators.footer_legend")

    def test_with_form(self):
        wf = {
            "type": "txt2img",
            "description": "desc",
            "form": [
                {"name": "field1", "type": "string", "required": True, "description": "First field"},
            ],
        }
        embed = workflow_detail_embed("wf", wf)
        field_values = [f.value for f in embed.fields]
        assert any("field1" in v for v in field_values)

    def test_with_settings(self):
        wf = {
            "type": "txt2img",
            "description": "desc",
            "settings": [
                {"name": "steps", "description": "Number of steps"},
                {"name": "__before", "description": "hidden"},
            ],
        }
        embed = workflow_detail_embed("wf", wf)
        field_values = [f.value for f in embed.fields]
        assert any("steps" in v for v in field_values)
        # __before should be excluded
        assert not any("__before" in v for v in field_values)

    def test_with_settings_args(self):
        wf = {
            "type": "txt2img",
            "description": "desc",
            "settings": [
                {
                    "name": "resolution",
                    "args": [
                        {"name": "width", "type": "int", "required": True, "description": "Width"},
                        {"name": "height", "type": "int", "required": False, "description": "Height"},
                    ],
                },
            ],
        }
        embed = workflow_detail_embed("wf", wf)
        field_values = [f.value for f in embed.fields]
        assert any("width" in v for v in field_values)
        assert any("height" in v for v in field_values)


class TestWorkflowListEmbed:
    def test_basic(self):
        wfs = {
            "wf1": {"type": "txt2img", "description": "First"},
            "wf2": {"type": "img2img", "description": "Second"},
        }
        embed = workflow_list_embed(wfs)
        assert embed.title == i18n.get("embed.titles.available_workflows")
        assert len(embed.fields) == 2
        assert embed.footer.text == i18n.get("embed.messages.workflow_list_footer")

    def test_with_type_filter(self):
        wfs = {"wf1": {"type": "txt2img", "description": "d"}}
        embed = workflow_list_embed(wfs, type_filter="txt2img")
        assert i18n.get("embed.messages.workflow_type_filter", type_filter="txt2img") in embed.description

    def test_groups_by_type(self):
        wfs = {
            "a": {"type": "txt2img", "description": "d1"},
            "b": {"type": "txt2img", "description": "d2"},
            "c": {"type": "upscale", "description": "d3"},
        }
        embed = workflow_list_embed(wfs)
        field_names = [f.name for f in embed.fields]
        assert any("TXT2IMG" in n for n in field_names)
        assert any("UPSCALE" in n for n in field_names)
