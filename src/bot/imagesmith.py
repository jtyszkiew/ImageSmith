import importlib
import inspect
import sys

from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from logger import logger
from .commands import forge_command, reforge_command, upscale_command, workflows_command
from ..comfy.workflow_manager import WorkflowManager
from ..core.hook_manager import HookManager
from ..core.generation_queue import GenerationQueue
from ..comfy.client import ComfyUIClient
from ..core.security import SecurityManager, BasicSecurity, SecurityResult


class ComfyUIBot(commands.Bot):
    def __init__(self,
                 configuration_path: str = 'configuration.yml',
                 plugins_path: str = 'plugins'):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(command_prefix='/', intents=intents)

        self.workflow_manager = WorkflowManager(configuration_path)
        self.security_manager = SecurityManager()
        self.hook_manager = HookManager()
        self.comfy_client = None
        self.plugins = []
        self.active_generations = {}
        self.generation_queue = GenerationQueue()
        self.plugins_path = plugins_path

        # This is temporary solution before rewriting the SecurityManager
        self.basic_security = BasicSecurity(self)

    async def setup_hook(self) -> None:
        """Setup hook that runs when the bot starts"""
        logger.info("Setting up bot...")
        await self.load_plugins()

        try:
            await self.hook_manager.execute_hook('is.comfyui.client.before_create',
                                                 self.workflow_manager.config['comfyui']['instances'])
            self.comfy_client = ComfyUIClient(self.workflow_manager.config['comfyui']['instances'], self.hook_manager)
            await self.hook_manager.execute_hook('is.comfyui.client.after_create',
                                                 self.workflow_manager.config['comfyui']['instances'])

            await self.comfy_client.connect()
            logger.info("Connected to ComfyUI")
        except Exception as e:
            logger.error(f"Failed to connect to ComfyUI: {e}")
            await self.cleanup()
            sys.exit(1)

        logger.info("Registering commands...")
        try:
            self.tree.add_command(forge_command(self))
            self.tree.add_command(reforge_command(self))
            self.tree.add_command(upscale_command(self))
            self.tree.add_command(workflows_command(self))

            commands = await self.tree.sync()
            logger.info(f"Registered {len(commands)} Discord commands:")
            for cmd in commands:
                logger.info(f"- /{cmd.name}")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            await self.cleanup()
            sys.exit(1)

    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guilds')

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

        logger.info("Invite link:")
        logger.info(invite_link)
        logger.info("Bot is ready!")

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")
        try:
            if self.comfy_client:
                await self.comfy_client.close()
            await self.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def load_plugins(self):
        """Load plugins from the plugins directory"""
        plugins_dir = Path(self.plugins_path)
        if not plugins_dir.exists():
            logger.warn("No plugins directory found")
            return

        import sys
        sys.path.append(str(Path.cwd()))

        plugin_files = [f for f in plugins_dir.glob("*.py") if f.name != "__init__.py"]

        for plugin_file in plugin_files:
            logger.info(f"Loading plugin: {plugin_file}")

            try:
                spec = importlib.util.spec_from_file_location(
                    plugin_file.stem,
                    plugin_file
                )
                if spec is None:
                    logger.warning(f"Failed to get spec for {plugin_file}")
                    continue

                module = importlib.util.module_from_spec(spec)
                if spec.loader is None:
                    logger.warning(f"Failed to get loader for {plugin_file}")
                    continue

                spec.loader.exec_module(module)
                logger.debug(f"Successfully loaded module: {module.__name__}")

                for item_name in dir(module):
                    if item_name.startswith('__'):
                        continue

                    try:
                        obj = getattr(module, item_name)

                        if inspect.isclass(obj):
                            try:
                                from ..core.plugin import Plugin
                                if issubclass(obj, Plugin):
                                    if obj != Plugin:
                                        try:
                                            plugin_instance = obj(self)
                                            logger.debug(f"Running on_load...")
                                            await plugin_instance.on_load()
                                            logger.debug(f"on_load completed")
                                            self.plugins.append(plugin_instance)
                                            logger.info(f"Successfully loaded and registered plugin: {obj.__name__}")
                                        except Exception as e:
                                            logger.error(f"Error instantiating plugin {obj.__name__}: {e}")
                                            import traceback
                                            traceback.print_exc()
                            except Exception as e:
                                logger.error(f"  - Error checking Plugin subclass: {e}")
                    except Exception as e:
                        logger.error(f"Error processing item {item_name}: {e}")

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file}: {e}")
                import traceback
                traceback.print_exc()

        logger.info(f"Loaded {len(self.plugins)} plugins:")
        for plugin in self.plugins:
            logger.info(f"- {plugin.__class__.__name__}")

    async def handle_generation(self,
                                interaction: discord.Interaction,
                                workflow_type: str,
                                prompt: str,
                                workflow: Optional[str] = None,
                                settings: Optional[str] = None,
                                input_image: Optional[discord.Attachment] = None):
        """Handle image generation for all command types"""
        try:
            workflow_name = workflow or self.workflow_manager.get_default_workflow(workflow_type,
                                                                                   channel_name=interaction.channel.name,
                                                                                   user_name=interaction.user.name)
            workflow_config = self.workflow_manager.get_workflow(workflow_name)

            await self.hook_manager.execute_hook('is.security.before', interaction, workflow_name, workflow_type,
                                                 prompt, workflow_config, settings)

            security_results: list[SecurityResult] = await self.hook_manager.execute_hook(
                'is.security',
                interaction, workflow_name, workflow_type, prompt, workflow_config, settings
            )

            for s_check in security_results:
                if not s_check.state:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description=s_check.message,
                            color=0xFF0000
                        )
                    )
                    return

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

                if not input_image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="Invalid image format. Supported formats: PNG, JPG, JPEG, WEBP",
                            color=0xFF0000
                        )
                    )
                    return

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

            image = None
            if input_image:
                image = await self.comfy_client.upload_image(await input_image.read())

            async def run_generation():
                try:
                    workflow_json = self.workflow_manager.prepare_workflow(
                        workflow_name,
                        prompt,
                        settings,
                        image
                    )

                    result = await self.comfy_client.generate(workflow_json)
                    if 'error' in result:
                        raise Exception(result['error'])

                    prompt_id = result.get('prompt_id')
                    if not prompt_id:
                        raise Exception("No prompt ID received from ComfyUI")

                    async def update_message(status: str, image_file: Optional[discord.File] = None):
                        new_embed = message.embeds[0].copy()

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
