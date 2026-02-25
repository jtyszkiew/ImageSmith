from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import discord
from discord import ui

from logger import logger
from src.core.i18n import i18n


@dataclass
class FormField:
    """Represents a single form field configuration"""
    name: str
    type: str
    description: str
    message: str
    on_submit: str
    required: bool = True
    on_default: Optional[str] = None  # Add on_default handler
    options: Optional[List[Dict[str, str]]] = None
    on_provided: Optional[str] = None

    @classmethod
    def from_dict(cls, field_data: dict) -> 'FormField':
        return cls(
            name=field_data['name'],
            type=field_data['type'],
            description=field_data.get('description', ''),
            message=field_data['message'],
            on_submit=field_data.get('on_submit', ''),
            required=field_data.get('required', True),
            on_default=field_data.get('on_default', None),  # Get on_default from YAML
            options=field_data.get('options', None),
            on_provided=field_data.get('on_provided', None)
        )


class SubmitButton(ui.Button):
    def __init__(self, view: 'FormView'):
        super().__init__(
            label=i18n.get("form.submit"),
            style=discord.ButtonStyle.success,
            custom_id="form_submit"
        )
        self.form_view = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.form_view.user_id:
            await interaction.response.send_message(i18n.get("form.cannot_interact"), ephemeral=True)
            return

        # Validate required fields
        missing_fields = []
        for field in self.form_view.fields:
            if (field.required and
                    field.name not in self.form_view.completed_fields and
                    field.name not in self.form_view.skipped_fields):
                missing_fields.append(field.name)

        if missing_fields:
            await interaction.response.send_message(
                i18n.get("form.fill_required", fields=', '.join(missing_fields)),
                ephemeral=True
            )
            return

        # Add any uncompleted optional fields to skipped_fields
        for field in self.form_view.fields:
            if not field.required and field.name not in self.form_view.completed_fields:
                self.form_view.skipped_fields.add(field.name)

        # Mark form as submitted
        self.form_view.submitted = True
        await interaction.response.defer(ephemeral=True)


@dataclass
class FormDefinition:
    """Represents the complete form configuration"""
    fields: List[FormField]

    @classmethod
    def from_yaml(cls, yaml_data: dict) -> 'FormDefinition':
        fields = []
        for field_data in yaml_data.get('form', []):
            fields.append(FormField.from_dict(field_data))
        return cls(fields=fields)


class FormFieldHandler(ABC):
    """Base class for form field handlers"""

    @abstractmethod
    def create_component(self, field: FormField) -> ui.Item:
        """Create the appropriate Discord UI component for this field type"""
        pass

    @abstractmethod
    async def process_value(self, value: Any) -> Any:
        """Process and validate the value from the component"""
        pass

    @abstractmethod
    def requires_modal(self) -> bool:
        """Return True if this field type requires a modal"""
        pass


class TextFieldHandler(FormFieldHandler):
    """Handler for number input fields"""

    def create_component(self, field: FormField) -> ui.TextInput:
        return ui.TextInput(
            label=field.message,
            placeholder=i18n.get("form.enter_number"),
            custom_id=f"form_field_{field.name}"
        )

    async def process_value(self, value: str) -> int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(i18n.get("form.invalid_number"))

    def requires_modal(self) -> bool:
        return True


class TextareaFieldHandler(FormFieldHandler):
    """Handler for multi-line text input fields"""

    def create_component(self, field: FormField) -> ui.TextInput:
        return ui.TextInput(
            label=field.message,
            placeholder=i18n.get("form.enter_text"),
            style=discord.TextStyle.long,
            custom_id=f"form_field_{field.name}"
        )

    async def process_value(self, value: str) -> str:
        return str(value)

    def requires_modal(self) -> bool:
        return True


class SelectFieldHandler(FormFieldHandler):
    """Handler for Loras selection fields"""

    def __init__(self, max_values: Optional[int] = None):
        self.max_values = max_values

    def create_component(self, field: FormField) -> ui.Select:
        options = [
            discord.SelectOption(label=option['name'], value=option['value'])
            for option in field.options or []
        ]
        return ui.Select(
            placeholder=field.description,
            options=options,
            max_values=len(options) if self.max_values is None else self.max_values,
            custom_id=f"form_field_{field.name}"
        )

    async def process_value(self, values: List[str]) -> List[str]:
        return values

    def requires_modal(self) -> bool:
        return False


