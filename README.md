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
git clone https://github.com/yourusername/imagesmith.git
cd imagesmith
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
```yaml
discord:
  token: YOUR_DISCORD_TOKEN
comfyui:
  url: "http://localhost:8188"  # Your ComfyUI instance URL
default_workflow: avatar_generator
workflows:
  avatar_generator:
    description: "Generate Avatar"
    workflow: "./workflows/avatar_generator.json"
    text_prompt_node_id: 27
    selectable: true
    upscaler: avatar_upscaler
    settings:
      - name: __before
        description: "Default settings"
        code: |
          def __before(workflowjson):
              workflowjson["27"]["inputs"]["steps"] = 20
      - name: change_steps
        description: "Change steps"
        code: |
          def change_steps(workflowjson, value):
              workflowjson["27"]["inputs"]["steps"] = int(value)
```

### Running the Bot

```bash
python bot.py
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

### Workflows

Each workflow in `configuration.yml` can have:
- `description`: Workflow description
- `workflow`: Path to ComfyUI workflow JSON
- `text_prompt_node_id`: Node ID containing the prompt
- `selectable`: Whether visible in UI
- `upscaler`: Optional upscaler workflow
- `settings`: Custom settings functions

### Settings

Two special settings are available:
- `__before`: Applied before any custom settings
- `__after`: Applied after all custom settings

Example setting:
```yaml
settings:
  - name: change_steps
    description: "Change generation steps"
    code: |
      def change_steps(workflowjson, value):
          workflowjson["27"]["inputs"]["steps"] = int(value)
```

## 🔌 Plugin System

### Creating a Plugin

```python
# plugins/my_plugin.py
from plugin_base import Plugin

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

## 📦 Project Structure

```
imagesmith/
├── bot.py              # Main bot implementation
├── plugin_base.py      # Plugin base class
├── configuration.yml   # Bot configuration
├── plugins/           
│   ├── __init__.py
│   └── prompt_logger.py
├── workflows/          # ComfyUI workflow files
│   └── avatar_generator.json
└── tests/              # Test suite
    ├── __init__.py
    ├── conftest.py
    └── test_*.py
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
