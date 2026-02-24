import io
import struct
import urllib

import discord
from typing import List, Dict
import aiohttp
import websockets
import json
import asyncio
import urllib.parse
from PIL import Image

from logger import logger
from src.comfy.instance import ComfyUIInstance, ComfyUIAuth
from src.comfy.load_balancer import LoadBalanceStrategy, LoadBalancer


TRANSIENT_STATUS_CODES = {502, 503, 504}


class ComfyUIClient:
    def __init__(
            self,
            instances_config: List[Dict],
            hook_manager=None,
            load_balancer_strategy=LoadBalanceStrategy.LEAST_BUSY,
    ):
        self.instances: List[ComfyUIInstance] = []
        self.load_balancer = LoadBalancer(self.instances, load_balancer_strategy, hook_manager)
        self.current_instance_index = 0
        self.prompt_to_instance = {}
        self.hook_manager = hook_manager
        self.timeout_check_task = None
        self.timeout_check_interval = 5

        for instance_config in instances_config:
            auth = None
            if 'auth' in instance_config:
                auth = ComfyUIAuth(**instance_config['auth'])

            instance = ComfyUIInstance(
                base_url=instance_config['url'],
                weight=instance_config.get('weight', 1),
                auth=auth,
                timeout=instance_config.get('timeout', 900)
            )
            self.instances.append(instance)

        if not self.instances:
            raise ValueError("No ComfyUI instances configured")

    async def connect(self):
        """Connect to all ComfyUI instances"""
        connect_tasks = [instance.initialize() for instance in self.instances]
        results = await asyncio.gather(*connect_tasks, return_exceptions=True)

        connected_instances = sum(1 for instance in self.instances if instance.connected)
        if connected_instances == 0:
            raise Exception("Failed to connect to any ComfyUI instance")

        logger.info(f"Connected to {connected_instances}/{len(self.instances)} ComfyUI instances")

        # Start timeout checker
        self.timeout_check_task = asyncio.create_task(self._check_timeouts())

    async def close(self):
        """Close connections to all instances"""
        if self.timeout_check_task:
            self.timeout_check_task.cancel()
            try:
                await self.timeout_check_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, 'instances'):
            cleanup_tasks = [instance.cleanup() for instance in self.instances]
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def generate(self, workflow: dict, instance: ComfyUIInstance = None) -> dict:
        if not instance:
            instance = await self.load_balancer.get_instance()

        async with instance.lock:
            try:
                instance.active_generations += 1

                prompt_data = {
                    'prompt': workflow,
                    'client_id': instance.client_id
                }

                session = await instance.get_session()

                max_retries = 3
                retry_delay = 2

                for attempt in range(max_retries + 1):
                    async with session.post(
                            f"{instance.base_url}/prompt",
                            json=prompt_data
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            prompt_id = result.get('prompt_id')
                            if prompt_id:
                                instance.active_prompts.add(prompt_id)
                                self.prompt_to_instance[prompt_id] = instance
                            instance.total_generations += 1
                            return result

                        error_text = await response.text()
                        is_transient = (
                            response.status in TRANSIENT_STATUS_CODES
                            or (response.status == 404 and not error_text.strip())
                        )
                        if is_transient and attempt < max_retries:
                            logger.warning(f"Transient error (status {response.status}), retrying in {retry_delay * 2**attempt}s...")
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                            continue
                        raise Exception(f"Generation request failed with status {response.status}: {error_text}")

            finally:
                instance.active_generations -= 1

    async def upload_image(self, image_data: bytes) -> tuple[str, ComfyUIInstance]:
        instance = await self.load_balancer.get_instance()

        async with instance.lock:
            try:
                session = await instance.get_session()

                data = aiohttp.FormData()
                data.add_field('image', io.BytesIO(image_data))

                async with session.post(
                        f"{instance.base_url}/api/upload/image",
                        data=data,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Image upload failed with status {response.status}: {error_text}")

                    result = await response.json()
                    return result, instance

            finally:
                await instance.mark_used()


    async def listen_for_updates(self, prompt_id: str, message_callback):
        """Listen for updates about a specific generation"""
        # Find instance handling this prompt
        instance = self.prompt_to_instance.get(prompt_id)
        if not instance or not instance.connected:
            raise Exception(f"No connected instance found for prompt {prompt_id}")

        milestones = [25, 50, 75, 100]
        current_image_data = None
        current_image_filename = None
        latest_preview_image = None
        generation_complete = False
        node_progress = {}

        try:
            while not generation_complete:
                try:
                    message = await instance.ws.recv()
                    if isinstance(message, bytes):
                        if len(message) <= 8:
                            continue

                        event_type = struct.unpack('>I', message[:4])[0]
                        image_type = struct.unpack('>I', message[4:8])[0]
                        image_data = message[8:]

                        try:
                            with Image.open(io.BytesIO(image_data)) as img:
                                buffer = io.BytesIO()
                                img.save(buffer, format="JPEG")
                                buffer.seek(0)
                                latest_preview_image = discord.File(buffer, filename="preview.jpg")
                        except Exception as e:
                            logger.error(f"Failed to decode preview image: {e}")

                        continue

                    data = json.loads(message)

                    msg_type = data.get('type')
                    msg_data = data.get('data', {})

                    if msg_data.get('prompt_id') != prompt_id:
                        continue

                    # Handle different message types
                    if msg_type == 'progress':
                        # Progress message handling
                        node = msg_data.get('node')
                        value = msg_data.get('value', 0)
                        max_value = msg_data.get('max', 100)

                        progress_percentage = (value / max_value) * 100

                        if node_progress.get(node, {}).get('last_milestone') == 100 and progress_percentage < 100:
                            node_progress[node] = {'last_milestone': 0}

                        for milestone in milestones:
                            if progress_percentage >= milestone > node_progress.get(node, {}).get('last_milestone', 0):
                                node_progress[node] = {
                                    'value': value,
                                    'max': max_value,
                                    'last_milestone': milestone
                                }
                                progress_bar = self._create_progress_bar(value, max_value)
                                status = f"🔄 Processing node {node}...\n{progress_bar}"
                                if latest_preview_image and not latest_preview_image.fp.closed:
                                    await message_callback(status, latest_preview_image)
                                else:
                                    await message_callback(status, None)

                    elif msg_type == 'executing':
                        node_id = msg_data.get('node')
                        if node_id:
                            if node_id in node_progress:
                                del node_progress[node_id]
                            await message_callback(f"🔄 Processing node {node_id}...", None)
                        else:
                            generation_complete = True
                            if prompt_id in instance.active_prompts:
                                instance.active_prompts.remove(prompt_id)
                            if prompt_id in self.prompt_to_instance:
                                del self.prompt_to_instance[prompt_id]
                            image_file = None
                            if current_image_data:
                                image_file = discord.File(
                                    io.BytesIO(current_image_data),
                                    filename=current_image_filename,
                                )
                            await message_callback("✅ Generation complete!", image_file)

                    elif msg_type == 'executed':
                        node_output = msg_data.get('output')
                        if node_output and isinstance(node_output, dict) and 'images' in node_output:
                            for image_data in node_output['images']:
                                if isinstance(image_data, dict) and 'filename' in image_data:
                                    image_url = self._get_resource_url(instance, image_data)
                                    if image_url:
                                        async with instance.session.get(image_url) as response:
                                            if response.status == 200:
                                                current_image_data = await response.read()
                                                current_image_filename = image_data.get('filename')

                                                image_file = discord.File(
                                                    io.BytesIO(current_image_data),
                                                    filename=current_image_filename,
                                                )
                                                await message_callback("🖼 New image generated!", image_file)
                        if node_output and isinstance(node_output, dict) and 'gifs' in node_output:
                            for video_data in node_output['gifs']:
                                if isinstance(video_data, dict) and 'filename' in video_data:
                                    video_url = self._get_resource_url(instance, video_data)
                                    if video_url:
                                        async with instance.session.get(video_url) as response:
                                            if response.status == 200:
                                                current_image_data = await response.read()
                                                current_image_filename = video_data.get('filename')

                                                image_file = discord.File(
                                                    io.BytesIO(current_image_data),
                                                    filename=current_image_filename,
                                                )
                                                await message_callback("🎥 New video generated!", image_file)

                    elif msg_type == 'error':
                        error_msg = msg_data.get('error', 'Unknown error')
                        if prompt_id in instance.active_prompts:
                            instance.active_prompts.remove(prompt_id)
                        if prompt_id in self.prompt_to_instance:
                            del self.prompt_to_instance[prompt_id]

                        logger.error(f"ComfyUI Error: {error_msg}")

                        # We don't want to expose the error message to the user
                        await message_callback(f"❌ Error: ComfyUI Error, check logs for more information.")
                        raise Exception(f"ComfyUI Error: {error_msg}")

                except websockets.ConnectionClosed:
                    logger.error("WebSocket connection closed unexpectedly")
                    await message_callback("❌ Connection closed unexpectedly")
                    raise
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse WebSocket message: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error while listening for updates: {str(e)}")
                    await message_callback(f"❌ Error: {str(e)}")
                    raise

        finally:
            # Clean up tracking on any exit
            if prompt_id in instance.active_prompts:
                instance.active_prompts.remove(prompt_id)
            if prompt_id in self.prompt_to_instance:
                del self.prompt_to_instance[prompt_id]

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _create_progress_bar(self, value: int, max_value: int, length: int = 10) -> str:
        """Create a text-based progress bar"""
        filled = int(length * (value / max_value))
        bar = '█' * filled + '░' * (length - filled)
        percentage = int(100 * (value / max_value))
        return f"[{bar}] {percentage}%"

    async def _check_timeouts(self):
        """Periodically check for timed out instances"""
        while True:
            try:
                for instance in self.instances:
                    if instance.connected and instance.is_timed_out() and not instance.active_prompts:
                        logger.info(f"Instance {instance.base_url} timed out, cleaning up...")
                        await instance.cleanup()
                        if self.hook_manager:
                            await self.hook_manager.execute_hook('is.comfyui.client.instance.timeout',
                                                                 instance.base_url)
            except Exception as e:
                logger.error(f"Error in timeout checker: {e}")

            await asyncio.sleep(self.timeout_check_interval)

    def _get_resource_url(self, instance: ComfyUIInstance, image_data: dict) -> str:
        """Construct the image URL for a specific instance"""
        try:
            filename = image_data.get('filename')
            subfolder = image_data.get('subfolder', '')
            type_ = image_data.get('type', 'output')

            params = []
            if filename:
                params.append(f"filename={urllib.parse.quote(filename)}")
            if subfolder:
                params.append(f"subfolder={urllib.parse.quote(subfolder)}")
            if type_:
                params.append(f"type={urllib.parse.quote(type_)}")

            query_string = '&'.join(params)
            url = f"{instance.base_url}/view?{query_string}"
            logger.debug(f"Generated image URL: {url}")
            return url
        except Exception as e:
            logger.error(f"Error generating image URL: {e}")
            return None