class ResolutionFieldHandler(SelectFieldHandler):
    """Handler for resolution input fields"""
    def __init__(self):
        super().__init__(max_values=1)

    async def process_value(self, values: List[str]) -> List[int]:
        if not values:
            raise ValueError(i18n.get("form.no_resolution"))

        max_dimension = 2048  # or whatever your max should be

        try:
            # Strip whitespace and convert to lowercase
            resolution = values[0].strip().lower()

            # Validate format using more specific split
            if 'x' not in resolution:
                raise ValueError(i18n.get("form.resolution_separator"))

            width, height = map(int, resolution.split('x', 1))

            # Add validation for reasonable dimensions
            if width <= 0 or height <= 0:
                raise ValueError(i18n.get("form.resolution_positive"))

            # Optional: Add maximum dimension check
            if width > max_dimension or height > max_dimension:
                raise ValueError(i18n.get("form.resolution_max", max_dimension=max_dimension))

            return [int(width), int(height)]

        except ValueError as e:
            # Re-raise with more specific message if it's our custom error
            known_errors = (
                i18n.get("form.resolution_separator"),
                i18n.get("form.resolution_positive"),
                i18n.get("form.resolution_max", max_dimension=max_dimension),
            )
            if str(e) in known_errors:
                raise
            raise ValueError(i18n.get("form.resolution_format"))

    def requires_modal(self) -> bool:
        return False

class FormModal(ui.Modal):
    """Modal for collecting form input"""

    def __init__(self, field: FormField, handler: FormFieldHandler, completed_fields: Set[str], user_id: int):
        super().__init__(title=field.description)
        self.field = field
        self.handler = handler
        self.completed_fields = completed_fields
        self.user_id = user_id
        self.add_item(handler.create_component(field))

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.get("form.cannot_interact"), ephemeral=True)
            return

        try:
            # Get the raw value from the first component
            raw_value = interaction.data['components'][0]['components'][0]['value']

            # Process the value using the handler's process_value method
            processed_value = await self.handler.process_value(raw_value)

            # Initialize form_data if it doesn't exist
            if not hasattr(interaction.client, 'form_data'):
                interaction.client.form_data = {}

            # Store the processed value
            interaction.client.form_data[self.field.name] = processed_value
            self.completed_fields.add(self.field.name)


            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                i18n.get("form.error_processing", field_name=self.field.name, error=i18n.sanitize_error(str(e))),
                ephemeral=True
            )


class FormButton(ui.Button):
    """Button that triggers a modal form"""
    def __init__(self, field: FormField, handler: FormFieldHandler, view: 'FormView'):
        if field.required:
            label = i18n.get("form.set_field", field_name=field.name)
        else:
            label = i18n.get("form.set_field_optional", field_name=field.name)
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"form_button_{field.name}"
        )
        self.field = field
        self.handler = handler
        self.form_view = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.form_view.user_id:
            await interaction.response.send_message(i18n.get("form.cannot_interact"), ephemeral=True)
            return

        modal = FormModal(self.field, self.handler, self.form_view.completed_fields, self.form_view.user_id)
        await interaction.response.send_modal(modal)


