import asyncio
import base64
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import websockets

from logger import logger


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
                 auth: Optional[ComfyUIAuth] = None,
                 timeout: int = 900):
        self.base_url = base_url.rstrip('/')
        self.ws_url = self.base_url.replace('http', 'ws')
        self.weight = weight
        self.auth = auth
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.client_id = str(uuid.uuid4())
        self.active_generations = 0
        self.total_generations = 0
        self.last_used = datetime.now()
        self.connected = False
        self.lock = asyncio.Lock()
        self.active_prompts = set()
        self.timeout = timeout
        self.timeout_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize instance connections"""
        try:
            session = await self.get_session()

            async with session.get(f"{self.base_url}/history") as response:
                if response.status == 401:
                    raise Exception(f"Authentication failed for ComfyUI instance {self.base_url}")
                elif response.status != 200:
                    raise Exception(f"Failed to connect to ComfyUI API: {response.status}")

            ws_headers = {}
            if self.auth and self.auth.api_key:
                ws_headers['Authorization'] = f'Bearer {self.auth.api_key}'

            ws_kwargs = {
                'origin': self.base_url,
                'extra_headers': ws_headers,
            }

            if self.ws_url.startswith('wss://'):
                if self.auth and not self.auth.ssl_verify:
                    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    ws_kwargs['ssl'] = ssl_context
                else:
                    ws_kwargs['ssl'] = True

            self.ws = await websockets.connect(
                f"{self.ws_url}/ws?clientId={self.client_id}",
                **ws_kwargs
            )

            self.connected = True
            logger.info(f"Connected to ComfyUI instance at {self.base_url}")

        except Exception as e:
            self.connected = False
            await self.cleanup()
            raise Exception(f"Failed to connect to ComfyUI instance {self.base_url}: {e}")

    async def mark_used(self):
        """Mark the instance as recently used"""
        self.last_used = datetime.now()

    def is_timed_out(self) -> bool:
        """Check if instance has timed out"""
        if self.timeout <= 0:
            return False
        time_since_last_use = datetime.now() - self.last_used
        return time_since_last_use > timedelta(seconds=self.timeout)

    async def cleanup(self):
        """Clean up instance connections"""
        async with self.lock:
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
