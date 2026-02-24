import ssl

import pytest
from unittest.mock import AsyncMock, Mock, patch
import aiohttp
import websockets
from datetime import datetime, timedelta
import asyncio

from src.comfy.client import ComfyUIClient
from src.comfy.instance import ComfyUIInstance, ComfyUIAuth
from src.comfy.load_balancer import LoadBalancer, LoadBalanceStrategy


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session

@pytest.fixture
def mock_websocket():
    ws = AsyncMock(spec=websockets.WebSocketClientProtocol)
    return ws

@pytest.fixture
def instance():
    return ComfyUIInstance(base_url='http://localhost:8188')

@pytest.fixture
def mock_logger():
    return Mock()

@pytest.fixture
def mock_hook_manager():
    return AsyncMock()

class TestComfyUIInstance:
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_session, mock_websocket):
        instance = ComfyUIInstance('http://localhost:8188')

        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        async def mock_connect(*args, **kwargs):
            return mock_websocket

        mock_ws_connect = AsyncMock(side_effect=mock_connect)

        with patch('aiohttp.ClientSession', return_value=mock_session), \
                patch('websockets.connect', mock_ws_connect):  # Store the mock
            await instance.initialize()

        assert instance.connected is True
        assert instance.session == mock_session
        assert instance.ws == mock_websocket

        # Verify correct websocket connection URL
        mock_ws_connect.assert_called_once()
        call_args = mock_ws_connect.call_args
        assert call_args[0][0].startswith(f"{instance.ws_url}/ws?clientId=")
        assert 'origin' in call_args[1]
        assert call_args[1]['origin'] == instance.base_url

    @pytest.mark.asyncio
    async def test_initialize_with_auth(self, mock_session, mock_websocket):
        auth = ComfyUIAuth(
            username='test',
            password='pass',
            api_key='test-key',
            ssl_verify=False
        )
        instance = ComfyUIInstance('http://localhost:8188', auth=auth)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        async def mock_connect(*args, **kwargs):
            return mock_websocket

        mock_ws_connect = AsyncMock(side_effect=mock_connect)

        with patch('aiohttp.ClientSession', return_value=mock_session), \
                patch('websockets.connect', mock_ws_connect):
            await instance.initialize()

        # Verify API key was used in headers
        mock_ws_connect.assert_called_once()
        ws_kwargs = mock_ws_connect.call_args[1]
        assert ws_kwargs['extra_headers']['Authorization'] == 'Bearer test-key'

    @pytest.mark.asyncio
    async def test_initialize_auth_failure(self, mock_session, mock_logger):
        instance = ComfyUIInstance('http://localhost:8188')

        # Mock 401 response
        mock_response = AsyncMock()
        mock_response.status = 401
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_response
        mock_session.get.return_value = context_manager

        with patch('aiohttp.ClientSession', return_value=mock_session), \
                patch('logger.logger', mock_logger):
            with pytest.raises(Exception, match="Authentication failed"):
                await instance.initialize()

        assert instance.connected is False


    @pytest.mark.asyncio
    async def test_initialize_ssl_connection(self, mock_session, mock_websocket):
        auth = ComfyUIAuth(ssl_verify=False)
        instance = ComfyUIInstance('https://localhost:8188', auth=auth)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        async def mock_connect(*args, **kwargs):
            return mock_websocket

        mock_ws_connect = AsyncMock(side_effect=mock_connect)

        with patch('aiohttp.ClientSession', return_value=mock_session), \
                patch('websockets.connect', mock_ws_connect):
            await instance.initialize()

        mock_ws_connect.assert_called_once()
        ws_kwargs = mock_ws_connect.call_args[1]
        assert 'ssl' in ws_kwargs
        # When ssl_verify=False, code creates an SSLContext with verification disabled
        ssl_ctx = ws_kwargs['ssl']
        assert isinstance(ssl_ctx, ssl.SSLContext)
        assert ssl_ctx.check_hostname is False
        assert ssl_ctx.verify_mode == ssl.CERT_NONE

    @pytest.mark.asyncio
    async def test_cleanup(self, instance, mock_session, mock_websocket):
        instance.session = mock_session
        instance.ws = mock_websocket
        instance.connected = True

        await instance.cleanup()

        mock_session.close.assert_called_once()
        mock_websocket.close.assert_called_once()
        assert instance.session is None
        assert instance.ws is None
        assert instance.connected is False

    def test_is_timed_out(self, instance):
        # Test no timeout
        instance.timeout = 0
        assert instance.is_timed_out() is False

        # Test not timed out
        instance.timeout = 300
        instance.last_used = datetime.now()
        assert instance.is_timed_out() is False

        # Test timed out
        instance.last_used = datetime.now() - timedelta(seconds=301)
        assert instance.is_timed_out() is True

    @pytest.mark.asyncio
    async def test_mark_used(self, instance):
        old_time = instance.last_used
        await asyncio.sleep(0.1)  # Small delay
        await instance.mark_used()
        assert instance.last_used > old_time

    @pytest.mark.asyncio
    async def test_instance_auth(self):
        """Test instance authentication"""
        # Create instance with auth
        auth = ComfyUIAuth(
            username='test_user',
            password='test_pass',
            api_key='test_key',
            ssl_verify=True
        )

        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock session
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Create mock response for connection test
            mock_response = AsyncMock()
            mock_response.status = 200

            # Make session.get return a context manager
            class MockContextManager:
                async def __aenter__(self):
                    return mock_response

                async def __aexit__(self, *args):
                    pass

            mock_session.get.return_value = MockContextManager()

            # Create instance
            instance = ComfyUIInstance(
                base_url='http://localhost:8188',
                auth=auth
            )

            # Get session
            session = await instance.get_session()

            # Verify ClientSession was created with correct headers
            assert mock_session_class.called
            call_args = mock_session_class.call_args
            headers = call_args.kwargs.get('headers', {})

            # API key should take precedence
            assert 'Authorization' in headers
            assert headers['Authorization'] == 'Bearer test_key'

            # Test basic auth when no API key is present
            auth_no_key = ComfyUIAuth(
                username='test_user',
                password='test_pass',
                ssl_verify=True
            )

            instance_basic_auth = ComfyUIInstance(
                base_url='http://localhost:8188',
                auth=auth_no_key
            )

            # Reset mock
            mock_session_class.reset_mock()

            # Get new session
            session = await instance_basic_auth.get_session()

            # Verify basic auth headers
            call_args = mock_session_class.call_args
            headers = call_args.kwargs.get('headers', {})
            assert 'Authorization' in headers
            assert headers['Authorization'].startswith('Basic ')

            # Verify SSL settings
            connector = call_args.kwargs.get('connector')
            assert isinstance(connector, aiohttp.TCPConnector)
            assert connector._ssl == True

    @pytest.mark.asyncio
    async def test_instance_auth_none(self):
        """Test instance with no auth"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock session
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Create mock response
            mock_response = AsyncMock()
            mock_response.status = 200

            # Make session.get return a context manager
            class MockContextManager:
                async def __aenter__(self):
                    return mock_response

                async def __aexit__(self, *args):
                    pass

            mock_session.get.return_value = MockContextManager()

            # Create instance without auth
            instance = ComfyUIInstance(
                base_url='http://localhost:8188'
            )

            # Get session
            session = await instance.get_session()

            # Verify no auth headers were added
            call_args = mock_session_class.call_args
            headers = call_args.kwargs.get('headers', {})
            assert 'Authorization' not in headers

    @pytest.mark.asyncio
    async def test_instance_auth_ssl(self):
        """Test instance with different SSL configurations"""
        test_cases = [
            # Basic SSL verification
            {
                'auth': ComfyUIAuth(ssl_verify=True),
                'verify_ssl': True
            },
            # Disable SSL verification
            {
                'auth': ComfyUIAuth(ssl_verify=False),
                'verify_ssl': False
            },
            # With SSL context
            {
                'auth': ComfyUIAuth(
                    ssl_verify=True,
                    ssl_cert=ssl.create_default_context()
                ),
                'verify_ssl': True
            }
        ]

        for case in test_cases:
            with patch('aiohttp.ClientSession') as mock_session_class, \
                    patch('aiohttp.TCPConnector') as mock_connector_class:

                # Create mock connector
                mock_connector = Mock()
                mock_connector_class.return_value = mock_connector

                # Create mock session
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                # Create mock response
                mock_response = AsyncMock()
                mock_response.status = 200

                # Make session.get return a context manager
                class MockContextManager:
                    async def __aenter__(self):
                        return mock_response

                    async def __aexit__(self, *args):
                        pass

                mock_session.get.return_value = MockContextManager()

                # Create instance
                instance = ComfyUIInstance(
                    base_url='http://localhost:8188',
                    auth=case['auth']
                )

                # Get session
                session = await instance.get_session()

                # Verify connector was created with correct SSL settings
                connector_call = mock_connector_class.call_args
                ssl_param = connector_call.kwargs.get('ssl')

                if case['verify_ssl']:
                    # When ssl_verify is True, verify either True or SSLContext was passed
                    assert ssl_param is True or isinstance(ssl_param, ssl.SSLContext)
                else:
                    # When ssl_verify is False, verify False was passed
                    assert ssl_param is False

    @pytest.mark.asyncio
    async def test_instance_auth_with_cert_path(self):
        """Test instance with SSL certificate path"""
        # Create a mock SSL context
        mock_ssl_context = Mock(spec=ssl.SSLContext)

        with patch('ssl.create_default_context', return_value=mock_ssl_context) as mock_ssl, \
                patch('aiohttp.ClientSession') as mock_session_class, \
                patch('aiohttp.TCPConnector') as mock_connector_class:
            # Create mock connector
            mock_connector = Mock()
            mock_connector_class.return_value = mock_connector

            # Create mock session
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Create mock response
            mock_response = AsyncMock()
            mock_response.status = 200

            # Make session.get return a context manager
            class MockContextManager:
                async def __aenter__(self):
                    return mock_response

                async def __aexit__(self, *args):
                    pass

            mock_session.get.return_value = MockContextManager()

            # Create instance with cert path
            auth = ComfyUIAuth(
                ssl_verify=True,
                ssl_cert='path/to/cert.pem'
            )

            instance = ComfyUIInstance(
                base_url='http://localhost:8188',
                auth=auth
            )

            # Get session
            session = await instance.get_session()

            # Verify SSL context was created
            mock_ssl.assert_called_once()
            mock_ssl_context.load_verify_locations.assert_called_once_with('path/to/cert.pem')

            # Verify connector was created with SSL context
            connector_call = mock_connector_class.call_args
            assert connector_call.kwargs.get('ssl') == mock_ssl_context

    @pytest.mark.asyncio
    async def test_instance_no_ssl(self):
        """Test instance without SSL"""
        with patch('aiohttp.ClientSession') as mock_session_class, \
                patch('aiohttp.TCPConnector') as mock_connector_class:
            # Create mock connector
            mock_connector = Mock()
            mock_connector_class.return_value = mock_connector

            # Create instance without auth
            instance = ComfyUIInstance(
                base_url='http://localhost:8188'
            )

            # Get session
            session = await instance.get_session()

            # Verify connector was created with default SSL settings (True)
            connector_call = mock_connector_class.call_args
            assert connector_call.kwargs.get('ssl') is True
