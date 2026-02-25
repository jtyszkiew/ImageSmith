from enum import Enum
import random
from logger import logger
from .instance import ComfyUIInstance
from ..core.hook_manager import HookManager


class LoadBalanceStrategy(Enum):
    ROUND_ROBIN = "ROUND_ROBIN"
    RANDOM = "RANDOM"
    LEAST_BUSY = "LEAST_BUSY"


class LoadBalancer:

    def __init__(
            self,
            instances: list[ComfyUIInstance],
            strategy: LoadBalanceStrategy,
            hook_manager: HookManager,
    ):
        self.instances = instances
        self.strategy = strategy
        self.current_instance_index = 0
        self.hook_manager = hook_manager

    def _select_instance_round_robin(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]

        if not connected_instances:
            raise Exception("No connected instances available")

        instance = connected_instances[self.current_instance_index % len(connected_instances)]
        self.current_instance_index += 1
        return instance

    def _select_instance_random(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]
        if not connected_instances:
            raise Exception("No connected instances available")

        weights = [instance.weight for instance in connected_instances]

        return random.choices(connected_instances, weights=weights, k=1)[0]

    def _select_instance_least_busy(self) -> ComfyUIInstance:
        connected_instances = [i for i in self.instances if i.connected]

        if not connected_instances:
            raise Exception("No connected instances available")

        return min(connected_instances,
                   key=lambda i: i.active_generations / i.weight)

    async def _select_instance(self, status_callback=None) -> ComfyUIInstance:
        strategies = {
            LoadBalanceStrategy.ROUND_ROBIN: self._select_instance_round_robin,
            LoadBalanceStrategy.RANDOM: self._select_instance_random,
            LoadBalanceStrategy.LEAST_BUSY: self._select_instance_least_busy
        }

        # Filter out disconnected or timed out instances
        available_instances = [i for i in self.instances if i.connected and not i.is_timed_out()]

        if not available_instances:
            for instance in self.instances:
                if not instance.connected and not instance.active_prompts:
                    logger.info(f"Attempting to reconnect to instance {instance.base_url}")
                    await self.hook_manager.execute_hook('is.comfyui.client.instance.reconnect', instance.base_url, status_callback=status_callback)
                    await instance.initialize()

            available_instances = [i for i in self.instances if i.connected]
            if not available_instances:
                raise Exception("No available instances")

        self.instances = available_instances
        return strategies[self.strategy]()

    async def get_instance(self, status_callback=None) -> ComfyUIInstance:
        instance = await self._select_instance(status_callback=status_callback)
        await instance.mark_used()
        return instance
