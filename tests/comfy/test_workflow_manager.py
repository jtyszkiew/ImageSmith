from unittest.mock import patch

import pytest
import json
from src.comfy.workflow_manager import WorkflowManager

class TestWorkflowManager:
    @pytest.fixture
    def sample_workflow_json(self, tmp_path):
        workflow_data = {
            "6": {"inputs": {"text": "default prompt"}},
            "4": {"inputs": {"ckpt_name": "default_model.safetensors"}},
            "3": {"inputs": {"seed": 123456}},
            "5": {"inputs": {"width": 512, "height": 512}}
        }
        workflow_file = tmp_path / ".json"
        workflow_file.write_text(json.dumps(workflow_data))
        return workflow_file

    @pytest.fixture
    def config_yaml(self, tmp_path, sample_workflow_json):
        config_data = {
            'comfyui': {
                'url': 'http://127.0.0.1:8188',
                'input_dir': str(tmp_path / "input")
            },
            'workflows': {
                'test_txt2img': {
                    'type': 'txt2img',
                    'description': 'Test txt2img workflow',
                    'workflow': str(sample_workflow_json),
                    'text_prompt_node_id': '6',
                    'default': True,
                    'settings': [
                        {
                            'name': 'hd',
                            'description': 'HD resolution',
                            'code': """
def hd(workflowjson):
    workflowjson["5"]["inputs"]["width"] = 1280
    workflowjson["5"]["inputs"]["height"] = 720
                            """
                        }
                    ]
                },
                'test_img2img': {
                    'type': 'img2img',
                    'description': 'Test img2img workflow',
                    'workflow': str(sample_workflow_json),
                    'text_prompt_node_id': '6',
                    'image_input_node_id': '7'
                },
                'test_txt2img_channel': {
                    'type': 'txt2img',
                    'description': 'test txt2img channel workflow',
                    'workflow': str(sample_workflow_json),
                    'text_prompt_node_id': '6',
                    'default_for': {
                        'channels': ['test_channel']
                    },
                },
                'test_txt2img_user': {
                    'type': 'txt2img',
                    'description': 'test txt2img user workflow',
                    'workflow': str(sample_workflow_json),
                    'text_prompt_node_id': '6',
                    'default_for': {
                        'users': ['test_user']
                    },
                },
            }
        }
        return config_data

    @pytest.fixture
    def workflow_manager(self, config_yaml):
        with patch('src.comfy.workflow_manager.WorkflowManager._load_config') as mock_load:
            mock_load.return_value = config_yaml
            return WorkflowManager('')

    def test_init(self, workflow_manager, config_yaml):
        assert workflow_manager.config is not None
        assert workflow_manager.workflows is not None
        assert workflow_manager.input_dir.exists()

    def test_get_workflow(self, workflow_manager):
        workflow = workflow_manager.get_workflow('test_txt2img')
        assert workflow is not None
        assert workflow['type'] == 'txt2img'
        assert workflow['text_prompt_node_id'] == '6'

    def test_get_nonexistent_workflow(self, workflow_manager):
        workflow = workflow_manager.get_workflow('nonexistent')
        assert workflow == {}

    def test_get_selectable_workflows(self, workflow_manager):
        # Test getting all workflows
        workflows = workflow_manager.get_selectable_workflows()
        assert len(workflows) == 4

        # Test getting specific type
        txt2img_workflows = workflow_manager.get_selectable_workflows('txt2img')
        assert len(txt2img_workflows) == 3
        assert list(txt2img_workflows.keys())[0] == 'test_txt2img'

    def test_load_workflow_file(self, workflow_manager, sample_workflow_json):
        workflow = workflow_manager.load_workflow_file(str(sample_workflow_json))
        assert workflow is not None
        assert "6" in workflow
        assert workflow["6"]["inputs"]["text"] == "default prompt"

    @pytest.mark.asyncio
    async def test_update_workflow_nodes(self, workflow_manager, sample_workflow_json):
        workflow_json = workflow_manager.load_workflow_file(str(sample_workflow_json))
        workflow_config = {
            'text_prompt_node_id': '6'
        }

        # Test updating prompt
        updated = workflow_manager.update_workflow_nodes(
            workflow_json,
            workflow_config,
            prompt="test prompt"
        )
        assert updated["6"]["inputs"]["text"] == "test prompt"

    def test_apply_settings(self, workflow_manager, sample_workflow_json):
        workflow_json = workflow_manager.load_workflow_file(str(sample_workflow_json))
        workflow_config = workflow_manager.get_workflow('test_txt2img')

        # Test applying HD setting
        updated = workflow_manager.apply_settings(
            workflow_json,
            workflow_config,
            "hd"
        )
        assert updated["5"]["inputs"]["width"] == 1280
        assert updated["5"]["inputs"]["height"] == 720

    @pytest.mark.asyncio
    async def test_prepare_workflow(self, workflow_manager):
        workflow = workflow_manager.prepare_workflow(
            'test_txt2img',
            prompt="test prompt",
            settings="hd"
        )
        assert workflow["6"]["inputs"]["text"] == "test prompt"
        assert workflow["5"]["inputs"]["width"] == 1280
        assert workflow["5"]["inputs"]["height"] == 720

    @pytest.mark.asyncio
    def test_get_default_workflow_for_channel(self, workflow_manager):
        workflow = workflow_manager.get_default_workflow('txt2img', channel_name='test_channel')
        print("Returned workflow:", workflow)
        assert workflow == 'test_txt2img_channel'

    @pytest.mark.asyncio
    def test_get_default_workflow_for_user(self, workflow_manager):
        workflow = workflow_manager.get_default_workflow('txt2img', user_name='test_user')

        assert workflow == 'test_txt2img_user'
