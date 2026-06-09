"""调试 AI 配置加载和 Provider 可用性"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import get_settings
from app.services.ai import ai_service

def main():
    print("=== AI 配置调试 ===")
    
    # 1. 检查环境配置
    settings = get_settings()
    print(f"AI_DEFAULT_PROVIDER: {settings.AI_DEFAULT_PROVIDER}")
    print(f"AI_OPENAI_API_KEY: {'***' if settings.AI_OPENAI_API_KEY else 'EMPTY'}")
    print(f"AI_OPENAI_MODEL: {settings.AI_OPENAI_MODEL}")
    print(f"AI_OPENAI_BASE_URL: {settings.AI_OPENAI_BASE_URL}")
    print(f"AI_DASHSCOPE_API_KEY: {'***' if settings.AI_DASHSCOPE_API_KEY else 'EMPTY'}")
    print(f"AI_DASHSCOPE_MODEL: {settings.AI_DASHSCOPE_MODEL}")
    
    # 2. 检查包依赖
    print("\n=== 包依赖检查 ===")
    try:
        import openai
        print("✓ openai 包已安装")
        print(f"  版本: {openai.__version__}")
    except ImportError as e:
        print(f"✗ openai 包未安装: {e}")
    
    try:
        import dashscope
        print("✓ dashscope 包已安装")
        print(f"  版本: {dashscope.__version__}")
    except ImportError as e:
        print(f"✗ dashscope 包未安装: {e}")
    
    # 3. 检查 AI Service
    print("\n=== AI Service 状态 ===")
    print(f"当前 provider: {ai_service.current_provider()}")
    print(f"可用 providers: {list(ai_service._providers.keys())}")
    
    # 4. 检查各个 provider 的可用性
    print("\n=== Provider 可用性检查 ===")
    for name, provider in ai_service._providers.items():
        print(f"{name}: {'✓ 可用' if provider.is_available() else '✗ 不可用'}")
        if name == "openai":
            print(f"  - API Key: {'✓ 已配置' if provider._api_key else '✗ 未配置'}")
            print(f"  - Base URL: {provider._base_url}")
            print(f"  - Model: {provider._model}")
            print(f"  - Client: {'✓ 已初始化' if provider._client else '✗ 未初始化'}")

if __name__ == "__main__":
    main()
