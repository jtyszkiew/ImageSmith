import io
import json
from pathlib import Path
from typing import Dict, Optional, Any

from PIL import Image
import yaml

from logger import logger


class WorkflowManager:
    """Manages ComfyUI workflows and their configurations"""

    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.workflows = self.config['workflows']
        self.default_workflow = self.config.get('default_workflow')

        # Get ComfyUI input directory from config
        self.input_dir = Path(self.config.get('comfyui', {}).get('input_dir', 'input'))
        if not self.input_dir.is_absolute():
            # If relative path, make it relative to the config file location
            config_dir = Path(config_path).parent
            self.input_dir = config_dir / self.input_dir

        # Ensure input directory exists
        self.input_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using ComfyUI input directory: {self.input_dir}")

    def update_workflow_nodes(self, workflow_json: dict, workflow_config: dict,
                              prompt: str = None, image: dict = None) -> dict:
        """Update workflow nodes with prompt and/or image data"""
        modified_workflow = workflow_json.copy()

        # Update prompt if provided and node is configured
        if prompt and 'text_prompt_node_id' in workflow_config:
            node_id = str(workflow_config['text_prompt_node_id'])
            if node_id in modified_workflow:
                node = modified_workflow[node_id]
                if 'inputs' in node and 'text' in node['inputs']:
                    node['inputs']['text'] = prompt
                    logger.debug(f"Updated prompt in node {node_id}: {prompt}")

        # Update image if provided and node is configured
        if image and 'image_input_node_id' in workflow_config:
            try:
                node_id = str(workflow_config['image_input_node_id'])
                if node_id not in modified_workflow:
                    raise ValueError(f"Node ID {node_id} not found in workflow")

                # Update node with image path
                node = modified_workflow[node_id]
                if 'inputs' in node and 'image' in node['inputs']:
                    # Just use the filename for ComfyUI
                    node['inputs']['image'] = image['name']
                    logger.debug(f"Updated image in node {node_id} with filename: {image['name']}")
                else:
                    raise ValueError(f"Node {node_id} does not have 'image' input")

            except Exception as e:
                logger.error(f"Error updating image node: {e}")
                raise ValueError(f"Failed to process input image: {str(e)}")

        return modified_workflow

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def get_workflow(self, name: str) -> dict:
        """Get workflow configuration by name"""
        return self.workflows.get(name, {})

    def get_selectable_workflows(self, workflow_type: str = None) -> Dict[str, dict]:
        """Get all workflows that are marked as selectable and match the specified type"""
        workflows = {k: v for k, v in self.workflows.items()
                     if v.get('selectable', True)}

        if workflow_type:
            workflows = {k: v for k, v in workflows.items()
                         if v.get('type', 'txt2img') == workflow_type}

        return workflows

    def get_default_workflow(self, workflow_type: str, channel_name: str = None, user_name: str = None) -> str:
        """Get default workflow for the specified type"""
        for name, workflow in self.workflows.items():
            if not channel_name and not user_name:
                if workflow.get('type', 'txt2img') == workflow_type and workflow.get('default', False):
                    return name

            default_for = workflow.get('default_for', {})

            if channel_name:
                default_for_channels = default_for.get('channels', [])

                # Check if workflow is default for this channel
                if workflow.get('type', 'txt2img') == workflow_type and channel_name in default_for_channels:
                    return name

            if user_name:
                default_for_users = default_for.get('users', [])

                # Check if workflow is default for this user
                if workflow.get('type', 'txt2img') == workflow_type and user_name in default_for_users:
                    return name

        # Return first workflow of the specified type if no default is set
        for name, workflow in self.workflows.items():
            if workflow.get('type', 'txt2img') == workflow_type:
                return name

        return None

    def load_workflow_file(self, workflow_path: str) -> dict:
        """Load workflow JSON file"""
        with open(workflow_path, 'r', encoding='utf8') as f:
            return json.load(f)

    def _apply_setting(self, workflow_json: dict, setting_name: str, setting_def: dict, params: list[Any] = None):
        """Apply a single setting to the workflow"""
        try:
            if 'code' in setting_def:
                code = setting_def['code']
                # Create function from code string
                exec(code)
                if params:
                    locals()[setting_name](workflow_json, *params)
                else:
                    locals()[setting_name](workflow_json)
                logger.debug(f"Applied setting: {setting_name}")
        except Exception as e:
            logger.error(f"Error applying setting {setting_name}: {e}", exc_info=True)

    def _find_setting_def(self, workflow: dict, setting_name: str) -> Optional[dict]:
        """Find setting definition in workflow settings"""
        if 'settings' not in workflow:
            return None

        for setting_def in workflow['settings']:
            if setting_def.get('name') == setting_name:
                return setting_def
        return None

    def apply_settings(self, workflow_json: dict, workflow_config: dict, settings_str: str = None, image: Image = None) -> dict:
        """Apply settings to a workflow including __before and __after"""
        workflow = workflow_config

        if not workflow:
            return workflow_json

        try:
            # Apply __before settings if they exist
            before_setting = self._find_setting_def(workflow, '__before')
            if before_setting:
                logger.debug("Applying __before settings...")
                if image:
                    self._apply_setting(workflow_json, '__before', before_setting, [image])
                else:
                    self._apply_setting(workflow_json, '__before', before_setting)

            # Apply custom settings if provided
            if settings_str:
                settings_list = settings_str.split(';')
                for setting in settings_list:
                    if not setting:
                        continue

                    # Parse setting name and parameters
                    if '(' in setting and ')' in setting:
                        func_name = setting.split('(')[0]
                        params_str = setting[len(func_name) + 1:-1]
                        params = [p.strip() for p in params_str.split(',') if p.strip()]
                    else:
                        func_name = setting
                        params = []

                    # Find and apply the setting
                    setting_def = self._find_setting_def(workflow, func_name)
                    if setting_def:
                        self._apply_setting(workflow_json, func_name, setting_def, params)
                    else:
                        logger.warning(f"Setting '{func_name}' not found in workflow configuration")

            # Apply __after settings if they exist
            after_setting = self._find_setting_def(workflow, '__after')
            if after_setting:
                logger.debug("Applying __after settings...")
                self._apply_setting(workflow_json, '__after', after_setting)

            return workflow_json

        except Exception as e:
            logger.error(f"Error applying settings: {e}")
            return workflow_json

    def prepare_workflow(self, workflow_name: str, prompt: str = None,
                         settings: Optional[str] = None,
                         image: Optional[dict] = None,
                         input_image: Optional[Image.Image] = None) -> dict:
        """Prepare a workflow with prompt, settings, and image data"""
        try:
            workflow_config = self.get_workflow(workflow_name)
            if not workflow_config:
                raise ValueError(f"Workflow '{workflow_name}' not found")

            # Load workflow file
            workflow_json = self.load_workflow_file(workflow_config['workflow'])

            # Update nodes with prompt and image
            workflow_json = self.update_workflow_nodes(
                workflow_json,
                workflow_config,
                prompt,
                image
            )

            # Apply settings
            workflow_json = self.apply_settings(workflow_json, workflow_config, settings, input_image)

            return workflow_json
        except Exception as e:
            logger.error(f"Error preparing workflow: {e}")
            raise
