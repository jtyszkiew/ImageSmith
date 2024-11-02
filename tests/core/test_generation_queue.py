import pytest
from src.core.generation_queue import GenerationQueue

class TestGenerationQueue:
    @pytest.fixture
    def queue(self):
        return GenerationQueue()

    def test_queue_init(self, queue):
        assert queue.processing is False
        assert queue.current_task is None
        assert queue.get_queue_position() == 0

    @pytest.mark.asyncio
    async def test_add_to_queue(self, queue):
        async def test_generation(): pass

        await queue.add_to_queue(test_generation)
        assert queue.get_queue_position() == 1

    @pytest.mark.asyncio
    async def test_process_queue(self, queue):
        processed = []

        async def test_generation():
            processed.append(1)

        await queue.add_to_queue(test_generation)
        await queue.process_queue()

        assert len(processed) == 1
        assert queue.get_queue_position() == 0

    @pytest.mark.asyncio
    async def test_error_handling(self, queue):
        async def failing_generation():
            raise ValueError("Test error")

        await queue.add_to_queue(failing_generation)
        await queue.process_queue()

        assert queue.processing is False
        assert queue.get_queue_position() == 0
