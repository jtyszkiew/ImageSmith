# ImageSmith 🔨
[![Discord](https://img.shields.io/discord/1301892549568368651.svg?label=Discord)](https://discord.gg/9Ne74HPEue)
![Codecov](https://img.shields.io/codecov/c/github/jtyszkiew/ImageSmith)

A Discord bot that integrates with ComfyUI to generate images through a user-friendly Discord interface. Forge your imagination into reality!

### Discord
You can join my Discord channel on which I'm testing updates on the bot. You won't be able to use the bot there (since it's my private instance) but you can see the possible options

### What's ImageSmith not?
Magical bot that will create workflows for you. You need to create them yourself, bot only allows you to use them through Discord UI. There are some example workflows in the repository but these are the most basic ones.

## 🌟 Features

- Direct integration with ComfyUI
- Queue-based generation system
- Customizable workflows
- Plugin system for extensibility
- Real-time generation progress updates
- Configurable settings and parameters
- Hook system for workflow customization

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Running ComfyUI instance
- Discord Bot Token

## Installation

### From source
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
- `comfyui.instances[0].url`: Your ComfyUI instance URL
- `comfyui.input_dir`: ComfyUI input directory (here comfyui saves images for img2img operations)

When using example configuration don't forget to change model name in 
```
workflowjson["4"]["inputs"]["ckpt_name"]
```

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
python main.py
```
## Docker

### Basic run
For basic run you need to only set the `DISCORD_TOKEN` environment variable.

> [!IMPORTANT]  
> Default [`forge`, `reforge`, `upscale`] workflows are using `sd_xl_base_1.0` ([Model on HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors)) 
> 
> Default [`txt2vid`] workflow is using Mochi models from [this manual](https://blog.comfy.org/mochi-1/)
> 
> You need to have these models in your ComfyUI instance if you want to test the bot with default workflows without any changes.

```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" ghcr.io/jtyszkiew/imagesmith:latest
```

### Custom configuration
If you want to change the `configuration.yml` file (and you want to change it for sure in scenarios other than "basic run")
```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" --mount type=bind,source=./configuration.yml,target=/app/configuration.yml ghcr.io/jtyszkiew/imagesmith:latest
```

### Custom configuration and custom workflows
If you want changed `configuration.yml` and custom workflows that will be placed in `/app/custom_workflows` directory inside container.

> [!IMPORTANT]  
> Remember that you should use the docker container paths in `configuration.yml` file. Either start your `workflow` configuration section from `/app/custom_workflows` or `./custom_workflows`.

```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" --mount type=bind,source=./configuration.yml,target=/app/configuration.yml -v "./custom_workflows:/app/custom_workflows" ghcr.io/jtyszkiew/imagesmith:latest
```

## 💬 Usage

### Commands

- `/forge [prompt] [workflow] [settings]` - txt2img
    - `prompt`: Description of the image you want to create
    - `workflow`: (Optional) Workflow to use
    - `settings`: (Optional) Additional settings


- `/reforge [image] [prompt] [workflow] [settings]` - img2img
  - `image`: Image to use as a reference
  - `prompt`: Description of the image you want to create
  - `workflow`: (Optional) Workflow to use
  - `settings`: (Optional) Additional settings


- `/upscale [image] [prompt] [workflow] [settings]` - similar to img2img but with upscaling
  - `image`: Image to use as a reference
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

## Defining custom setting
Custom settings are designed to help you modify the workflows before executing it in ComfyUI. Why? For my it's often a case when I want to change some smaller setting on
the fly for one generation - for example number of steps, seed or the image orientation.

Example setting:
```yaml
- name: hd
  description: Will change resolution for this workflow to hd
  code: |
    def hd(workflowjson):
        workflowjson["5"]["inputs"]["width"] = 1280
        workflowjson["5"]["inputs"]["height"] = 720
```
This setting will change the resolution of the image to 1280x720.

Usage: `/forge A fantasy character --settings "hd()"`

```yaml
- name: portrait
  description: Will change resolution for this workflow to portrait
  code: |
    def portrait(workflowjson):
        width = workflowjson["5"]["inputs"]["width"]
        height = workflowjson["5"]["inputs"]["height"]

        print(width, height)

        workflowjson["5"]["inputs"]["width"] = width if width < height else height
        workflowjson["5"]["inputs"]["height"] = width if width > height else height
```

This setting will change the resolution of the image to portrait.

Usage: `/forge A fantasy character --settings "portrait()"`

## Combining multiple settings
You can combine multiple settings in one command. Just separate them with a semicolon.

Usage: `/forge A fantasy character --settings "hd();portrait()"`

## 🔌 Plugin System

### Creating a Plugin

```python
from src.core.plugin import Plugin

class MyPlugin(Plugin):
    async def on_load(self):
        await super().on_load()
        self.bot.hook_manager.register_hook('pre_generate', self.my_hook)
        
    async def my_hook(self, workflow_json: dict, prompt: str):
        # Modify workflow or prompt
        return workflow_json
```

### Available Hooks

- `is.comfyui.client.before_create`: Called before ComfyUI client creation
- `is.comfyui.client.after_create`: Called after ComfyUI client creation
- `is.security.before`: Called just before the security module is checking permissions
- `is.comfyui.client.instance.timeout`: Called when one of instances goes timeout (can be set by param `timeout` in configuration)
- `is.comfyui.client.instance.reconnect`: Reconnect is called before generation if instance is disconnected (timeout)

Hooks & Plugins are work in progress and will be expanded in the future.

## Security

Currently, the bot is using a simple security system. You can define a list of users and roles that are allowed to use workflows and settings:

### Security for Setting
```yaml
- name: hd
  description: Will change resolution for this workflow to hd
  security:
    enabled: true
    allowed_roles:
      - "Smith"
    allowed_users:
      - "Smith123"
  code: "..."
```

### Security for Workflow
```yaml
workflows:
  forge:
    security:
      enabled: true
      allowed_roles:
        - "Smith"
      allowed_users:
        - "Smith123"
```

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
