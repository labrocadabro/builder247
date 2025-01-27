"""Unit tests for tool response types."""

import pytest
from src.tools.types import ToolResponse, ToolResponseStatus


def test_tool_response_init():
    """Test ToolResponse initialization."""
    # Success response
    response = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="test data",
        metadata={"key": "value"},
    )
    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == "test data"
    assert response.metadata == {"key": "value"}
    assert response.error is None

    # Error response
    response = ToolResponse(
        status=ToolResponseStatus.ERROR,
        error="test error",
        metadata={"error_type": "ValueError"},
    )
    assert response.status == ToolResponseStatus.ERROR
    assert response.error == "test error"
    assert response.metadata == {"error_type": "ValueError"}
    assert response.data is None


def test_tool_response_validation():
    """Test ToolResponse validation."""
    # Missing required status
    with pytest.raises(TypeError):
        ToolResponse()  # type: ignore

    # Invalid status type
    with pytest.raises(TypeError):
        ToolResponse(status="SUCCESS")  # type: ignore


def test_tool_response_metadata():
    """Test ToolResponse metadata handling."""
    # Default metadata
    response = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="test",
    )
    assert response.metadata == {}

    # Custom metadata
    response = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="test",
        metadata={"key": "value"},
    )
    assert response.metadata == {"key": "value"}

    # Invalid metadata type
    with pytest.raises(ValueError):
        ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data="test",
            metadata="invalid",
        )

    # Metadata must be string keys
    with pytest.raises(ValueError):
        ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data="test",
            metadata={123: "value"},
        )
