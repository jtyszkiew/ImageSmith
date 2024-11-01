# ImageSmith 🔨

A Discord bot that integrates with ComfyUI to generate images through a user-friendly Discord interface. Forge your imagination into reality!

## 🌟 Features

- Direct integration with ComfyUI
- Queue-based generation system
- Customizable workflows
- Plugin system for extensibility
- Real-time generation progress updates
- Support for upscaling and img2img operations
- Configurable settings and parameters
- Hook system for workflow customization

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Running ComfyUI instance
- Discord Bot Token

### Installation

1. Clone the repository:
```bash
git clone https://github.com/jtyszkiew/ImageSmith.git
cd ImageSmith
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create configuration file:
```bash
cp configuration.example.yml configuration.yml
```

5. Edit `configuration.yml` with your settings:

Especially:
- `discord.token`: Your Discord Bot Token
- `comfyui.url`: Your ComfyUI instance URL
- `comfyui.input_dir`: ComfyUI input directory (here comfyui saves images for img2img operations)

When using example configuration don't forget to change model name in `workflowjson["4"]["inputs"]["ckpt_name"]`

```yaml
- name: __before
  description: Will change steps for this workflow to the number provided in parenthesis
  code: |
    def __before(workflowjson):
        import random

        workflowjson["4"]["inputs"]["ckpt_name"] = "Juggernaut_X_RunDiffusion.safetensors"
        workflowjson["3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
```

### Running the Bot

```bash
python imagesmith.py
```

## 💬 Usage

### Commands

- `/forge [prompt] [workflow] [settings]` - Generate an image
    - `prompt`: Description of the image you want to create
    - `workflow`: (Optional) Workflow to use
    - `settings`: (Optional) Additional settings

- `/workflows` - List available workflows

### Examples

Basic generation:
```
/forge A majestic mountain landscape at sunset
```

Using specific workflow:
```
/forge A cyberpunk city --workflow cyberpunk_generator
```

With settings:
```
/forge A fantasy character --workflow character_generator --settings "change_steps(30);add_lora('fantasy_style', 0.8)"
```

## ⚙️ Configuration

### Settings

Two special settings are available:
- `__before`: Applied before any custom settings
- `__after`: Applied after all custom settings

Example setting:
```yaml
- name: __before
  description: Will change steps for this workflow to the number provided in parenthesis
  code: |
    def __before(workflowjson):
        import random

        workflowjson["4"]["inputs"]["ckpt_name"] = "Juggernaut_X_RunDiffusion.safetensors"
        workflowjson["3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
```
Here we change the `seed` & `ckpt_name` before all generations.

## 🔌 Plugin System

### Creating a Plugin

```python
# plugins/my_plugin.py
from plugin import Plugin

class MyPlugin(Plugin):
    async def on_load(self):
        await super().on_load()
        self.bot.hook_manager.register_hook('pre_generate', self.my_hook)
        
    async def my_hook(self, workflow_json: dict, prompt: str):
        # Modify workflow or prompt
        return workflow_json
```

### Available Hooks

- `pre_generate`: Called before generation starts
- `generation_complete`: Called when generation finishes

## 🧪 Testing

Run tests:
```bash
pip install pytest pytest-asyncio pytest-mock pytest-cov
pytest tests/ -v --cov=./
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/AmazingFeature`
3. Commit your changes: `git commit -m 'Add AmazingFeature'`
4. Push to the branch: `git push origin feature/AmazingFeature`
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) for the amazing image generation backend
- [discord.py](https://github.com/Rapptz/discord.py) for the Discord integration

## ⚠️ Disclaimer

This bot is for educational and creative purposes. Users are responsible for ensuring their usage complies with ComfyUI's and Discord's terms of service.
