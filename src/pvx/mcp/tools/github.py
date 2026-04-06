import httpx
from typing import Dict, Any, List

class GitHubTool:
    """
    MCP tool for GitHub operations.
    Skeletons for read/write/PR operations.
    """
    def __init__(self, token: str, allowed_repos: List[str]):
        self.token = token
        self.allowed_repos = allowed_repos
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    async def get_repo_contents(self, repo: str, path: str) -> Dict[str, Any]:
        if repo not in self.allowed_repos:
            return {"error": f"Repo '{repo}' is not allowed"}
            
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{repo}/contents/{path}"
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return {"error": response.text}

    async def create_issue(self, repo: str, title: str, body: str) -> Dict[str, Any]:
        if repo not in self.allowed_repos:
            return {"error": f"Repo '{repo}' is not allowed"}
            
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{repo}/issues"
            data = {"title": title, "body": body}
            response = await client.post(url, headers=self.headers, json=data)
            if response.status_code == 201:
                return response.json()
            return {"error": response.text}
