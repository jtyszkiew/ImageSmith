import io
import ssl
import urllib

import discord
from typing import List, Optional, Dict
import aiohttp
import websockets
import uuid
import json
import asyncio
import urllib.parse
import base64
from enum import Enum
import random
from dataclasses import dataclass

from logger import logger


class LoadBalanceStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_BUSY = "least_busy"


@dataclass
class ComfyUIAuth:
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    ssl_verify: bool = True
    ssl_cert: Optional[str] = None


class ComfyUIInstance:
    def __init__(self,
                 base_url: str,
                 weight: int = 1,
                 auth: Optional[ComfyUIAuth] = None):
        self.base_url = base_url.rstrip('/')
        self.ws_url = self.base_url.replace('http', 'ws')
        self.weight = weight
        self.auth = auth
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.client_id = str(uuid.uuid4())
        self.active_generations = 0
        self.total_generations = 0
        self.last_used = 0
        self.connected = False
        self._lock = asyncio.Lock()
        self.active_prompts = set()  # Track active prompt IDs

    async def initialize(self):
        """Initialize instance connections"""
        try:
            session = await self.get_session()

            # Test connection to API
            async with session.get(f"{self.base_url}/history") as response:
                if response.status == 401:
                    raise Exception("Authentication failed")
                elif response.status != 200:
                    raise Exception(f"Failed to connect to ComfyUI API: {response.status}")

            # Connect to WebSocket with authentication if needed
            ws_headers = {}
            if self.auth and self.auth.api_key:
                ws_headers['Authorization'] = f'Bearer {self.auth.api_key}'

            # Determine WebSocket connection parameters
            ws_kwargs = {
                'extra_headers': ws_headers
            }

            # Only add SSL settings for secure WebSocket connections
            if self.ws_url.startswith('wss://'):
                ws_kwargs['ssl'] = self.auth.ssl_verify if self.auth else True

            self.ws = await websockets.connect(
                f"{self.ws_url}/ws?clientId={self.client_id}",
                **ws_kwargs
            )

            self.connected = True
            logger.info(f"Connected to ComfyUI instance at {self.base_url}")

        except Exception as e:
            self.connected = False
            await self.cleanup()
            raise logger.error(f"Failed to connect to ComfyUI instance {self.base_url}: {e}")

    async def cleanup(self):
        """Clean up instance connections"""
        async with self._lock:
            try:
                if self.ws:
                    await self.ws.close()
                    self.ws = None
                if self.session:
                    await self.session.close()
                    self.session = None
                self.connected = False
            except Exception as e:
                logger.error(f"Error during cleanup of instance {self.base_url}: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session with proper authentication"""
        if not self.session:
            headers = {}
            if self.auth:
                if self.auth.api_key:
                    headers['Authorization'] = f'Bearer {self.auth.api_key}'
                elif self.auth.username and self.auth.password:
                    auth_str = base64.b64encode(
                        f"{self.auth.username}:{self.auth.password}".encode()
                    ).decode()
                    headers['Authorization'] = f'Basic {auth_str}'

            ssl_context = None
            if self.auth:
                if isinstance(self.auth.ssl_cert, ssl.SSLContext):
                    ssl_context = self.auth.ssl_cert
                elif isinstance(self.auth.ssl_cert, str):
                    ssl_context = ssl.create_default_context()
                    ssl_context.load_verify_locations(self.auth.ssl_cert)

            self.session = aiohttp.ClientSession(
                headers=headers,
                connector=aiohttp.TCPConnector(
                    ssl=ssl_context if ssl_context else self.auth.ssl_verify if self.auth else True
                )
            )

        return self.session


class ComfyUIClient:
    """Load-balanced client for interacting with multiple ComfyUI instances"""

    def __init__(self, instances_config: List[Dict]):
        self.instances: List[ComfyUIInstance] = []
        self.strategy = LoadBalanceStrategy.LEAST_BUSY
        self.current_instance_index = 0
        self.prompt_to_instance = {}  # Map prompt IDs to instances

        # Initialize instances from config
        for instance_config in instances_config:
            auth = None
            if 'auth' in instance_config:
                auth = ComfyUIAuth(**instance_config['auth'])

            instance = ComfyUIInstance(
                base_url=instance_config['url'],
                weight=instance_config.get('weight', 1),
                auth=auth
            )
            self.instances.append(instance)

        if not self.instances:
            raise ValueError("No ComfyUI instances configured")

    async def connect(self):
        """Connect to all ComfyUI instances"""
        connect_tasks = [instance.initialize() for instance in self.instances]
        results = await asyncio.gather(*connect_tasks, return_exceptions=True)

        # Check if at least one instance connected successfully
        connected_instances = sum(1 for instance in self.instances if instance.connected)
        if connected_instances == 0:
            raise Exception("Failed to connect to any ComfyUI instance")

        logger.info(f"Connected to {connected_instances}/{len(self.instances)} ComfyUI instances")

    async def close(self):
        """Close connections to all instances"""
        if hasattr(self, 'instances'):
            cleanup_tasks = [instance.cleanup() for instance in self.instances]
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    def _select_instance_round_robin(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]

        if not connected_instances:
            raise Exception("No connected instances available")

        instance = connected_instances[self.current_instance_index % len(connected_instances)]
        self.current_instance_index += 1
        return instance

    def _select_instance_random(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]
        if not connected_instances:
            raise Exception("No connected instances available")

        weights = [instance.weight for instance in connected_instances]
        return random.choices(connected_instances, weights=weights, k=1)[0]

    def _select_instance_least_busy(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]

        if not connected_instances:
            raise Exception("No connected instances available")

        return min(connected_instances,
                   key=lambda i: i.active_generations / i.weight)

    async def _get_instance(self) -> ComfyUIInstance:
        strategies = {
            LoadBalanceStrategy.ROUND_ROBIN: self._select_instance_round_robin,
            LoadBalanceStrategy.RANDOM: self._select_instance_random,
            LoadBalanceStrategy.LEAST_BUSY: self._select_instance_least_busy
        }

        instance = strategies[self.strategy]()
        return instance

    async def generate(self, workflow: dict) -> dict:
        instance = await self._get_instance()

        async with instance._lock:
            try:
                instance.active_generations += 1

                prompt_data = {
                    'prompt': workflow,
                    'client_id': instance.client_id
                }

                session = await instance.get_session()
                async with session.post(
                        f"{instance.base_url}/prompt",
                        json=prompt_data
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Generation request failed with status {response.status}: {error_text}")

                    result = await response.json()
                    prompt_id = result.get('prompt_id')
                    if prompt_id:
                        instance.active_prompts.add(prompt_id)
                        self.prompt_to_instance[prompt_id] = instance
                    instance.total_generations += 1
                    return result

            finally:
                instance.active_generations -= 1

    async def _test_image_access(self, url: str) -> bool:
        """Test if an image URL is accessible"""
        if self.session is None:
            return False

        try:
            async with self.session.get(url) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Error testing image access: {e}")
            return False

    def _get_image_url(self, instance: ComfyUIInstance, image_data: dict) -> str:
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

    def _create_progress_bar(self, value: int, max_value: int, length: int = 10) -> str:
        """Create a text-based progress bar"""
        filled = int(length * (value / max_value))
        bar = '█' * filled + '░' * (length - filled)
        percentage = int(100 * (value / max_value))
        return f"[{bar}] {percentage}%"

    async def listen_for_updates(self, prompt_id: str, message_callback):
        """Listen for updates about a specific generation"""
        # Find instance handling this prompt
        instance = self.prompt_to_instance.get(prompt_id)
        if not instance or not instance.connected:
            raise Exception(f"No connected instance found for prompt {prompt_id}")

        current_image_data = None
        generation_complete = False
        node_progress = {}

        try:
            while not generation_complete:
                try:
                    message = await instance.ws.recv()
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
                        milestones = [25, 50, 75, 100]

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
                                    filename=f"forge_{prompt_id}.png"
                                )
                            await message_callback("✅ Generation complete!", image_file)

                    elif msg_type == 'executed':
                        node_output = msg_data.get('output')
                        if node_output and isinstance(node_output, dict) and 'images' in node_output:
                            for image_data in node_output['images']:
                                if isinstance(image_data, dict) and 'filename' in image_data:
                                    image_url = self._get_image_url(instance, image_data)
                                    if image_url:
                                        async with instance.session.get(image_url) as response:
                                            if response.status == 200:
                                                current_image_data = await response.read()
                                                image_file = discord.File(
                                                    io.BytesIO(current_image_data),
                                                    filename=f"forge_{prompt_id}.png"
                                                )
                                                await message_callback("🖼 New image generated!", image_file)

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
