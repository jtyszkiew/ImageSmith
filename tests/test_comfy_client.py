import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import aiohttp
import websockets
from imagesmith import ComfyUIClient

class AsyncContextManagerMock:
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockClientSession:
    """Mock for aiohttp.ClientSession"""
    def __init__(self, mock_response):
        self.mock_response = mock_response
        self.get = self._get
        self.post = self._post
        self.close = AsyncMock()

    def _get(self, url):
        return AsyncContextManagerMock(self.mock_response)

    def _post(self, url, **kwargs):
        return AsyncContextManagerMock(self.mock_response)

@pytest.mark.asyncio
async def test_comfyui_client_connect():
    """Test ComfyUI client connection"""
    # Create mock response
    mock_response = AsyncMock()
    mock_response.status = 200

    # Create mock session using our custom class
    mock_session = MockClientSession(mock_response)

    # Create mock websocket
    mock_ws = AsyncMock()

    # Create an async mock for websockets.connect that returns our mock_ws
    async def mock_connect(*args, **kwargs):
        return mock_ws

    with patch('aiohttp.ClientSession', return_value=mock_session), \
            patch('websockets.connect', mock_connect):

        # Test connection
        client = ComfyUIClient("http://localhost:8188")
        await client.connect()

        # Verify connection was successful
        assert client.session is not None
        assert client.ws is not None

@pytest.mark.asyncio
async def test_generate():
    """Test generation request"""
    # Create mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"prompt_id": "test_id"})

    # Create mock session
    mock_session = MockClientSession(mock_response)

    # Create mock websocket
    mock_ws = AsyncMock()
    mock_ws.recv = AsyncMock(return_value='{"status": "success"}')

    # Test generate
    client = ComfyUIClient("http://localhost:8188")
    client.session = mock_session
    client.ws = mock_ws

    result = await client.generate({"test": "workflow"})

    assert result["prompt_id"] == "test_id"

@pytest.mark.asyncio
async def test_listen_for_updates():
    """Test WebSocket updates"""
    # Create mock response for downloads
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"test_image_data")

    # Create mock session
    mock_session = MockClientSession(mock_response)

    # Create mock WebSocket with async recv function
    class MockWebSocket:
        def __init__(self):
            self.messages = [
                '{"type":"executing","data":{"node":"1","prompt_id":"test_id"}}',
                '{"type":"executed","data":{"output":{"images":[{"filename":"test.png"}]},"prompt_id":"test_id"}}',
                '{"type":"executing","data":{"node":null,"prompt_id":"test_id"}}'  # Final execution message
            ]
            self.message_index = 0

        async def recv(self):
            if self.message_index < len(self.messages):
                message = self.messages[self.message_index]
                self.message_index += 1
                return message
            raise websockets.ConnectionClosed(1000, "Mock connection closed")

        async def close(self):
            pass

    # Setup client
    client = ComfyUIClient("http://localhost:8188")
    client.session = mock_session
    client.ws = MockWebSocket()

    # Track callback calls
    callback_calls = []
    async def mock_callback(status, image=None):
        callback_calls.append((status, image))
        print(f"Callback received: {status}")  # Debug print

    try:
        # Test updates
        await client.listen_for_updates("test_id", mock_callback)
    except websockets.ConnectionClosed:
        # We expect this exception after all messages are processed
        pass

    # Verify we received the callbacks
    assert len(callback_calls) > 0
    # Check for execution messages
    assert any("Processing node 1" in status for status, _ in callback_calls), "Should receive node processing message"
    assert any("Generation complete" in status for status, _ in callback_calls), "Should receive completion message"

@pytest.mark.asyncio
async def test_connection_error():
    """Test connection error handling"""
    # Create failing response
    mock_response = AsyncMock()
    mock_response.status = 500

    # Create mock session
    mock_session = MockClientSession(mock_response)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        client = ComfyUIClient("http://localhost:8188")

        with pytest.raises(Exception) as exc_info:
            await client.connect()

        assert "Failed to connect to ComfyUI API" in str(exc_info.value)
