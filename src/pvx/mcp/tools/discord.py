import httpx
from typing import Dict, Any, List

class DiscordTool:
    """
    MCP tool for Discord operations.
    Skeletons for logging/notifications.
    """
    def __init__(self, bot_token: str, allowed_channels: List[str]):
        self.bot_token = bot_token
        self.allowed_channels = allowed_channels
        self.base_url = "https://discord.com/api/v10"
        self.headers = {
            "Authorization": f"Bot {self.bot_token}"
        }

    async def send_message(self, channel_id: str, content: str) -> Dict[str, Any]:
        if channel_id not in self.allowed_channels:
            return {"error": f"Channel ID '{channel_id}' is not allowed"}
            
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/channels/{channel_id}/messages"
            data = {"content": content}
            response = await client.post(url, headers=self.headers, json=data)
            if response.status_code == 200:
                return response.json()
            return {"error": response.text}
