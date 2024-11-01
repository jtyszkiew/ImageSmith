import io
import os
import urllib
import uuid

import yaml
import json
import asyncio
import websockets
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional, Dict
import importlib.util
import inspect
import sys


class Plugin:
    """Base class for bot plugins"""
    def __init__(self, bot):
        print(f"Plugin.__init__ called for {self.__class__.__name__}")
        self.bot = bot

    async def on_load(self):
        """Called when the plugin is loaded"""
        print(f"Plugin.on_load called for {self.__class__.__name__}")

    async def on_unload(self):
        """Called when the plugin is unloaded"""
        print(f"Plugin.on_unload called for {self.__class__.__name__}")


class HookManager:
    """Manages hooks for bot extensibility"""

    def __init__(self):
        self.hooks = {}

    def register_hook(self, hook_name: str, callback):
        """Register a new hook"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        self.hooks[hook_name].append(callback)

    async def execute_hook(self, hook_name: str, *args, **kwargs):
        """Execute all callbacks for a given hook"""
        if hook_name in self.hooks:
            results = []
            for callback in self.hooks[hook_name]:
                result = await callback(*args, **kwargs)
                results.append(result)
            return results
        return []

class WorkflowManager:
    """Manages ComfyUI workflows and their configurations"""
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.workflows = self.config['workflows']
        self.default_workflow = self.config.get('default_workflow')

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def get_workflow(self, name: str) -> dict:
        """Get workflow configuration by name"""
        return self.workflows.get(name, {})

    def get_selectable_workflows(self) -> Dict[str, dict]:
        """Get all workflows that are marked as selectable"""
        return {k: v for k, v in self.workflows.items()
                if v.get('selectable', True)}

    def load_workflow_file(self, workflow_path: str) -> dict:
        """Load workflow JSON file"""
        with open(workflow_path, 'r') as f:
            return json.load(f)

    def update_prompt_node(self, workflow_json: dict, prompt: str, workflow_config: dict) -> dict:
        """Update the prompt in the specified node"""
        try:
            # Get the text prompt node ID from workflow config
            text_prompt_node_id = workflow_config.get('text_prompt_node_id')
            if not text_prompt_node_id:
                print(f"Warning: No text_prompt_node_id specified in workflow config")
                return workflow_json

            # Convert node ID to string as JSON keys are strings
            node_id = str(text_prompt_node_id)

            if node_id not in workflow_json:
                print(f"Warning: Node ID {node_id} not found in workflow")
                return workflow_json

            node = workflow_json[node_id]

            # Update the text input in the node
            if 'inputs' in node:
                # Check if the node has a 'text' input
                if 'text' in node['inputs']:
                    node['inputs']['text'] = prompt
                    print(f"Updated prompt in node {node_id}: {prompt}")
                else:
                    print(f"Warning: Node {node_id} does not have a 'text' input")
            else:
                print(f"Warning: Node {node_id} does not have inputs")

            return workflow_json
        except Exception as e:
            print(f"Error updating prompt node: {e}")
            return workflow_json

    def _apply_setting(self, workflow_json: dict, setting_name: str, setting_def: dict, params: list[str] = None):
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
                print(f"Applied setting: {setting_name}")
        except Exception as e:
            print(f"Error applying setting {setting_name}: {e}")

    def _find_setting_def(self, workflow: dict, setting_name: str) -> Optional[dict]:
        """Find setting definition in workflow settings"""
        if 'settings' not in workflow:
            return None

        for setting_def in workflow['settings']:
            if setting_def.get('name') == setting_name:
                return setting_def
        return None

    def apply_settings(self, workflow_json: dict, settings_str: str = None) -> dict:
        """Apply settings to a workflow including __before and __after"""
        workflow = self.get_workflow(self.default_workflow)
        if not workflow:
            return workflow_json

        try:
            # Apply __before settings if they exist
            before_setting = self._find_setting_def(workflow, '__before')
            if before_setting:
                print("Applying __before settings...")
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
                        print(f"Warning: Setting '{func_name}' not found in workflow configuration")

            # Apply __after settings if they exist
            after_setting = self._find_setting_def(workflow, '__after')
            if after_setting:
                print("Applying __after settings...")
                self._apply_setting(workflow_json, '__after', after_setting)

            return workflow_json

        except Exception as e:
            print(f"Error applying settings: {e}")
            return workflow_json

    def prepare_workflow(self, workflow_name: str, prompt: str, settings: Optional[str] = None) -> dict:
        """Prepare a workflow with prompt and settings"""
        try:
            # Get workflow configuration
            workflow_config = self.get_workflow(workflow_name)
            if not workflow_config:
                raise ValueError(f"Workflow '{workflow_name}' not found")

            # Load workflow file
            workflow_json = self.load_workflow_file(workflow_config['workflow'])

            # Update prompt
            workflow_json = self.update_prompt_node(workflow_json, prompt, workflow_config)

            # Apply settings
            workflow_json = self.apply_settings(workflow_json, settings)

            return workflow_json
        except Exception as e:
            print(f"Error preparing workflow: {e}")
            raise


class ComfyUIClient:
    """Client for interacting with ComfyUI API"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.ws_url = self.base_url.replace('http', 'ws')
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.client_id = str(uuid.uuid4())
        print(f"Generated client ID: {self.client_id}")

    async def connect(self):
        """Establish connections to ComfyUI"""
        try:
            self.session = aiohttp.ClientSession()

            # Test connection to API
            async with self.session.get(f"{self.base_url}/history") as response:
                if response.status != 200:
                    raise Exception(f"Failed to connect to ComfyUI API: {response.status}")

            # Connect to WebSocket
            self.ws = await websockets.connect(f"{self.ws_url}/ws?clientId={self.client_id}")
            print("Connected to ComfyUI WebSocket")

        except Exception as e:
            if self.session:
                await self.session.close()
            if self.ws:
                await self.ws.close()
            raise Exception(f"Failed to connect to ComfyUI: {e}")

    async def close(self):
        """Close all connections"""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None
            if self.session:
                await self.session.close()
                self.session = None
        except Exception as e:
            print(f"Error during cleanup: {e}")

    async def generate(self, workflow: dict) -> dict:
        """Send generation request to ComfyUI"""
        if self.session is None:
            raise Exception("Client not connected")

        prompt_data = {
            'prompt': workflow,
            'client_id': self.client_id
        }

        try:
            async with self.session.post(
                    f"{self.base_url}/prompt",
                    json=prompt_data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Generation request failed with status {response.status}: {error_text}")
                return await response.json()
        except Exception as e:
            print(f"Generation request failed: {e}")
            raise

    async def _test_image_access(self, url: str) -> bool:
        """Test if an image URL is accessible"""
        if self.session is None:
            return False

        try:
            async with self.session.get(url) as response:
                return response.status == 200
        except Exception as e:
            print(f"Error testing image access: {e}")
            return False

    def _get_image_url(self, image_data: dict) -> str:
        """Construct the image URL from image data"""
        try:
            filename = image_data.get('filename')
            subfolder = image_data.get('subfolder', '')
            type_ = image_data.get('type', 'output')

            # Build the URL with proper encoding
            params = []
            if filename:
                params.append(f"filename={urllib.parse.quote(filename)}")
            if subfolder:
                params.append(f"subfolder={urllib.parse.quote(subfolder)}")
            if type_:
                params.append(f"type={urllib.parse.quote(type_)}")

            # Join all parameters
            query_string = '&'.join(params)

            # Construct final URL
            url = f"{self.base_url}/view?{query_string}"
            print(f"Generated image URL: {url}")
            return url
        except Exception as e:
            print(f"Error generating image URL: {e}")
            return None

    def _create_progress_bar(self, value: int, max_value: int, length: int = 10) -> str:
        """Create a text-based progress bar"""
        filled = int(length * (value / max_value))
        bar = '█' * filled + '░' * (length - filled)
        percentage = int(100 * (value / max_value))
        return f"[{bar}] {percentage}%"

    async def listen_for_updates(self, prompt_id: str, message_callback):
        """Listen for updates about a specific generation"""
        if self.ws is None or self.session is None:
            raise Exception("Client not connected")

        current_image_data = None
        generation_complete = False
        node_progress = {}  # Track progress for each node

        while not generation_complete:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                # print(f"Received WebSocket message: {data}")

                msg_type = data.get('type')
                msg_data = data.get('data', {})

                # Check if this message is for our prompt
                if msg_data.get('prompt_id') != prompt_id:
                    continue

                if msg_type == 'progress':
                    node = msg_data.get('node')
                    value = msg_data.get('value', 0)
                    max_value = msg_data.get('max', 100)

                    # Store progress for this node
                    node_progress[node] = {
                        'value': value,
                        'max': max_value
                    }

                    # Create progress status message
                    progress_bar = self._create_progress_bar(value, max_value)
                    status = f"🔄 Processing node {node}...\n{progress_bar}"

                    # Update status without changing the image
                    await message_callback(status, None)

                elif msg_type == 'executing':
                    node_id = msg_data.get('node')
                    if node_id:
                        # Clear progress for new node
                        if node_id in node_progress:
                            del node_progress[node_id]
                        await message_callback(f"🔄 Processing node {node_id}...", None)
                    else:
                        # Final execution message
                        generation_complete = True

                        # Send final message with current image if we have one
                        image_file = None
                        if current_image_data:
                            image_file = discord.File(
                                io.BytesIO(current_image_data),
                                filename=f"forge_{prompt_id}.png"
                            )
                        await message_callback("✅ Generation complete!", image_file)

                elif msg_type == 'executed':
                    node_output = msg_data.get('output')

                    if node_output and isinstance(node_output, dict) and 'images' in node_output:
                        images = node_output['images']
                        if images and isinstance(images, list):
                            for image_data in images:
                                if isinstance(image_data, dict) and 'filename' in image_data:
                                    # Get image URL
                                    image_url = self._get_image_url(image_data)
                                    if image_url:
                                        print(f"Attempting to download image from: {image_url}")
                                        async with self.session.get(image_url) as response:
                                            if response.status == 200:
                                                # Store the image data
                                                current_image_data = await response.read()
                                                print(f"Downloaded new image data: {len(current_image_data)} bytes")

                                                # Create new file object for the new image
                                                image_file = discord.File(
                                                    io.BytesIO(current_image_data),
                                                    filename=f"forge_{prompt_id}.png"
                                                )

                                                # Update with new image
                                                await message_callback("🖼 New image generated!", image_file)
                                            else:
                                                print(f"Failed to download image: {response.status}")

                elif msg_type == 'error':
                    error_msg = msg_data.get('error', 'Unknown error')
                    print(f"ComfyUI Error: {error_msg}")
                    await message_callback(f"❌ Error: {error_msg}")
                    raise Exception(f"ComfyUI Error: {error_msg}")

            except websockets.ConnectionClosed:
                print("WebSocket connection closed unexpectedly")
                await message_callback("❌ Connection closed unexpectedly")
                raise

            except json.JSONDecodeError as e:
                print(f"Failed to parse WebSocket message: {e}")
                continue

            except Exception as e:
                print(f"Error while listening for updates: {str(e)}")
                await message_callback(f"❌ Error: {str(e)}")
                raise

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


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


class ImageButton(discord.ui.Button):
    """Custom button for image interactions"""

    def __init__(self, label: str, custom_id: str, emoji: str):
        super().__init__(
            label=label,
            custom_id=custom_id,
            style=discord.ButtonStyle.secondary,
            emoji=emoji
        )


class ImageView(discord.ui.View):
    """Custom view for image interaction buttons"""

    def __init__(self, prompt_id: str, has_upscaler: bool = False):
        super().__init__(timeout=None)

        if has_upscaler:
            self.add_item(ImageButton("Upscale", f"upscale_{prompt_id}", "✨"))

        self.add_item(ImageButton("Regenerate", f"regenerate_{prompt_id}", "🔄"))
        self.add_item(ImageButton("Use as Input", f"img2img_{prompt_id}", "🖼"))

class GenerationQueue:
    """Manages queued generation requests"""
    def __init__(self):
        self.queue = asyncio.Queue()
        self.processing = False
        self.current_task = None

    async def add_to_queue(self, generation_func, *args, **kwargs):
        """Add a new generation request to the queue"""
        await self.queue.put((generation_func, args, kwargs))
        print(f"Added new generation to queue. Queue size: {self.queue.qsize()}")

        if not self.processing:
            asyncio.create_task(self.process_queue())

    async def process_queue(self):
        """Process queued generation requests"""
        if self.processing:
            return

        self.processing = True
        try:
            while not self.queue.empty():
                generation_func, args, kwargs = await self.queue.get()
                print(f"Processing generation from queue. Remaining: {self.queue.qsize()}")

                try:
                    self.current_task = asyncio.current_task()
                    await generation_func(*args, **kwargs)
                except Exception as e:
                    print(f"Error processing generation: {e}")
                finally:
                    self.current_task = None
                    self.queue.task_done()

        finally:
            self.processing = False

    def is_processing(self) -> bool:
        """Check if currently processing a generation"""
        return self.processing

    def get_queue_position(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

class ComfyUIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(command_prefix='/', intents=intents)

        self.workflow_manager = WorkflowManager('configuration.yml')
        self.hook_manager = HookManager()
        self.comfy_client = None
        self.plugins = []
        self.active_generations = {}
        self.generation_queue = GenerationQueue()  # Add queue system

    async def setup_hook(self) -> None:
        """Setup hook that runs when the bot starts."""
        print("Setting up bot...")
        await self.load_plugins()

        try:
            # Initialize ComfyUI client and connect
            self.comfy_client = ComfyUIClient(self.workflow_manager.config['comfyui']['url'])
            await self.comfy_client.connect()
            print("Connected to ComfyUI")
        except Exception as e:
            print(f"Failed to connect to ComfyUI: {e}")
            await self.cleanup()
            sys.exit(1)

        print("Registering commands...")
        try:
            # Add commands to the command tree
            self.tree.add_command(self.forge_command())
            self.tree.add_command(self.workflows_command())

            # Sync commands
            commands = await self.tree.sync()
            print(f"Registered {len(commands)} commands:")
            for cmd in commands:
                print(f"- /{cmd.name}")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
            await self.cleanup()
            sys.exit(1)

    async def cleanup(self):
        """Clean up resources"""
        print("Cleaning up resources...")
        try:
            if self.comfy_client:
                await self.comfy_client.close()
            await self.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    async def load_plugins(self):
        """Load plugins from the plugins directory"""
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            print("No plugins directory found")
            return

        # Add the current directory to Python path for imports
        import sys
        sys.path.append(str(Path.cwd()))

        # Skip __init__.py when loading plugins
        plugin_files = [f for f in plugins_dir.glob("*.py") if f.name != "__init__.py"]

        for plugin_file in plugin_files:
            print(f"\n{'='*50}")
            print(f"Loading plugin file: {plugin_file}")
            print(f"{'='*50}")

            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    plugin_file.stem,
                    plugin_file
                )
                if spec is None:
                    print(f"Failed to get spec for {plugin_file}")
                    continue

                module = importlib.util.module_from_spec(spec)
                if spec.loader is None:
                    print(f"Failed to get loader for {plugin_file}")
                    continue

                spec.loader.exec_module(module)
                print(f"Successfully loaded module: {module.__name__}")

                # Debug: print all items in module
                print("\nModule contents:")
                for item_name in dir(module):
                    if item_name.startswith('__'):  # Skip built-in attributes
                        continue

                    try:
                        obj = getattr(module, item_name)
                        print(f"Found item: {item_name} (type: {type(obj)})")

                        # Check if it's a class
                        if inspect.isclass(obj):
                            print(f"  - Is class: Yes")
                            # Check if it's a Plugin subclass
                            try:
                                from plugin_base import Plugin
                                if issubclass(obj, Plugin):
                                    print(f"  - Is Plugin subclass: Yes")
                                    if obj != Plugin:  # Don't load the base Plugin class
                                        print(f"\nInitializing plugin: {obj.__name__}")
                                        try:
                                            plugin_instance = obj(self)
                                            print(f"Successfully created instance")
                                            print(f"Running on_load...")
                                            await plugin_instance.on_load()
                                            print(f"on_load completed")
                                            self.plugins.append(plugin_instance)
                                            print(f"Successfully loaded and registered plugin: {obj.__name__}\n")
                                        except Exception as e:
                                            print(f"Error instantiating plugin {obj.__name__}: {e}")
                                            import traceback
                                            traceback.print_exc()
                                else:
                                    print(f"  - Is Plugin subclass: No")
                            except Exception as e:
                                print(f"  - Error checking Plugin subclass: {e}")
                        else:
                            print(f"  - Is class: No")
                    except Exception as e:
                        print(f"Error processing item {item_name}: {e}")

            except Exception as e:
                print(f"Failed to load plugin {plugin_file}: {e}")
                import traceback
                traceback.print_exc()

        print(f"\nLoaded {len(self.plugins)} plugins:")
        for plugin in self.plugins:
            print(f"- {plugin.__class__.__name__}")

    async def process_generation(self, workflow_json: dict, prompt: str, message: discord.Message):
        try:
            # Pre-generation hooks
            modified_workflow = workflow_json.copy()
            hook_results = await self.hook_manager.execute_hook('pre_generate', modified_workflow, prompt)

            # Apply any modifications from hooks
            for result in hook_results:
                if isinstance(result, dict):
                    modified_workflow.update(result)

            # Generate image
            result = await self.comfy_client.generate(modified_workflow)
            if 'error' in result:
                raise Exception(result['error'])

            prompt_id = result.get('prompt_id')
            if not prompt_id:
                raise Exception("No prompt ID received from ComfyUI")

            # Update status callback with hook integration
            async def update_message(status: str, image_file: Optional[discord.File] = None):
                try:
                    if image_file:
                        # Track successful generation
                        await self.hook_manager.execute_hook(
                            'generation_complete',
                            prompt,
                            str(image_file.filename),
                            True
                        )
                except Exception as e:
                    print(f"Error in generation hooks: {e}")

                # Update Discord message
                new_embed = message.embeds[0].copy()

                # Update status field
                for i, field in enumerate(new_embed.fields):
                    if field.name == "Status":
                        new_embed.set_field_at(i, name="Status", value=status, inline=False)
                        break

                if image_file:
                    await message.edit(embed=new_embed, attachments=[image_file])
                else:
                    await message.edit(embed=new_embed)

            # Listen for updates
            await self.comfy_client.listen_for_updates(prompt_id, update_message)

        except Exception as e:
            # Track failed generation
            await self.hook_manager.execute_hook(
                'generation_complete',
                prompt,
                None,
                False
            )
            raise

    def forge_command(self):
        """Create the forge command"""
        @app_commands.command(
            name="forge",
            description="Forge an image using ComfyUI"
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
            workflow_name = workflow or self.workflow_manager.default_workflow
            workflow_config = self.workflow_manager.get_workflow(workflow_name)

            if not workflow_config:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"Workflow '{workflow_name}' not found!",
                        color=0xFF0000
                    )
                )
                return

            # Create initial embed
            embed = discord.Embed(title="🔨 ImageSmith Forge", color=0x2F3136)

            # Check queue position
            queue_position = self.generation_queue.get_queue_position()
            if queue_position > 0:
                status = f"⏳ Queued (Position: {queue_position + 1})"
            else:
                status = "Starting generation..."

            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Workflow", value=workflow_name, inline=True)
            embed.add_field(name="Prompt", value=prompt, inline=False)
            if settings:
                embed.add_field(name="Settings", value=f"```{settings}```", inline=False)

            # Send initial response
            await interaction.response.send_message(embed=embed)
            message = await interaction.original_response()

            # Define the generation function that will be queued
            async def run_generation():
                try:
                    # Prepare workflow
                    workflow_json = self.workflow_manager.prepare_workflow(
                        workflow_name,
                        prompt,
                        settings
                    )

                    # Execute hooks
                    await self.hook_manager.execute_hook('pre_generate', workflow_json, prompt)

                    # Generate image
                    result = await self.comfy_client.generate(workflow_json)
                    if 'error' in result:
                        raise Exception(result['error'])

                    prompt_id = result.get('prompt_id')
                    if not prompt_id:
                        raise Exception("No prompt ID received from ComfyUI")

                    # Define update callback
                    async def update_message(status: str, image_file: Optional[discord.File] = None):
                        new_embed = message.embeds[0].copy()

                        # Update status field
                        for i, field in enumerate(new_embed.fields):
                            if field.name == "Status":
                                new_embed.set_field_at(i, name="Status", value=status, inline=False)
                                break

                        if image_file:
                            if status == "✅ Generation complete!":
                                view = discord.ui.View()
                                if workflow_config.get('upscaler'):
                                    view.add_item(discord.ui.Button(
                                        style=discord.ButtonStyle.primary,
                                        label="✨ Upscale",
                                        custom_id=f"upscale_{prompt_id}"
                                    ))
                                view.add_item(discord.ui.Button(
                                    style=discord.ButtonStyle.secondary,
                                    label="🔄 Regenerate",
                                    custom_id=f"regenerate_{prompt_id}"
                                ))
                                view.add_item(discord.ui.Button(
                                    style=discord.ButtonStyle.secondary,
                                    label="🖼 Use as Input",
                                    custom_id=f"img2img_{prompt_id}"
                                ))
                                await message.edit(embed=new_embed, attachments=[image_file], view=view)
                            else:
                                await message.edit(embed=new_embed, attachments=[image_file])
                        else:
                            await message.edit(embed=new_embed)

                    # Listen for updates
                    await self.comfy_client.listen_for_updates(prompt_id, update_message)

                except Exception as e:
                    error_embed = discord.Embed(title="🔨 ImageSmith Forge", color=0xFF0000)
                    error_embed.add_field(name="Status", value=f"❌ Error: {str(e)}", inline=False)
                    error_embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
                    error_embed.add_field(name="Workflow", value=workflow_name, inline=True)
                    await message.edit(embed=error_embed)

            # Add generation to queue
            await self.generation_queue.add_to_queue(run_generation)

        return forge

    def workflows_command(self):
        """Create the workflows command"""

        @app_commands.command(
            name="workflows",
            description="List available workflows"
        )
        async def workflows(interaction: discord.Interaction):
            workflows = self.workflow_manager.get_selectable_workflows()

            embed = discord.Embed(title="🔨 Available Forge Workflows", color=0x2F3136)
            embed.set_footer(text=f"Requested by {interaction.user.name}")

            for name, workflow in workflows.items():
                embed.add_field(
                    name=name,
                    value=workflow.get('description', 'No description'),
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        return workflows

    async def on_ready(self):
        """Called when the bot is ready"""
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print(f'Connected to {len(self.guilds)} guilds')

        # Generate invite link with required permissions
        permissions = discord.Permissions(
            send_messages=True,
            read_messages=True,
            attach_files=True,
            embed_links=True,
            use_external_emojis=True,
            add_reactions=True,
            read_message_history=True,
        )

        invite_link = discord.utils.oauth_url(
            self.user.id,
            permissions=permissions,
            scopes=("bot", "applications.commands")
        )

        print("\nInvite link:")
        print(invite_link)
        print("\nBot is ready!")


async def main():
    bot = ComfyUIBot()

    print("Starting bot...")
    try:
        await bot.start(os.getenv('DISCORD_TOKEN') or bot.workflow_manager.config['discord']['token'])
    except KeyboardInterrupt:
        print("\nShutting down...")
        await bot.cleanup()
    except Exception as e:
        print(f"Fatal error: {e}")
        await bot.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
