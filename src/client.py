"""
Anthropic API client wrapper with tool integration support.
"""
from typing import List, Dict, Any, Optional, Union
import os
from dotenv import load_dotenv
import anthropic
from anthropic.types import MessageParam

class AnthropicClient:
    """Wrapper for Anthropic API client with tool integration."""
    
    def __init__(self, model: str = "claude-3-sonnet-20240229"):
        """Initialize the client with API key from environment."""
        load_dotenv()
        api_key = os.getenv("CLAUDE_API_KEY")
        
        # Ensure API key is present before initializing client
        if not api_key:
            raise ValueError("CLAUDE_API_KEY not found in environment")
            
        try:
            # Initialize with latest Anthropic SDK
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = model
            self.conversation_history: List[MessageParam] = []
        except Exception as e:
            raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")
    
    def send_message(
        self,
        message: str,
        system: Optional[Union[str, List[str]]] = None,
        max_tokens: int = 1024
    ) -> str:
        """Send a message to Claude and return the response."""
        try:
            # Create message request
            request = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": message}]
            }
            
            # Add system message if provided
            if system:
                if isinstance(system, str):
                    request["system"] = [system]
                else:
                    request["system"] = system
            
            # Add conversation history if any
            if self.conversation_history:
                request["messages"] = self.conversation_history + request["messages"]
            
            response = self.client.messages.create(**request)
            
            # Add messages to history
            self.conversation_history.append({"role": "user", "content": message})
            assistant_message = response.content[0].text
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message
            
        except anthropic.APIError as e:
            raise Exception(f"Anthropic API error: {str(e)}")
    
    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = [] 