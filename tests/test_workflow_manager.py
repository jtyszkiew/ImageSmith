import pytest
from pathlib import Path
import yaml

from imagesmith import WorkflowManager


def test_workflow_manager_init(config_file):
    """Test WorkflowManager initialization"""
    manager = WorkflowManager(config_file)
    assert manager.default_workflow == "test_workflow"
    assert "test_workflow" in manager.workflows

def test_get_workflow(config_file):
    """Test getting workflow configuration"""
    manager = WorkflowManager(config_file)
    workflow = manager.get_workflow("test_workflow")
    assert workflow is not None
    assert workflow["description"] == "Test Workflow"
    assert workflow["text_prompt_node_id"] == 27
    assert workflow["selectable"] is True

def test_get_selectable_workflows(config_file):
    """Test getting selectable workflows"""
    manager = WorkflowManager(config_file)
    workflows = manager.get_selectable_workflows()
    assert "test_workflow" in workflows
    assert workflows["test_workflow"]["selectable"] is True

def test_update_prompt_node(config_file):
    """Test updating prompt in workflow"""
    manager = WorkflowManager(config_file)
    workflow_json = {
        "27": {
            "inputs": {
                "text": "old prompt"
            }
        }
    }
    workflow_config = {"text_prompt_node_id": 27}

    updated = manager.update_prompt_node(workflow_json.copy(), "new prompt", workflow_config)
    assert updated["27"]["inputs"]["text"] == "new prompt"

def test_apply_settings(config_file):
    """Test applying settings to workflow"""
    manager = WorkflowManager(config_file)

    workflow_json = {
        "27": {
            "inputs": {
                "steps": 10
            }
        }
    }

    # Test __before settings
    result = manager.apply_settings(workflow_json.copy())
    assert result["27"]["inputs"]["steps"] == 20

    # Test custom settings
    result = manager.apply_settings(workflow_json.copy(), "change_steps(30)")
    assert result["27"]["inputs"]["steps"] == 30

def test_prepare_workflow(config_file):
    """Test complete workflow preparation"""
    manager = WorkflowManager(config_file)

    result = manager.prepare_workflow("test_workflow", "test prompt", "change_steps(25)")

    assert result["27"]["inputs"]["text"] == "test prompt"
    assert result["27"]["inputs"]["steps"] == 25
