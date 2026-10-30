"""
Centralized configuration management
Loads settings from environment variables and config files
"""
import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "gateway_config.json"
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "gateway.db")
LOG_DIR = BASE_DIR / "logs"

# Ensure log directory exists
LOG_DIR.mkdir(exist_ok=True)

# Gateway settings
GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8790"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

# Security settings
API_KEY_SECRET = os.getenv("API_KEY_SECRET", "change_this_secret")
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "false").lower() == "true"

# Logging settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOG_DIR / os.getenv("LOG_FILE", "gateway.log")

def load_providers() -> List[Dict[str, Any]]:
    """Load provider configuration from JSON file"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        data = [data]
    
    return data

def save_providers(providers: List[Dict[str, Any]]) -> None:
    """Save provider configuration to JSON file"""
    with open(CONFIG_PATH, "w") as f:
        json.dump(providers, f, indent=2)

def get_api_keys_from_env() -> Dict[str, List[str]]:
    """Extract API keys from environment variables"""
    keys = {
        "groq": [],
        "openrouter": [],
        "gemini": []
    }
    
    # Groq keys
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            keys["groq"].append(key)
    
    # OpenRouter keys
    for i in range(1, 10):
        key = os.getenv(f"OPENROUTER_API_KEY_{i}")
        if key:
            keys["openrouter"].append(key)
    
    # Gemini keys
    for i in range(1, 10):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            keys["gemini"].append(key)
    
    return keys

def merge_env_keys(providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge API keys from environment into provider config"""
    env_keys = get_api_keys_from_env()
    
    for provider in providers:
        provider_name = provider.get("provider", "").lower()
        if provider_name in env_keys and env_keys[provider_name]:
            # Use env keys if available, otherwise keep config keys
            provider["api_keys"] = env_keys[provider_name]
    
    return providers

# Initialize providers
try:
    providers = load_providers()
    providers = merge_env_keys(providers)
except Exception as e:
    print(f"Warning: Could not load providers: {e}")
    providers = []
