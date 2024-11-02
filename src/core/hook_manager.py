class HookManager:
    """Manages hooks for bot extensibility"""

    def __init__(self):
        self.hooks = {}

    def register_hook(self, hook_name: str, callback):
        """Register a new hook"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        self.hooks[hook_name].append(callback)

    async def execute_hook(self, hook_name: str, *args, **kwargs):
        """Execute all callbacks for a given hook"""
        if hook_name in self.hooks:
            results = []
            for callback in self.hooks[hook_name]:
                result = await callback(*args, **kwargs)
                results.append(result)
            return results
        return []
