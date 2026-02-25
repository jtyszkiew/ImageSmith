![gif](./assets/imagesmith.gif)

# ImageSmith

[![Discord](https://img.shields.io/discord/1301892549568368651.svg?label=Discord)](https://discord.gg/9Ne74HPEue)
![Codecov](https://img.shields.io/codecov/c/github/jtyszkiew/ImageSmith)

> Forge your imagination into reality with ImageSmith - A powerful Discord bot that seamlessly integrates with ComfyUI
> for intuitive image, video, and audio generation.

> **Note**: ImageSmith is a workflow executor, not a workflow creator. You'll need to create your own workflows, but the
> bot makes them easily accessible through Discord's UI. Check out the example workflows in the repository to get
> started.

## Table of Contents

- [Quick Start](#quick-start)
- [User Guide](#user-guide)
- [Configuration](#configuration)
- [Security](#security)
- [Internationalization](#internationalization)
- [Extending](#extending)
- [Development](#development)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [Disclaimer](#disclaimer)
- [Community](#community)

## Quick Start

You need a running [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instance and a [Discord Bot Token](https://discord.com/developers/applications).

> **Important**: Default workflows use `sd_xl_base_1.0` for image generation and Mochi models for video generation.
> Ensure these are available in your ComfyUI instance.

### Docker

```bash
docker run -e DISCORD_TOKEN="<your_discord_token>" \
  # Optional: mount your own configuration file
  # --mount type=bind,source=./configuration.yml,target=/app/configuration.yml \
  # Optional: mount a custom workflows directory
  # -v "./custom_workflows:/app/custom_workflows" \
  ghcr.io/jtyszkiew/imagesmith:latest
```

### From Source

```bash
git clone https://github.com/jtyszkiew/ImageSmith.git
cd ImageSmith
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
cp configuration.example.yml configuration.yml
# Edit configuration.yml with your settings
python main.py
```

## User Guide

ImageSmith exposes slash commands for generating images, videos, and audio from text prompts or existing images. The output type depends on the ComfyUI workflow — the bot automatically detects whether the workflow produces images, video (gifs), or audio and sends the appropriate file to Discord.

Command names are configurable — see [Custom Command Names](#custom-command-names).

### Commands

| Command      | Description                | Parameters                                    |
|--------------|----------------------------|-----------------------------------------------|
| `/forge`     | Generate from text         | `prompt`, `[workflow]`, `[settings]`          |
| `/reforge`   | Transform existing image   | `image`, `prompt`, `[workflow]`, `[settings]` |
| `/upscale`   | Upscale with modifications | `image`, `prompt`, `[workflow]`, `[settings]` |
| `/workflows` | List available workflows   | -                                             |

### Example Usage

```
# Basic generation
/forge A majestic mountain landscape at sunset

# Using specific workflow
/forge A cyberpunk city --workflow cyberpunk_generator

# With custom settings
/forge A fantasy character --workflow character_generator --settings "change_steps(30);add_lora('fantasy_style', 0.8)"
```

## Configuration

All configuration lives in `configuration.yml`. Copy `configuration.example.yml` as a starting point.

### ComfyUI Connection

The `comfyui` block configures how the bot connects to one or more ComfyUI instances.

```yaml
comfyui:
  instances:
    - url: 'http://127.0.0.1:8188'
      weight: 1
    - url: 'https://comfyui-2.example.com:8188'
      weight: 2
      auth:
        username: admin
        password: secret
      timeout: 120
    - url: 'https://comfyui-3.example.com:8188'
      auth:
        api_key: your-api-key-here
        ssl_verify: true
        ssl_cert: /path/to/ca-bundle.pem
  input_dir: /path/to/comfyui/input
  show_node_updates: true
  load_balancer:
    strategy: LEAST_BUSY
```

#### Authentication

Each instance can have its own `auth` block. Authentication methods are checked in this order:

1. **API Key** — if `api_key` is set, sends a `Bearer` token header on both HTTP and WebSocket connections
2. **Basic Auth** — if `username` and `password` are set (and no `api_key`), sends a Basic auth header on HTTP connections

| Key          | Type   | Description                                       |
|--------------|--------|---------------------------------------------------|
| `api_key`    | string | Bearer token for API key authentication           |
| `username`   | string | Username for HTTP Basic authentication            |
| `password`   | string | Password for HTTP Basic authentication            |
| `ssl_verify` | bool   | Verify TLS certificates (default: `true`)         |
| `ssl_cert`   | string | Path to a custom CA bundle PEM file               |

### Workflows

Workflows map Discord commands to ComfyUI workflow JSON files. Each workflow is a named entry under the `workflows` key.

```yaml
workflows:
  forge:
    type: txt2img
    description: "Generate realistic images"
    workflow: "./workflows/txt2img.json"
    text_prompt_node_id: "6"
    text_prompt_input_key: "text"
    default: true
    selectable: true

  reforge:
    type: img2img
    description: "Regenerate images"
    workflow: "./workflows/img2img.json"
    text_prompt_node_id: "6"
    image_input_node_id: "10"
    default: true

  txt2vid:
    type: txt2img
    description: "Generate short video"
    workflow: "./workflows/txt2vid.json"
    text_prompt_node_id: "6"
```

| Key                      | Type   | Description                                                              |
|--------------------------|--------|--------------------------------------------------------------------------|
| `type`                   | string | `txt2img`, `img2img`, or `upscale`                                       |
| `description`            | string | Shown in the `/workflows` listing                                        |
| `workflow`               | string | Path to the ComfyUI workflow JSON file                                   |
| `text_prompt_node_id`    | string | Node ID in the workflow JSON to inject the text prompt into              |
| `text_prompt_input_key`  | string | Input field name within the prompt node (default: `"text"`)              |
| `image_input_node_id`    | string | Node ID to inject the uploaded image into (`img2img`/`upscale` types)    |
| `default`                | bool   | Global default for its type — the first match wins                       |
| `selectable`             | bool   | If `false`, hides from `/workflows` and the workflow dropdown (default: `true`) |

Video and audio workflows use `txt2img` as the type. The bot automatically detects the output format (image, gif/video, or audio) from what ComfyUI returns.

### Load Balancing

When multiple ComfyUI instances are configured, the bot distributes work across them.

```yaml
comfyui:
  load_balancer:
    strategy: LEAST_BUSY
```

| Strategy      | Description                                                                 |
|---------------|-----------------------------------------------------------------------------|
| `LEAST_BUSY`  | Picks the instance with the lowest ratio of active generations to weight (default) |
| `ROUND_ROBIN` | Cycles through connected instances in order                                 |
| `RANDOM`      | Picks a random instance, weighted by each instance's `weight` value         |

The `weight` field on each instance (default: `1`) affects both `RANDOM` (probability weight) and `LEAST_BUSY` (busyness denominator). A higher weight means the instance receives proportionally more work.

### Settings

Settings are Python functions that modify the workflow JSON before it is sent to ComfyUI. They are defined per-workflow.

Two special names are reserved:

- `__before` — runs automatically before any user-specified settings
- `__after` — runs automatically after all user-specified settings

```yaml
workflows:
  forge:
    settings:
      - name: __before
        description: "Default workflow configuration"
        code: |
          def __before(workflowjson):
              import random
              workflowjson["4"]["inputs"]["ckpt_name"] = "Juggernaut_X_RunDiffusion.safetensors"
              workflowjson["3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)

      - name: hd
        description: "HD resolution preset"
        code: |
          def hd(workflowjson):
              workflowjson["5"]["inputs"]["width"] = 1280
              workflowjson["5"]["inputs"]["height"] = 720
```

Users invoke settings in their command: `/forge A fantasy character --settings "hd()"`

Multiple settings can be chained with semicolons: `"hd();add_lora('fantasy_style', 0.8)"`

### Forms

Forms collect interactive input from users via Discord modals or select menus before a workflow runs.

```yaml
workflows:
  forge:
    form:
      - name: seed
        type: text
        required: false
        description: Seed for the model
        message: Provide a seed you would like to use
        on_submit: |
          def on_submit(workflowjson, value):
              workflowjson["65"]["inputs"]["seed"] = value
        on_default: |
          def on_default(workflowjson):
              import random
              workflowjson["65"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
```

#### Field Types

| Type         | Input method    | Value passed to `on_submit`                      |
|--------------|-----------------|--------------------------------------------------|
| `text`       | Modal text input | Integer (parsed from input)                     |
| `textarea`   | Modal text input (multi-line) | String (raw input)                 |
| `resolution` | Select dropdown  | List of two integers `[width, height]` (max 2048)|
| `select`     | Select dropdown (multi-select) | List of strings                  |

#### Field Configuration

| Key          | Type    | Description                                                             | Required |
|--------------|---------|-------------------------------------------------------------------------|----------|
| `name`       | string  | Name of the form field                                                  | Yes      |
| `type`       | string  | `text`, `textarea`, `resolution`, or `select`                           | Yes      |
| `required`   | bool    | Whether the field is required                                           | No       |
| `description`| string  | Displayed as the modal title or dropdown placeholder                    | No       |
| `message`    | string  | Displayed as the input label inside the modal                           | No       |
| `on_submit`  | string  | Python code executed when the form is submitted. Function name must be `on_submit`. | Yes |
| `on_default` | string  | Python code executed when a non-required field has no input. Function name must be `on_default`. | No |
| `options`    | list    | List of `{name, value}` objects for `select` and `resolution` types     | No       |

#### Select Example

```yaml
- name: style
  type: select
  required: true
  description: Choose art style
  message: Select one or more styles
  options:
    - name: Realistic
      value: realistic
    - name: Anime
      value: anime
    - name: Oil Painting
      value: oil_painting
  on_submit: |
    def on_submit(workflowjson, value):
        workflowjson["3"]["inputs"]["style"] = ", ".join(value)
```

#### Resolution Example

```yaml
- name: resolution
  type: resolution
  required: true
  description: Output resolution
  message: Select a resolution
  options:
    - name: 512x512
      value: 512x512
    - name: 1024x1024
      value: 1024x1024
    - name: 1280x720
      value: 1280x720
  on_submit: |
    def on_submit(workflowjson, value):
        workflowjson["5"]["inputs"]["width"] = value[0]
        workflowjson["5"]["inputs"]["height"] = value[1]
```

### Custom Command Names

Rename the default slash commands to whatever you prefer:

```yaml
commands:
  forge: "generate"
  reforge: "remix"
  upscale: "enhance"
  workflows: "list"
```

Any key omitted keeps its default name. For example, to only rename `/forge` to `/generate`:

```yaml
commands:
  forge: "generate"
```

### Display Settings

```yaml
comfyui:
  show_node_updates: false
```

When `show_node_updates` is set to `false`, per-node "Processing node X..." messages and progress bars are hidden. Completion, error, and media messages still appear normally. The default is `true`.

### Default Workflows per Channel or User

You can set a workflow as the default for specific channels or users. When a user runs a command without specifying a workflow, the bot checks (in order):

1. A workflow whose `default_for.users` list contains the user's name
2. A workflow whose `default_for.channels` list contains the channel's name
3. A workflow with `default: true` for that command type
4. The first workflow of the matching type

```yaml
workflows:
  anime_forge:
    type: txt2img
    description: "Anime-style generation"
    workflow: "./workflows/anime_txt2img.json"
    text_prompt_node_id: "6"
    default_for:
      channels:
        - anime-art
        - anime-general
      users:
        - anime_fan_123
```

## Security

### Workflow Access Control

Restrict who can use a workflow by adding a `security` block:

```yaml
workflows:
  forge:
    security:
      enabled: true
      allowed_roles:
        - "Artist"
        - "Admin"
      allowed_users:
        - "trusteduser"
      allowed_channels:
        - "image-generation"
```

| Key                | Type   | Description                                              |
|--------------------|--------|----------------------------------------------------------|
| `enabled`          | bool   | Enable access control for this workflow (default: `false`)|
| `allowed_roles`    | list   | Discord role names that can use this workflow             |
| `allowed_users`    | list   | Discord usernames that can use this workflow              |
| `allowed_channels` | list   | Channel names where this workflow can be used             |

When `enabled` is `true`, all three checks are ANDed together — the user must satisfy every non-empty list. If a list is empty or omitted, that check is skipped.

### Setting Access Control

Individual settings within a workflow can also have their own access control:

```yaml
workflows:
  forge:
    settings:
      - name: hd
        description: "HD resolution preset"
        security:
          enabled: true
          allowed_roles:
            - "Premium"
          allowed_users:
            - "admin_user"
        code: |
          def hd(workflowjson):
              workflowjson["5"]["inputs"]["width"] = 1280
              workflowjson["5"]["inputs"]["height"] = 720
```

The same `allowed_roles`, `allowed_users`, and `allowed_channels` keys are available at the setting level.

## Internationalization

ImageSmith includes built-in support for multiple languages. All UI strings — embeds, buttons, status messages, errors, forms, and security messages — are fully translatable.

### Supported Languages

| Code | Language          |
|------|-------------------|
| —    | English (default) |
| `de` | German            |
| `es` | Spanish           |
| `fr` | French            |
| `ja` | Japanese          |
| `pl` | Polish            |
| `pt` | Portuguese        |

### Configuration

```yaml
language: "pl"
```

You can also override individual string keys without creating a language file:

```yaml
i18n:
  embed:
    titles:
      error: "Custom Error Title"
  bot:
    starting_generation: "Generating your image..."
```

Strings are resolved in three layers (later layers override earlier):

1. `i18n.yml` — built-in English defaults
2. `i18n.<language>.yml` — language file (loaded when `language` is set)
3. `i18n` block in `configuration.yml` — inline overrides

See `i18n.yml` for the full list of available string keys.

Setting `env: "dev"` in your configuration causes raw error messages to be shown instead of generic error text. The default is `"prod"`.

## Extending

### Plugin Development

Plugins are Python classes that extend the bot's functionality. Place them in the `plugins/` directory — they are auto-discovered and loaded on startup.

```python
from src.core.plugin import Plugin


class MyPlugin(Plugin):
    async def on_load(self):
        await super().on_load()
        self.bot.hook_manager.register_hook('is.comfyui.client.before_create', self.my_hook)

    async def my_hook(self, workflow_json: dict, instances: list):
        return workflow_json
```

Every plugin receives `self.bot` — the `ImageSmith` instance — which provides access to:

- `bot.hook_manager` — register and fire hooks
- `bot.workflow_manager` — access workflows and configuration
- `bot.comfy_client` — the ComfyUI client
- `bot.form_manager` — register custom form field handlers

### Available Hooks

| Hook                                     | When it fires                          |
|------------------------------------------|----------------------------------------|
| `is.comfyui.client.before_create`        | Before the ComfyUI client is created   |
| `is.comfyui.client.after_create`         | After the client is created and connected |
| `is.comfyui.client.instance.timeout`     | When an idle instance times out        |
| `is.comfyui.client.instance.reconnect`   | Before attempting to reconnect an instance |
| `is.security.before`                     | Before the security check runs         |
| `is.security`                            | During the security check (return `SecurityResult` to allow/deny) |

## Development

### Testing

```bash
pip install pytest pytest-asyncio pytest-mock pytest-cov
pytest tests/ -v --cov=./
```

### Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/AmazingFeature`
3. Commit changes: `git commit -m 'Add AmazingFeature'`
4. Push to branch: `git push origin feature/AmazingFeature`
5. Open a Pull Request

## License

Licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - Image generation backend
- [discord.py](https://github.com/Rapptz/discord.py) - Discord integration

## Disclaimer

This bot is for educational and creative purposes. Users are responsible for ensuring their usage complies with
ComfyUI's and Discord's terms of service.

## Community

Join our [Discord server](https://discord.gg/9Ne74HPEue) to see the bot in action and stay updated with the latest
developments!
