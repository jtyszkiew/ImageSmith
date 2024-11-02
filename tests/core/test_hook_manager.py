import pytest
from src.core.hook_manager import HookManager

class TestHookManager:
    @pytest.fixture
    def hook_manager(self):
        return HookManager()

    def test_hook_manager_init(self, hook_manager):
        assert isinstance(hook_manager.hooks, dict)
        assert len(hook_manager.hooks) == 0

    def test_register_hook(self, hook_manager):
        async def test_callback(): pass
        hook_manager.register_hook('test_hook', test_callback)
        assert 'test_hook' in hook_manager.hooks
        assert len(hook_manager.hooks['test_hook']) == 1
        assert hook_manager.hooks['test_hook'][0] == test_callback

    @pytest.mark.asyncio
    async def test_execute_hook(self, hook_manager):
        test_value = []

        async def test_callback(value):
            test_value.append(value)
            return value * 2

        hook_manager.register_hook('test_hook', test_callback)
        results = await hook_manager.execute_hook('test_hook', 5)

        assert len(results) == 1
        assert results[0] == 10
        assert test_value[0] == 5

    @pytest.mark.asyncio
    async def test_execute_nonexistent_hook(self, hook_manager):
        results = await hook_manager.execute_hook('nonexistent_hook')
        assert results == []
