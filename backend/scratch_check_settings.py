import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.config import get_settings

settings = get_settings()
print(f"USE_LOCAL_LLM: {settings.USE_LOCAL_LLM}")
print(f"GEMINI_API_KEY: {settings.GEMINI_API_KEY[:8]}...")
print(f"GROQ_API_KEY: {settings.GROQ_API_KEY[:8]}...")
print(f"GROQ_MODEL: {settings.GROQ_MODEL}")
print(f"FIGURE_ANALYSIS_ENABLED: {settings.FIGURE_ANALYSIS_ENABLED}")
