import asyncio

from logger import logger


class GenerationQueue:
    """Manages queued generation requests"""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.processing = False
        self.current_task = None

    async def add_to_queue(self, generation_func, *args, **kwargs):
        """Add a new generation request to the queue"""
        await self.queue.put((generation_func, args, kwargs))
        logger.info(f"Added new generation to queue. Queue size: {self.queue.qsize()}")

        if not self.processing:
            asyncio.create_task(self.process_queue())

    async def process_queue(self):
        """Process queued generation requests"""
        if self.processing:
            return

        self.processing = True
        try:
            while not self.queue.empty():
                generation_func, args, kwargs = await self.queue.get()
                logger.info(f"Processing generation from queue. Remaining: {self.queue.qsize()}")

                try:
                    self.current_task = asyncio.current_task()
                    await generation_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error processing generation: {e}")
                finally:
                    self.current_task = None
                    self.queue.task_done()

        finally:
            self.processing = False

    def is_processing(self) -> bool:
        """Check if currently processing a generation"""
        return self.processing

    def get_queue_position(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()
