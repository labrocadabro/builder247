"""
Anthropic API client wrapper with tool integration support.
"""
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv
import anthropic

class AnthropicClient:
    """Wrapper for Anthropic API client with tool integration."""
    
    def __init__(self, model: str = "claude-3-opus-20240229"):
        """Initialize the client with API key from environment."""
        load_dotenv()
        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise ValueError("CLAUDE_API_KEY not found in environment")
        
        self.client = anthropic.Client(api_key=api_key)
        self.model = model
        self.conversation_history: List[Dict[str, Any]] = []
    
    def send_message(
        self,
        message: str,
        system: Optional[str] = None,
        max_tokens: int = 1024
    ) -> str:
        """Send a message to Claude and return the response."""
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=self.conversation_history
            )
            
            # Add assistant response to history
            assistant_message = response.content[0].text
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except anthropic.APIError as e:
            raise Exception(f"Anthropic API error: {str(e)}")
    
    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = [] 