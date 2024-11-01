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

from workflow import WorkflowManager


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

                    # Calculate the progress percentage
                    progress_percentage = (value / max_value) * 100

                    # Determine the closest milestone
                    milestones = [25, 50, 75, 100]
                    for milestone in milestones:
                        if progress_percentage >= milestone and node_progress.get(node, {}).get('last_milestone', 0) < milestone:
                            # Update progress only at milestone percentages
                            node_progress[node] = {
                                'value': value,
                                'max': max_value,
                                'last_milestone': milestone
                            }

                            # Create progress status message
                            progress_bar = self._create_progress_bar(value, max_value)
                            status = f"🔄 Processing node {node}...\n{progress_bar} ({milestone}%)"

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
        """Setup hook that runs when the bot starts"""
        print("Setting up bot...")
        await self.load_plugins()

        try:
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
            self.tree.add_command(self.reforge_command())
            self.tree.add_command(self.upscale_command())
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
            print(f"\n{'=' * 50}")
            print(f"Loading plugin file: {plugin_file}")
            print(f"{'=' * 50}")

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
                                from plugin import Plugin
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
            await self.handle_generation(interaction, 'txt2img', prompt, workflow, settings)

        return forge

    def reforge_command(self):
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
            await self.handle_generation(interaction, 'img2img', prompt, workflow, settings, image)

        return reforge

    def upscale_command(self):
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
            await self.handle_generation(interaction, 'upscale', prompt, workflow, settings, image)

        return upscale

    async def handle_generation(self,
                                interaction: discord.Interaction,
                                workflow_type: str,
                                prompt: str,
                                workflow: Optional[str] = None,
                                settings: Optional[str] = None,
                                input_image: Optional[discord.Attachment] = None):
        """Handle image generation for all command types"""
        try:
            workflow_name = workflow or self.workflow_manager.get_default_workflow(workflow_type)
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

            if workflow_config.get('type', 'txt2img') != workflow_type:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"Workflow '{workflow_name}' is not a {workflow_type} workflow!",
                        color=0xFF0000
                    )
                )
                return

            # Validate input image if required
            if workflow_type in ['img2img', 'upscale']:
                if not input_image:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="Image input is required for this workflow type!",
                            color=0xFF0000
                        )
                    )
                    return

                # Validate image format
                if not input_image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="Invalid image format. Supported formats: PNG, JPG, JPEG, WEBP",
                            color=0xFF0000
                        )
                    )
                    return

            # Create initial embed
            embed = discord.Embed(title="🔨 ImageSmith Forge", color=0x2F3136)
            queue_position = self.generation_queue.get_queue_position()
            status = f"⏳ Queued (Position: {queue_position + 1})" if queue_position > 0 else "Starting generation..."

            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Workflow", value=workflow_name, inline=True)
            if prompt:
                embed.add_field(name="Prompt", value=prompt, inline=False)
            if settings:
                embed.add_field(name="Settings", value=f"```{settings}```", inline=False)

            await interaction.response.send_message(embed=embed)
            message = await interaction.original_response()

            # Get image data if provided
            image_data = None
            if input_image:
                image_data = await input_image.read()

            async def run_generation():
                try:
                    workflow_json = self.workflow_manager.prepare_workflow(
                        workflow_name,
                        prompt,
                        settings,
                        image_data
                    )

                    # Generate image
                    result = await self.comfy_client.generate(workflow_json)
                    if 'error' in result:
                        raise Exception(result['error'])

                    prompt_id = result.get('prompt_id')
                    if not prompt_id:
                        raise Exception("No prompt ID received from ComfyUI")

                    async def update_message(status: str, image_file: Optional[discord.File] = None):
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

                    await self.comfy_client.listen_for_updates(prompt_id, update_message)

                except Exception as e:
                    error_embed = discord.Embed(title="🔨 ImageSmith Forge", color=0xFF0000)
                    error_embed.add_field(name="Status", value=f"❌ Error: {str(e)}", inline=False)
                    error_embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
                    error_embed.add_field(name="Workflow", value=workflow_name, inline=True)
                    await message.edit(embed=error_embed)

            await self.generation_queue.add_to_queue(run_generation)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=str(e),
                        color=0xFF0000
                    )
                )
            raise

    def workflows_command(self):
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
            workflows = self.workflow_manager.get_selectable_workflows(type)

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
