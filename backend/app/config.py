from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import os


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_DATABASE_URL = f"sqlite:///{(BASE_DIR / 'ai_mbse_demo.db').as_posix()}"


class Settings(BaseModel):
    app_name: str = "AI-MBSE-Demo"
    api_prefix: str = "/api"
    database_url: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    llm_api_base_url: str = os.getenv("LLM_API_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
    llm_enable_real_api: bool = os.getenv("LLM_ENABLE_REAL_API", "false").lower() == "true"

    sysml_api_base_url: str = os.getenv("SYSML_API_BASE_URL", "http://127.0.0.1:9000")
    sysml_api_token: str = os.getenv("SYSML_API_TOKEN", "")
    sysml_enable_real_api: bool = os.getenv("SYSML_ENABLE_REAL_API", "true").lower() == "true"
    sysml_project_id: str = os.getenv("SYSML_PROJECT_ID", "")
    sysml_project_name: str = os.getenv("SYSML_PROJECT_NAME", "AI-MBSE-Demo")

    magicdraw_enable_bridge: bool = os.getenv("MAGICDRAW_ENABLE_BRIDGE", "false").lower() == "true"
    magicdraw_bridge_url: str = os.getenv("MAGICDRAW_BRIDGE_URL", "http://127.0.0.1:7010/api")
    magicdraw_project_path: str = os.getenv("MAGICDRAW_PROJECT_PATH", "")
    magicdraw_package_name: str = os.getenv("MAGICDRAW_PACKAGE_NAME", "AI_MBSE_Demo")
    magicdraw_export_dir: str = os.getenv("MAGICDRAW_EXPORT_DIR", str(BASE_DIR / "exports" / "magicdraw"))
    magicdraw_import_timeout_sec: int = int(os.getenv("MAGICDRAW_IMPORT_TIMEOUT_SEC", "30") or "30")

    gmat_enable_real: bool = os.getenv("GMAT_ENABLE_REAL", "false").lower() == "true"
    gmat_console_path: str = os.getenv("GMAT_CONSOLE_PATH", "")
    gmat_root_dir: str = os.getenv("GMAT_ROOT_DIR", "")
    gmat_work_dir: str = os.getenv("GMAT_WORK_DIR", str(BASE_DIR / "exports" / "gmat"))

    simulink_enable_real: bool = os.getenv("SIMULINK_ENABLE_REAL", "false").lower() == "true"
    simulink_matlab_path: str = os.getenv("SIMULINK_MATLAB_PATH", "")
    simulink_model_path: str = os.getenv("SIMULINK_MODEL_PATH", "")
    simulink_work_dir: str = os.getenv("SIMULINK_WORK_DIR", str(BASE_DIR / "exports" / "simulink"))
    simulink_timeout_sec: int = int(os.getenv("SIMULINK_TIMEOUT_SEC", "120") or "120")

    reset_runtime_state_on_startup: bool = os.getenv("RESET_RUNTIME_STATE_ON_STARTUP", "true").lower() == "true"
    reset_knowledge_on_startup: bool = os.getenv("RESET_KNOWLEDGE_ON_STARTUP", "false").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()
