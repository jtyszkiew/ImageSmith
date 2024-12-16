import asyncio

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.comfy.instance import ComfyUIInstance
from src.core.hook_manager import HookManager
from src.comfy.load_balancer import LoadBalancer, LoadBalanceStrategy

@pytest.fixture
def mock_instance():
    instance = AsyncMock(spec=ComfyUIInstance)
    instance.connected = True
    instance.active_generations = 0
    instance.weight = 1
    instance.is_timed_out.return_value = False
    instance.active_prompts = []
    instance.base_url = 'http://localhost:8188'
    return instance

@pytest.fixture
def mock_hook_manager():
    return AsyncMock(spec=HookManager)

@pytest.fixture
def load_balancer(mock_instance, mock_hook_manager):
    instances = [mock_instance]
    return LoadBalancer(instances, LoadBalanceStrategy.ROUND_ROBIN, mock_hook_manager)

class TestLoadBalancer:
    @pytest.mark.asyncio
    async def test_get_instance_calls_mark_used(self, load_balancer, mock_instance):
        instance = await load_balancer.get_instance()
        mock_instance.mark_used.assert_called_once()
        assert instance == mock_instance

    @pytest.mark.asyncio
    async def test_round_robin_strategy(self):
        instances = [
            AsyncMock(spec=ComfyUIInstance, connected=True, weight=1),
            AsyncMock(spec=ComfyUIInstance, connected=True, weight=1),
        ]
        balancer = LoadBalancer(instances, LoadBalanceStrategy.ROUND_ROBIN, AsyncMock(spec=HookManager))

        # First call should return first instance
        instance1 = balancer._select_instance_round_robin()
        assert instance1 == instances[0]

        # Second call should return second instance
        instance2 = balancer._select_instance_round_robin()
        assert instance2 == instances[1]

        # Third call should wrap around to first instance
        instance3 = balancer._select_instance_round_robin()
        assert instance3 == instances[0]

    @pytest.mark.asyncio
    async def test_least_busy_strategy(self):
        instances = [
            AsyncMock(spec=ComfyUIInstance, connected=True, active_generations=2, weight=1),
            AsyncMock(spec=ComfyUIInstance, connected=True, active_generations=1, weight=1),
            AsyncMock(spec=ComfyUIInstance, connected=True, active_generations=3, weight=1),
        ]
        balancer = LoadBalancer(instances, LoadBalanceStrategy.LEAST_BUSY, AsyncMock(spec=HookManager))

        instance = balancer._select_instance_least_busy()
        assert instance == instances[1]  # Should select instance with lowest active_generations

    @pytest.mark.asyncio
    async def test_random_strategy(self, mock_instance):
        instances = [
            AsyncMock(spec=ComfyUIInstance, connected=True, weight=1),
            AsyncMock(spec=ComfyUIInstance, connected=True, weight=2),
        ]
        balancer = LoadBalancer(instances, LoadBalanceStrategy.RANDOM, AsyncMock(spec=HookManager))

        with patch('random.choices') as mock_choices:
            mock_choices.return_value = [instances[0]]
            instance = balancer._select_instance_random()
            mock_choices.assert_called_once_with(instances, weights=[1, 2], k=1)
            assert instance == instances[0]

    @pytest.mark.asyncio
    async def test_no_connected_instances_raises_exception(self, mock_hook_manager):
        instance1 = AsyncMock(spec=ComfyUIInstance)
        instance2 = AsyncMock(spec=ComfyUIInstance)

        # Set up all necessary attributes for both instances
        for instance in [instance1, instance2]:
            instance.connected = False
            instance.client_id = f'test_id_{id(instance)}'
            instance.active_generations = 0
            instance._lock = asyncio.Lock()
            instance.weight = 1
            instance.active_prompts = []
            instance.base_url = 'http://localhost:8188'
            instance.is_timed_out.return_value = False

        instances = [instance1, instance2]
        balancer = LoadBalancer(instances, LoadBalanceStrategy.ROUND_ROBIN, mock_hook_manager)

        with pytest.raises(Exception, match="No available instances"):
            await balancer._select_instance()

    @pytest.mark.asyncio
    async def test_reconnection_attempt_when_no_instances_available(self, mock_hook_manager):
        instance = AsyncMock(spec=ComfyUIInstance)
        instance.connected = False
        instance.active_prompts = []
        instance.base_url = 'http://test:8188'

        balancer = LoadBalancer([instance], LoadBalanceStrategy.ROUND_ROBIN, mock_hook_manager)

        # First attempt will fail but trigger reconnection
        with pytest.raises(Exception, match="No available instances"):
            await balancer._select_instance()

        # Verify reconnection attempt
        mock_hook_manager.execute_hook.assert_called_once_with(
            'is.comfyui.client.instance.reconnect',
            'http://test:8188'
        )
        instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_timed_out_instances_are_filtered(self):
        instances = [
            AsyncMock(spec=ComfyUIInstance, connected=True, is_timed_out=lambda: True),
            AsyncMock(spec=ComfyUIInstance, connected=True, is_timed_out=lambda: False),
        ]
        balancer = LoadBalancer(instances, LoadBalanceStrategy.ROUND_ROBIN, AsyncMock(spec=HookManager))

        instance = await balancer._select_instance()
        assert instance == instances[1]  # Should select the non-timed-out instance
