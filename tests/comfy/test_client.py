import json
import ssl
import urllib

import aiohttp
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.comfy.client import ComfyUIClient, ComfyUIInstance, LoadBalanceStrategy, ComfyUIAuth
from src.core.i18n import i18n


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
        assert any(i18n.get("client.progress.processing_node", node="test_node") in msg[0] for msg in received_messages)
        assert any(i18n.get("client.status.generation_complete") in msg[0] for msg in received_messages)

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



class MockPostSequence:
    """Returns different responses on successive calls."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return MockAsyncContextManager(resp)


class TestGenerateRetry:
    @pytest.fixture
    def success_response(self):
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={'prompt_id': 'test_prompt'})
        return response

    @pytest.fixture
    def mock_instance(self):
        instance = AsyncMock()
        instance.client_id = 'test_id'
        instance.connected = True
        instance.active_generations = 0
        instance._lock = asyncio.Lock()
        instance.base_url = 'http://localhost:8188'
        return instance

    @pytest.fixture
    def mocked_client(self, mock_instance):
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.instances = [mock_instance]
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)
        return client

    @pytest.mark.asyncio
    async def test_generate_retries_on_transient_404(self, mocked_client, mock_instance, success_response):
        """404 with empty body should be retried, then succeed on 200."""
        empty_404 = AsyncMock()
        empty_404.status = 404
        empty_404.text = AsyncMock(return_value="")

        session = AsyncMock()
        session.post = MockPostSequence([empty_404, success_response])
        mock_instance.get_session.return_value = session

        result = await mocked_client.generate({'test': 'workflow'})
        assert result == {'prompt_id': 'test_prompt'}
        assert session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_retries_on_502(self, mocked_client, mock_instance, success_response):
        """502 should be retried, then succeed on 200."""
        bad_gateway = AsyncMock()
        bad_gateway.status = 502
        bad_gateway.text = AsyncMock(return_value="Bad Gateway")

        session = AsyncMock()
        session.post = MockPostSequence([bad_gateway, success_response])
        mock_instance.get_session.return_value = session

        result = await mocked_client.generate({'test': 'workflow'})
        assert result == {'prompt_id': 'test_prompt'}
        assert session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_no_retry_on_404_with_body(self, mocked_client, mock_instance):
        """404 with a non-empty body is an application error — no retry."""
        not_found = AsyncMock()
        not_found.status = 404
        not_found.text = AsyncMock(return_value="Not Found: /prompt")

        session = AsyncMock()
        session.post = MockPostSequence([not_found])
        mock_instance.get_session.return_value = session

        with pytest.raises(Exception) as exc_info:
            await mocked_client.generate({'test': 'workflow'})

        assert "404" in str(exc_info.value)
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_no_retry_on_400(self, mocked_client, mock_instance):
        """400 is an application error — no retry."""
        bad_request = AsyncMock()
        bad_request.status = 400
        bad_request.text = AsyncMock(return_value="Bad Request")

        session = AsyncMock()
        session.post = MockPostSequence([bad_request])
        mock_instance.get_session.return_value = session

        with pytest.raises(Exception) as exc_info:
            await mocked_client.generate({'test': 'workflow'})

        assert "400" in str(exc_info.value)
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_exhausts_retries(self, mocked_client, mock_instance):
        """Always 404 empty body — should fail after max retries (4 attempts total)."""
        empty_404 = AsyncMock()
        empty_404.status = 404
        empty_404.text = AsyncMock(return_value="")

        session = AsyncMock()
        session.post = MockPostSequence([empty_404, empty_404, empty_404, empty_404])
        mock_instance.get_session.return_value = session

        with pytest.raises(Exception) as exc_info:
            await mocked_client.generate({'test': 'workflow'})

        assert "404" in str(exc_info.value)
        assert session.post.call_count == 4  # 1 initial + 3 retries


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


class TestCleanupPrompt:
    @pytest.fixture
    def client(self):
        return ComfyUIClient([{'url': 'http://localhost:8188'}])

    def test_cleanup_prompt(self, client):
        """Removes prompt from both tracking structures."""
        instance = Mock()
        instance.active_prompts = {'p1', 'p2'}
        client.prompt_to_instance['p1'] = instance

        client._cleanup_prompt('p1', instance)

        assert 'p1' not in instance.active_prompts
        assert 'p1' not in client.prompt_to_instance
        assert 'p2' in instance.active_prompts

    def test_cleanup_prompt_idempotent(self, client):
        """Safe to call when prompt already gone."""
        instance = Mock()
        instance.active_prompts = set()

        # Should not raise
        client._cleanup_prompt('nonexistent', instance)


class TestHandleBinaryPreview:
    @pytest.fixture
    def client(self):
        return ComfyUIClient([{'url': 'http://localhost:8188'}])

    def test_handle_binary_preview_valid_image(self, client):
        """Valid JPEG decoding returns discord.File."""
        from PIL import Image as PILImage
        import io as _io

        # Create a small valid image
        img = PILImage.new('RGB', (4, 4), color='red')
        buf = _io.BytesIO()
        img.save(buf, format='PNG')
        raw_png = buf.getvalue()

        # Prepend 8-byte header
        message = b'\x00' * 8 + raw_png

        result = client._handle_binary_preview(message)
        assert result is not None
        assert result.filename == 'preview.jpg'

    def test_handle_binary_preview_too_short(self, client):
        """Messages <= 8 bytes return None."""
        assert client._handle_binary_preview(b'\x00' * 8) is None
        assert client._handle_binary_preview(b'\x00' * 4) is None
        assert client._handle_binary_preview(b'') is None

    def test_handle_binary_preview_invalid_image(self, client):
        """Corrupted data returns None."""
        message = b'\x00' * 8 + b'this is not an image'
        result = client._handle_binary_preview(message)
        assert result is None


class TestDownloadMedia:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_instance(self, mock_session):
        instance = AsyncMock()
        instance.base_url = 'http://localhost:8188'
        instance.session = mock_session
        return instance

    @pytest.fixture
    def client(self):
        return ComfyUIClient([{'url': 'http://localhost:8188'}])

    @pytest.mark.asyncio
    async def test_download_media_success(self, client, mock_instance, mock_session):
        """Successful download returns (bytes, filename)."""
        response = AsyncMock()
        response.status = 200
        response.read = AsyncMock(return_value=b'media_bytes')
        mock_session.get = MockPost(response)

        result = await client._download_media(
            mock_instance,
            {'filename': 'output.png', 'type': 'output'},
        )

        assert result is not None
        assert result == (b'media_bytes', 'output.png')

    @pytest.mark.asyncio
    async def test_download_media_missing_filename(self, client, mock_instance):
        """Missing filename returns None."""
        result = await client._download_media(mock_instance, {'type': 'output'})
        assert result is None

    @pytest.mark.asyncio
    async def test_download_media_non_dict(self, client, mock_instance):
        """Non-dict input returns None."""
        result = await client._download_media(mock_instance, "not_a_dict")
        assert result is None


class TestShowNodeUpdates:
    @pytest.fixture
    def client_with_updates(self):
        return ComfyUIClient([{'url': 'http://localhost:8188'}], show_node_updates=True)

    @pytest.fixture
    def client_without_updates(self):
        return ComfyUIClient([{'url': 'http://localhost:8188'}], show_node_updates=False)

    def test_node_updates_enabled_by_default(self):
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        assert client.show_node_updates is True

    @pytest.mark.asyncio
    async def test_node_updates_disabled_skips_progress(self, client_without_updates):
        """With show_node_updates=False, _handle_progress does not call the callback."""
        callback = AsyncMock()
        node_progress = {}
        msg_data = {'node': 'node_1', 'value': 50, 'max': 100}

        await client_without_updates._handle_progress(
            msg_data, node_progress, [25, 50, 75, 100], None, callback,
        )

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_node_updates_disabled_sends_single_in_progress(self, client_without_updates):
        """With show_node_updates=False, _handle_executing sends a single 'in progress' message on first node."""
        callback = AsyncMock()
        instance = Mock()
        instance.active_prompts = {'p1'}
        node_progress = {}

        # First node: should send the in-progress message
        complete, notified = await client_without_updates._handle_executing(
            {'node': 'node_1'}, node_progress, callback,
            'p1', instance, None, None, False,
        )

        assert complete is False
        assert notified is True
        callback.assert_called_once()
        assert i18n.get("client.status.generation_in_progress") in callback.call_args[0][0]

        # Second node: should NOT send again
        callback.reset_mock()
        complete, notified = await client_without_updates._handle_executing(
            {'node': 'node_2'}, node_progress, callback,
            'p1', instance, None, None, True,
        )

        assert complete is False
        assert notified is True
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_node_updates_disabled_still_shows_completion(self, client_without_updates):
        """With show_node_updates=False, the completion message (node=None) is still sent."""
        callback = AsyncMock()
        instance = Mock()
        instance.active_prompts = {'p1'}
        client_without_updates.prompt_to_instance['p1'] = instance

        complete, notified = await client_without_updates._handle_executing(
            {'node': None}, {}, callback,
            'p1', instance, None, None,
        )

        assert complete is True
        callback.assert_called_once()
        assert i18n.get("client.status.generation_complete") in callback.call_args[0][0]

    @pytest.mark.asyncio
    async def test_node_updates_enabled_sends_all(self, client_with_updates):
        """With show_node_updates=True, both progress and executing callbacks fire."""
        callback = AsyncMock()

        # Test progress callback fires (50% hits both 25 and 50 milestones)
        node_progress = {}
        msg_data = {'node': 'node_1', 'value': 50, 'max': 100}
        await client_with_updates._handle_progress(
            msg_data, node_progress, [25, 50, 75, 100], None, callback,
        )
        assert callback.call_count >= 1

        # Test executing callback fires
        callback.reset_mock()
        instance = Mock()
        instance.active_prompts = {'p1'}
        complete, notified = await client_with_updates._handle_executing(
            {'node': 'node_1'}, {}, callback,
            'p1', instance, None, None,
        )
        assert complete is False
        callback.assert_called_once()


class TestWebSocketMediaHandling:
    @pytest.fixture
    def mock_response(self):
        response = AsyncMock()
        response.status = 200
        response.json.return_value = {'prompt_id': 'test_prompt'}
        response.read = AsyncMock(return_value=b"fake_media_data")
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
        instance.session = mock_session
        return instance

    @pytest.fixture
    def mocked_client(self, mock_instance):
        client = ComfyUIClient([{'url': 'http://localhost:8188'}])
        client.instances = [mock_instance]
        client.load_balancer = Mock()
        client.load_balancer.get_instance = AsyncMock(return_value=mock_instance)
        return client

    @pytest.mark.asyncio
    async def test_websocket_audio_handling(self, mocked_client, mock_instance):
        """End-to-end: audio outputs trigger 'New audio generated!' callback."""
        mock_ws = AsyncMock()
        mock_instance.ws = mock_ws

        messages = [
            {'type': 'executed', 'data': {
                'prompt_id': 'test_prompt',
                'output': {'audio': [{'filename': 'output.wav', 'type': 'output'}]},
            }},
            {'type': 'executing', 'data': {'prompt_id': 'test_prompt', 'node': None}},
        ]
        mock_ws.recv = AsyncMock(side_effect=[json.dumps(msg) for msg in messages])

        received = []
        async def callback(status, image=None):
            received.append((status, image))

        mocked_client.prompt_to_instance['test_prompt'] = mock_instance
        await mocked_client.listen_for_updates('test_prompt', callback)

        assert any(i18n.get("client.media.audio_generated") in msg[0] for msg in received)
        assert any(i18n.get("client.status.generation_complete") in msg[0] for msg in received)

    @pytest.mark.asyncio
    async def test_websocket_video_handling(self, mocked_client, mock_instance):
        """End-to-end: gif outputs trigger 'New video generated!' callback."""
        mock_ws = AsyncMock()
        mock_instance.ws = mock_ws

        messages = [
            {'type': 'executed', 'data': {
                'prompt_id': 'test_prompt',
                'output': {'gifs': [{'filename': 'output.mp4', 'type': 'output'}]},
            }},
            {'type': 'executing', 'data': {'prompt_id': 'test_prompt', 'node': None}},
        ]
        mock_ws.recv = AsyncMock(side_effect=[json.dumps(msg) for msg in messages])

        received = []
        async def callback(status, image=None):
            received.append((status, image))

        mocked_client.prompt_to_instance['test_prompt'] = mock_instance
        await mocked_client.listen_for_updates('test_prompt', callback)

        assert any(i18n.get("client.media.video_generated") in msg[0] for msg in received)
        assert any(i18n.get("client.status.generation_complete") in msg[0] for msg in received)

    @pytest.mark.asyncio
    async def test_websocket_mixed_media(self, mocked_client, mock_instance):
        """Node with both images and audio triggers both callbacks."""
        mock_ws = AsyncMock()
        mock_instance.ws = mock_ws

        messages = [
            {'type': 'executed', 'data': {
                'prompt_id': 'test_prompt',
                'output': {
                    'images': [{'filename': 'img.png', 'type': 'output'}],
                    'audio': [{'filename': 'audio.wav', 'type': 'output'}],
                },
            }},
            {'type': 'executing', 'data': {'prompt_id': 'test_prompt', 'node': None}},
        ]
        mock_ws.recv = AsyncMock(side_effect=[json.dumps(msg) for msg in messages])

        received = []
        async def callback(status, image=None):
            received.append((status, image))

        mocked_client.prompt_to_instance['test_prompt'] = mock_instance
        await mocked_client.listen_for_updates('test_prompt', callback)

        statuses = [msg[0] for msg in received]
        assert any(i18n.get("client.media.image_generated") in s for s in statuses)
        assert any(i18n.get("client.media.audio_generated") in s for s in statuses)
        assert any(i18n.get("client.status.generation_complete") in s for s in statuses)
