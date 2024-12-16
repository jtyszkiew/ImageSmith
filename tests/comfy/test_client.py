import json
import ssl
import urllib

import aiohttp
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.comfy.client import ComfyUIClient, ComfyUIInstance, LoadBalanceStrategy, ComfyUIAuth


class MockAsyncContextManager:
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        if isinstance(self.return_value, Exception):
            raise self.return_value

        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPost:
    def __init__(self, response):
        self.response = response
        self.args = None
        self.kwargs = None

    def __call__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        return MockAsyncContextManager(self.response)


class TestComfyUIClient:
    @pytest.fixture
    def mock_response(self):
        response = AsyncMock()
        response.status = 200
        response.json.return_value = {'prompt_id': 'test_prompt'}
        response.read = AsyncMock(return_value=b"fake_image_data")
        return response

    @pytest.fixture
    def mock_session(self, mock_response):
        session = AsyncMock()
        session.post = MockPost(mock_response)
        session.get = MockPost(mock_response)
        return session

    @pytest.fixture
    def mock_instance(self, mock_session):
        instance = AsyncMock()
        instance.client_id = 'test_id'
        instance.connected = True
        instance.active_generations = 0
        instance._lock = asyncio.Lock()
        instance.base_url = 'http://localhost:8188'
        instance.get_session.return_value = mock_session
        return instance

    @pytest.fixture
    def mocked_client(self, mock_instance):
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])

        client.instances = [mock_instance]
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)

        return client

    @pytest.mark.asyncio
    async def test_generate(self, mocked_client, mock_instance):
        result = await mocked_client.generate({'test': 'workflow'})

        session = await mock_instance.get_session()
        assert result == {'prompt_id': 'test_prompt'}

        assert mocked_client.load_balancer.get_instance.call_count == 1
        assert mock_instance.active_generations == 0
        assert session.post.response.json.called

    @pytest.mark.asyncio
    async def test_generate_error(self, mocked_client, mock_instance, mock_session):
        # Create error response
        error_response = AsyncMock()
        error_response.status = 500
        error_response.text.return_value = "Server error"

        # Replace post with error response
        mock_session.post = MockPost(error_response)

        with pytest.raises(Exception) as exc_info:
            await mocked_client.generate({'test': 'workflow'})

        assert "Generation request failed" in str(exc_info.value)
        assert mock_instance.active_generations == 0

    @pytest.mark.asyncio
    async def test_generate_network_error(self, mocked_client, mock_instance, mock_session):
        # Make post raise an exception
        def raise_error(*args, **kwargs):
            raise Exception("Network error")

        mock_session.post = raise_error

        with pytest.raises(Exception) as exc_info:
            await mocked_client.generate({'test': 'workflow'})

        assert "Network error" in str(exc_info.value)
        assert mock_instance.active_generations == 0

    @pytest.mark.asyncio
    async def test_concurrent_generations(self, mocked_client, mock_instance):
        # Start multiple generations
        tasks = [
            mocked_client.generate({'test': f'workflow_{i}'})
            for i in range(3)
        ]

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Verify all completed successfully
        assert all(result.get('prompt_id') == 'test_prompt' for result in results)
        assert mock_instance.active_generations == 0

    @pytest.mark.asyncio
    async def test_instance_cleanup(self, mocked_client, mock_instance):
        # Test cleanup
        await mocked_client.close()
        assert mock_instance.cleanup.called

    @pytest.mark.asyncio
    async def test_custom_workflow(self, mocked_client, mock_instance):
        custom_workflow = {
            'nodes': {
                '1': {'inputs': {'text': 'test'}},
                '2': {'inputs': {'image': 'test.png'}}
            }
        }

        result = await mocked_client.generate(custom_workflow)
        assert result == {'prompt_id': 'test_prompt'}

    @pytest.mark.asyncio
    async def test_instance_state_recovery(self, mocked_client, mock_instance, mock_session):
        """Test that instance state is recovered after errors"""

        # Make the first call fail
        def fail_once(*args, **kwargs):
            raise Exception("First attempt fails")

        mock_session.post = fail_once

        # First call should fail
        with pytest.raises(Exception):
            await mocked_client.generate({'test': 'workflow'})

        assert mock_instance.active_generations == 0

        # Restore normal behavior
        mock_session.post = MockPost(AsyncMock(status=200, json=AsyncMock(return_value={'prompt_id': 'test_prompt'})))

        # Second call should succeed
        result = await mocked_client.generate({'test': 'workflow'})
        assert result == {'prompt_id': 'test_prompt'}
        assert mock_instance.active_generations == 0


    @pytest.mark.asyncio
    async def test_websocket_handling(self, mocked_client, mock_instance, mock_session):
        """Test WebSocket message handling"""
        mock_ws = AsyncMock()
        mock_instance.ws = mock_ws
        mock_instance.session = mock_session
        mock_instance.connected = True

        messages = [
            {'type': 'progress', 'data': {'prompt_id': 'test_prompt', 'node': 'test_node', 'value': 50, 'max': 100}},
            {'type': 'executing', 'data': {'prompt_id': 'test_prompt', 'node': 'test_node'}},
            {'type': 'executed',
             'data': {'prompt_id': 'test_prompt', 'output': {'images': [{'filename': 'test.png', 'type': 'output'}]}}},
            {'type': 'executing', 'data': {'prompt_id': 'test_prompt', 'node': None}}
        ]

        mock_ws.recv = AsyncMock(side_effect=[json.dumps(msg) for msg in messages])

        received_messages = []

        async def callback(status, image=None):
            received_messages.append((status, image))

        mocked_client.prompt_to_instance['test_prompt'] = mock_instance

        await mocked_client.listen_for_updates('test_prompt', callback)

        assert len(received_messages) > 0
        assert any('Processing node test_node' in msg[0] for msg in received_messages)
        assert any('Generation complete!' in msg[0] for msg in received_messages)

    @pytest.mark.asyncio
    async def test_image_url_handling(self, mocked_client):
        """Test image URL construction and handling"""
        instance = mocked_client.instances[0]

        test_cases = [
            {
                'input': {'filename': 'test.png', 'type': 'output'},
                'expected': f"{instance.base_url}/view?filename=test.png&type=output"
            },
            {
                'input': {'filename': 'test space.png', 'type': 'output'},
                'expected': f"{instance.base_url}/view?filename=test%20space.png&type=output"
            },
            {
                'input': {'filename': 'test.png', 'subfolder': 'outputs/test', 'type': 'output'},
                'expected': f"{instance.base_url}/view?filename=test.png&subfolder=outputs/test&type=output"
            }
        ]

        for case in test_cases:
            url = mocked_client._get_resource_url(instance, case['input'])
            parsed_url = urllib.parse.urlparse(url)
            parsed_expected = urllib.parse.urlparse(case['expected'])

            # Compare URL components separately
            assert parsed_url.scheme == parsed_expected.scheme
            assert parsed_url.netloc == parsed_expected.netloc
            assert parsed_url.path == parsed_expected.path

            # Compare query parameters
            actual_params = urllib.parse.parse_qs(parsed_url.query)
            expected_params = urllib.parse.parse_qs(parsed_expected.query)
            assert actual_params == expected_params

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, mocked_client, mock_instance, mock_session):
        """Test WebSocket error handling"""
        mock_ws = AsyncMock()
        mock_instance.ws = mock_ws
        mock_instance.session = mock_session
        mock_instance.connected = True

        error_message = json.dumps({
            'type': 'error',
            'data': {
                'prompt_id': 'test_prompt',
                'error': 'Processing failed'
            }
        })

        mock_ws.recv = AsyncMock(return_value=error_message)

        received_messages = []

        async def callback(status, image=None):
            received_messages.append(status)

        mocked_client.prompt_to_instance['test_prompt'] = mock_instance

        with pytest.raises(Exception) as exc_info:
            await mocked_client.listen_for_updates('test_prompt', callback)

        assert "Processing failed" in str(exc_info.value)
        assert any('Error' in msg for msg in received_messages)



