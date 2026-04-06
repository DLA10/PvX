import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import Dict, List, Optional, Union

class OrchestratorConfig(BaseModel):
    cli: str = "claude"

class RoutingConfig(BaseModel):
    rules: Dict[str, str]
    fallback_chain: Dict[str, List[str]]
    classifier: Dict[str, Union[str, float]]

class LocalModelConfig(BaseModel):
    name: str
    vram_mb: int
    context_tokens: int
    supports_function_calling: bool

class ClaudeModelConfig(BaseModel):
    context_tokens: int

class ModelsConfig(BaseModel):
    local: List[LocalModelConfig]
    claude: ClaudeModelConfig

class PreemptionConfig(BaseModel):
    p5_preempts: List[str]
    p4_preempts: List[str]

class VRAMConfig(BaseModel):
    safety_buffer_mb: int
    zombie_timeout_seconds: int
    zombie_utilisation_threshold_pct: int
    polling_interval_seconds: int
    preemption: PreemptionConfig

class QueueConfig(BaseModel):
    default_priority: int
    default_max_retries: int
    dependency_failure_strategy: str
    affinity_batch_max_tasks: int
    affinity_batch_max_seconds: int
    starvation_timeout_seconds: int
    partial_save_min_tokens: int

class ContextConfig(BaseModel):
    compression_threshold_pct: int
    compression_model: str
    compression_keep_last_messages: int

class SecurityConfig(BaseModel):
    sql_blocked_keywords: List[str]
    path_traversal_check: bool
    command_injection_check: bool

class PostgresConfig(BaseModel):
    enabled: bool
    connection: str
    allowed_operations: List[str]
    blocked_operations: List[str]
    max_result_rows: int

class DiscordConfig(BaseModel):
    enabled: bool
    bot_token: str
    allowed_channels: List[str]

class GithubConfig(BaseModel):
    enabled: bool
    token: str
    allowed_repos: List[str]
    allowed_operations: List[str]
    blocked_operations: List[str]

class FilesystemConfig(BaseModel):
    enabled: bool
    allowed_paths: List[str]
    blocked_paths: List[str]
    max_file_size_mb: int

class CustomServerConfig(BaseModel):
    name: str
    url: str
    enabled: bool

class MCPServersConfig(BaseModel):
    postgresql: Optional[PostgresConfig] = None
    discord: Optional[DiscordConfig] = None
    github: Optional[GithubConfig] = None
    filesystem: Optional[FilesystemConfig] = None
    custom: Optional[List[CustomServerConfig]] = None

class AppConfig(BaseModel):
    orchestrator: OrchestratorConfig
    routing: RoutingConfig
    models: ModelsConfig
    vram: VRAMConfig
    queue: QueueConfig
    context: ContextConfig
    security: SecurityConfig
    mcp_servers: Optional[MCPServersConfig] = None

def load_config(config_path: str = "pvx.config.yaml") -> Optional[AppConfig]:
    path = Path(config_path)
    if not path.exists():
        path = Path("pvx.config.example.yaml")
        if not path.exists():
            # For testing/initialization fallback
            return None
            
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        
    return AppConfig(**data)

try:
    config = load_config()
except Exception:
    config = None
