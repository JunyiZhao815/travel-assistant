"""配置管理模块"""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载环境变量
# 首先尝试加载当前目录的.env
load_dotenv()

# 然后尝试加载HelloAgents的.env(如果存在)
helloagents_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if helloagents_env.exists():
    load_dotenv(helloagents_env, override=False)  # 不覆盖已有的环境变量


class Settings(BaseSettings):
    """应用配置"""

    # 应用基本配置
    app_name: str = "HelloAgents智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS配置 - 使用字符串,在代码中分割
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # 高德地图API配置
    amap_api_key: str = "825a0a359456a83cec0e2b985bc02556"

    # Unsplash API配置
    unsplash_access_key: str = "s9mTHRBx65X3bGaGULMOpB4JYhrWwSbrbOkkVLBxZjs"
    unsplash_secret_key: str = "axYt8A-zp99kk0Vdf3qYPeDLDRZx5DlH1WJtvqz71uM"

    # LLM默认配置 (支持被环境变量覆盖)
    openai_api_key: str = "sk-etR9rIkbDJDdFI9uzcfhALEmr9K7M7ZF8SVvm92QOrUOdgs9"
    openai_base_url: str = "https://api.hunyuan.cloud.tencent.com/v1"
    openai_model: str = "hunyuan-turbos-latest"

    # 日志配置
    log_level: str = "INFO"

    # 上下文压缩配置
    context_recent_turns: int = 4
    context_summary_trigger_turns: int = 6

    # RAG配置
    rag_enabled: bool = True
    rag_top_k: int = 3
    rag_knowledge_path: str = "knowledge/local_trip_knowledge.json"
    rag_retrieval_mode: str = "hybrid"  # keyword / vector / hybrid
    rag_keyword_weight: float = 0.4
    rag_vector_weight: float = 0.5
    rag_confidence_weight: float = 0.1
    rag_vector_backend: str = "local"  # local / pgvector
    pgvector_dsn: str = ""
    pgvector_table: str = "rag_knowledge_vectors"
    pgvector_dim: int = 256
    rag_versioning_enabled: bool = True
    rag_keep_latest_only: bool = True
    rag_expiration_enabled: bool = True
    rag_default_ttl_days: int = 30

    # 冲突指令消解配置
    instruction_conflict_guard_enabled: bool = True

    # 短期会话记忆配置
    session_memory_enabled: bool = True
    session_memory_ttl_minutes: int = 1440

    # 长期用户画像配置
    user_profile_enabled: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量

    def get_cors_origins_list(self) -> List[str]:
        """获取CORS origins列表"""
        return [origin.strip() for origin in self.cors_origins.split(',')]


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings


# 验证必要的配置
def validate_config():
    """验证配置是否完整"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY未配置")

    llm_api_key = settings.openai_api_key
    if not llm_api_key:
        warnings.append("固定LLM API Key未配置(settings.openai_api_key),LLM功能可能无法使用")

    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\n⚠️  配置警告:")
        for w in warnings:
            print(f"  - {w}")

    return True


# 打印配置信息(用于调试)
def print_config():
    """打印当前配置(隐藏敏感信息)"""
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务器: {settings.host}:{settings.port}")
    print(f"高德地图API Key: {'已配置' if settings.amap_api_key else '未配置'}")

    # 检查LLM配置
    llm_api_key = settings.openai_api_key
    llm_base_url = settings.openai_base_url
    llm_model = settings.openai_model

    print(f"LLM API Key: {'已配置' if llm_api_key else '未配置'}")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"LLM Model: {llm_model}")
    print(
        "上下文压缩: "
        f"recent_turns={settings.context_recent_turns}, "
        f"summary_trigger_turns={settings.context_summary_trigger_turns}"
    )
    print(
        "RAG配置: "
        f"enabled={settings.rag_enabled}, "
        f"top_k={settings.rag_top_k}, "
        f"path={settings.rag_knowledge_path}, "
        f"mode={settings.rag_retrieval_mode}, "
        f"kw_w={settings.rag_keyword_weight}, "
        f"vec_w={settings.rag_vector_weight}, "
        f"conf_w={settings.rag_confidence_weight}, "
        f"vector_backend={settings.rag_vector_backend}, "
        f"versioning={settings.rag_versioning_enabled}, "
        f"latest_only={settings.rag_keep_latest_only}, "
        f"expiration={settings.rag_expiration_enabled}, "
        f"default_ttl_days={settings.rag_default_ttl_days}"
    )
    if settings.rag_vector_backend == "pgvector":
        print(
            "pgvector: "
            f"table={settings.pgvector_table}, "
            f"dim={settings.pgvector_dim}, "
            f"dsn={'已配置' if settings.pgvector_dsn else '未配置'}"
        )
    print(f"冲突指令消解: enabled={settings.instruction_conflict_guard_enabled}")
    print(
        "短期会话记忆: "
        f"enabled={settings.session_memory_enabled}, "
        f"ttl_minutes={settings.session_memory_ttl_minutes}"
    )
    print(f"长期用户画像: enabled={settings.user_profile_enabled}")
    print(f"日志级别: {settings.log_level}")