class TestComfyUIClientImageUpload:
    @pytest.fixture
    def mock_response(self):
        response = AsyncMock()
        response.status = 200
        response.text = AsyncMock(return_value="Success")
        response.json = AsyncMock(return_value={'url': 'http://test.com/image.png'})
        return response

    @pytest.fixture
    def mock_session(self, mock_response):
        session = AsyncMock()
        session.post = MockPost(mock_response)
        session.get = MockPost(mock_response)
        return session

    @pytest.fixture
    def mock_instance(self, mock_session):
        instance = AsyncMock()
        instance.client_id = 'test_id'
        instance.connected = True
        instance._lock = asyncio.Lock()
        instance.base_url = 'http://localhost:8188'
        instance.get_session.return_value = mock_session
        return instance

    @pytest.mark.asyncio
    async def test_upload_image_success(self, mock_instance):
        """Test successful image upload"""
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)

        image_data = b"fake_image_data"
        result = await client.upload_image(image_data)

        # Verify result
        assert result == ({'url': 'http://test.com/image.png'}, mock_instance)

        # Verify session usage
        session = await mock_instance.get_session()
        assert session.post.args is not None

        # Verify mark_used was called
        mock_instance.mark_used.assert_called_once()

        # Verify request was made correctly
        expected_url = f"{mock_instance.base_url}/api/upload/image"
        assert session.post.args[0] == expected_url
        assert isinstance(session.post.kwargs['data'], aiohttp.FormData)

    @pytest.mark.asyncio
    async def test_upload_image_failure(self, mock_instance, mock_session):
        """Test failed image upload"""
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)

        # Create error response
        error_response = AsyncMock()
        error_response.status = 400
        error_response.text = AsyncMock(return_value="Bad request")
        mock_session.post = MockPost(error_response)

        image_data = b"fake_image_data"

        with pytest.raises(Exception) as exc_info:
            await client.upload_image(image_data)

        assert "Image upload failed with status 400" in str(exc_info.value)
        mock_instance.mark_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_image_network_error(self, mock_instance):
        """Test network error during image upload"""
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)

        # Create a session that raises an error on post
        error_session = AsyncMock()
        error = aiohttp.ClientError("Network error")
        error_session.post = MockPost(error)

        # Make sure get_session returns our error session
        mock_instance.get_session.return_value = error_session

        image_data = b"fake_image_data"

        with pytest.raises(aiohttp.ClientError) as exc_info:
            await client.upload_image(image_data)

        assert "Network error" in str(exc_info.value)
        mock_instance.mark_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_image_lock_usage(self, mock_instance):
        """Test that the lock is properly acquired and released during upload"""
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)

        # Create a proper mock for the lock
        mock_lock = AsyncMock()
        mock_instance.lock = mock_lock

        image_data = b"fake_image_data"
        await client.upload_image(image_data)

        # Verify lock was used correctly
        mock_lock.__aenter__.assert_called_once()
        mock_lock.__aexit__.assert_called_once()