class FormView(ui.View):
    """View containing all form fields"""
    def __init__(self, fields: List[FormField], handlers: Dict[str, FormFieldHandler], completed_fields: Set[str], user_id: int):
        super().__init__()
        self.fields = fields
        self.completed_fields = completed_fields
        self.user_id = user_id
        self.submitted = False
        self.skipped_fields = set()  # Track fields that were skipped (optional fields)

        for field in fields:
            handler = handlers.get(field.type)
            if handler:
                if handler.requires_modal():
                    self.add_item(FormButton(field, handler, self))
                else:
                    component = handler.create_component(field)
                    if not field.required:
                        component.placeholder = f"{component.placeholder} (Optional)"
                    self.add_item(component)

        self.add_item(SubmitButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(i18n.get("form.cannot_interact"), ephemeral=True)
            return False

        component_type = interaction.data.get("component_type")
        if component_type == discord.ComponentType.select.value:
            try:
                custom_id = interaction.data["custom_id"]
                field_name = custom_id.split("form_field_")[-1]
                values = interaction.data["values"]

                if not hasattr(interaction.client, 'form_data'):
                    interaction.client.form_data = {}

                interaction.client.form_data[field_name] = values
                self.completed_fields.add(field_name)

                await interaction.response.defer(ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(
                    i18n.get("form.error_selection", error=i18n.sanitize_error(str(e))),
                    ephemeral=True
                )
        return True


class DynamicFormManager:
    """Manager for handling dynamic forms"""

    def __init__(self):
        self.field_handlers = {
            'text': TextFieldHandler(),
            'textarea': TextareaFieldHandler(),
            'resolution': ResolutionFieldHandler(),
            'select': SelectFieldHandler(),
        }

    def register_field_handler(self, field_type: str, handler: FormFieldHandler):
        """Register a new field handler"""
        self.field_handlers[field_type] = handler

    async def process_workflow_form(self,
                                    interaction: discord.Interaction,
                                    workflow_config: dict,
                                    workflow_json: dict,
                                    message: discord.Message) -> dict:
        """Process the form defined in the workflow configuration"""
        if 'form' not in workflow_config:
            return workflow_json

        form_definition = FormDefinition.from_yaml(workflow_config)

        if not hasattr(interaction.client, 'form_data'):
            interaction.client.form_data = {}

        interaction.client.form_data['workflow_json'] = workflow_json
        interaction.client.form_data['field_definitions'] = form_definition.fields

        # Set to track completed fields
        completed_fields = set()

        # Update message to show we're collecting inputs
        status_label = i18n.get("embed.fields.status")
        embed = message.embeds[0].copy()
        for i, field in enumerate(embed.fields):
            if field.name == status_label:
                embed.set_field_at(i, name=status_label, value=i18n.get("form.please_fill"), inline=False)
                break

        # Create a view with all form fields
        view = FormView(form_definition.fields, self.field_handlers, completed_fields, interaction.user.id)
        await message.edit(embed=embed, view=view)

        # Wait for form submission
        timeout = 300.0
        end_time = datetime.utcnow() + timedelta(seconds=timeout)

        while not view.submitted:
            try:
                remaining = (end_time - datetime.utcnow()).total_seconds()
                if remaining <= 0:
                    raise TimeoutError()

                def check_interaction(i):
                    return (isinstance(i.data, dict) and
                            i.user.id == interaction.user.id and
                            (i.data.get('custom_id', '').startswith(('form_field_', 'form_button_', 'form_submit'))))

                await interaction.client.wait_for(
                    'interaction',
                    timeout=remaining,
                    check=check_interaction
                )
            except TimeoutError:
                embed = message.embeds[0].copy()
                # Find the status field index
                status_field_index = next(
                    (i for i, field in enumerate(embed.fields)
                     if field.name == status_label),
                    None
                )
                if status_field_index is not None:
                    embed.set_field_at(
                        status_field_index,
                        name=status_label,
                        value=i18n.get("form.timed_out"),
                        inline=False
                    )
                await message.edit(embed=embed, view=None)
                return None

        # Update message to show we're proceeding with generation
        embed = message.embeds[0].copy()
        for i, field in enumerate(embed.fields):
            if field.name == status_label:
                embed.set_field_at(i, name=status_label, value=i18n.get("form.proceeding"), inline=False)
                break
        await message.edit(embed=embed, view=None)

        return await self.apply_form_data_to_workflow(interaction.client.form_data, workflow_json)

    async def apply_form_data_to_workflow(self, form_data: dict, workflow_json: dict) -> dict:
        """Apply the collected form data to the workflow JSON"""
        modified_json = workflow_json.copy()

        # Convert field definitions to FormField objects if they're dicts
        field_definitions = []
        for field_def in form_data.get('field_definitions', []):
            if isinstance(field_def, dict):
                field_def = FormField.from_dict(field_def)
            field_definitions.append(field_def)

        # Process all fields, including those not filled in
        for field_def in field_definitions:
            field_name = field_def.name

            if field_name in form_data:
                # Field was filled in, use on_submit
                value = form_data[field_name]

                # Execute the on_submit code
                local_vars = {'workflowjson': modified_json}
                local_vars['value'] = value

                exec(field_def.on_submit, {}, local_vars)

                # Get and call the on_submit function
                on_submit = local_vars.get('on_submit')
                if on_submit:
                    try:
                        handler = self.field_handlers.get(field_def.type)
                        on_submit(modified_json, await handler.process_value(value))
                    except Exception as e:
                        logger.error(f"Error executing on_submit for field: {field_name}, error: {e}", exc_info=True)

                        raise e

            elif not field_def.required and field_def.on_default:
                # Field wasn't filled in but has a default handler
                local_vars = {'workflowjson': modified_json}

                # Execute the on_default code
                exec(field_def.on_default, {}, local_vars)

                # Get and call the on_default function
                on_default = local_vars.get('on_default')
                if on_default:
                    on_default(modified_json)

        return modified_json
