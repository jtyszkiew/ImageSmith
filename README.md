![gif](./assets/imagesmith.gif)

# ImageSmith 🔨

[![Discord](https://img.shields.io/discord/1301892549568368651.svg?label=Discord)](https://discord.gg/9Ne74HPEue)
![Codecov](https://img.shields.io/codecov/c/github/jtyszkiew/ImageSmith)

> Forge your imagination into reality with ImageSmith - A powerful Discord bot that seamlessly integrates with ComfyUI for intuitive image generation.

## ✨ Overview

ImageSmith is a Discord bot that brings the power of ComfyUI directly to your Discord server. With a user-friendly interface and powerful customization options, it allows users to generate images through simple commands while leveraging ComfyUI's advanced capabilities.

> **Note**: ImageSmith is a workflow executor, not a workflow creator. You'll need to create your own workflows, but the bot makes them easily accessible through Discord's UI. Check out the example workflows in the repository to get started.

## 🌟 Key Features

- 🔄 **Direct ComfyUI Integration** - Seamless connection with your ComfyUI instance
- 📊 **Queue Management** - Efficient handling of generation requests
- 🛠️ **Customizable Workflows** - Support for custom ComfyUI workflows
- 🔌 **Plugin System** - Extend functionality through plugins
- 📈 **Real-time Progress** - Live updates on generation status
- ⚙️ **Flexible Configuration** - Highly customizable settings
- 🪝 **Hook System** - Customize workflow behavior

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Running ComfyUI instance
- Discord Bot Token

### Installation Options

#### 🐳 Docker

**Basic Setup**
```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" ghcr.io/jtyszkiew/imagesmith:latest
```

**Custom Configuration**
```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" \
  --mount type=bind,source=./configuration.yml,target=/app/configuration.yml \
  ghcr.io/jtyszkiew/imagesmith:latest
```

**Custom Configuration & Workflows**
```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" \
  --mount type=bind,source=./configuration.yml,target=/app/configuration.yml \
  -v "./custom_workflows:/app/custom_workflows" \
  ghcr.io/jtyszkiew/imagesmith:latest
```

> **Important**: Default workflows use `sd_xl_base_1.0` for image generation and Mochi models for video generation. Ensure these are available in your ComfyUI instance.

#### 🔧 From Source

1. **Clone & Setup**
```bash
git clone https://github.com/jtyszkiew/ImageSmith.git
cd ImageSmith
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure**
```bash
cp configuration.example.yml configuration.yml
# Edit configuration.yml with your settings
```

3. **Run**
```bash
python main.py
```

## 💬 Usage Guide

### Available Commands

| Command | Description | Parameters |
|---------|-------------|------------|
| `/forge` | Generate image from text | `prompt`, `[workflow]`, `[settings]` |
| `/reforge` | Transform existing image | `image`, `prompt`, `[workflow]`, `[settings]` |
| `/upscale` | Upscale with modifications | `image`, `prompt`, `[workflow]`, `[settings]` |
| `/workflows` | List available workflows | - |

### Example Usage

```bash
# Basic generation
/forge A majestic mountain landscape at sunset

# Using specific workflow
/forge A cyberpunk city --workflow cyberpunk_generator

# With custom settings
/forge A fantasy character --workflow character_generator --settings "change_steps(30);add_lora('fantasy_style', 0.8)"
```

## ⚙️ Advanced Configuration

### Generic Settings

Two settings types: `__before` and `__after` are called before each workflow execution.

```yaml
- name: __before
  description: "Default workflow configuration"
  code: |
    def __before(workflowjson):
        import random
        workflowjson["4"]["inputs"]["ckpt_name"] = "Juggernaut_X_RunDiffusion.safetensors"
        workflowjson["3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
```

### Custom non-generic setting example

```yaml
- name: hd
  description: "HD resolution preset"
  code: |
    def hd(workflowjson):
        workflowjson["5"]["inputs"]["width"] = 1280
        workflowjson["5"]["inputs"]["height"] = 720
```

Usage: `/forge A fantasy character --settings "hd()"`

## 🔒 Security

Configure access control for workflows and settings:

```yaml
# Workflow security
workflows:
  forge:
    security:
      enabled: true
      allowed_roles: ["Smith"]
      allowed_users: ["Smith123"]
      
# Setting security
- name: hd
  security:
    enabled: true
    allowed_roles: ["Smith"]
    allowed_users: ["Smith123"]
  code: "..."
```

## 🔌 Plugin Development

Create custom plugins to extend functionality:

```python
from src.core.plugin import Plugin

class MyPlugin(Plugin):
    async def on_load(self):
        await super().on_load()
        self.bot.hook_manager.register_hook('is.comfyui.client.before_create', self.my_hook)
        
    async def my_hook(self, workflow_json: dict, instances: list):
        return workflow_json
```

### Available Hooks

- `is.comfyui.client.before_create`
- `is.comfyui.client.after_create`
- `is.security.before`
- `is.comfyui.client.instance.timeout`
- `is.comfyui.client.instance.reconnect`

## 🧪 Testing

```bash
pip install pytest pytest-asyncio pytest-mock pytest-cov
pytest tests/ -v --cov=./
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/AmazingFeature`
3. Commit changes: `git commit -m 'Add AmazingFeature'`
4. Push to branch: `git push origin feature/AmazingFeature`
5. Open a Pull Request

## 📄 License

Licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - Image generation backend
- [discord.py](https://github.com/Rapptz/discord.py) - Discord integration

## ⚠️ Disclaimer

This bot is for educational and creative purposes. Users are responsible for ensuring their usage complies with ComfyUI's and Discord's terms of service.

## 💬 Community

Join our [Discord server](https://discord.gg/9Ne74HPEue) to see the bot in action and stay updated with the latest developments!
