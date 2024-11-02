import io
import json
import urllib
import uuid
from typing import Optional

import aiohttp
import discord
import websockets


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
                        if progress_percentage >= milestone and node_progress.get(node, {}).get('last_milestone',
                                                                                                0) < milestone:
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
