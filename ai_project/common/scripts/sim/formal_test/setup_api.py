"""OpenAI API 配置脚本。

提供交互式配置 OpenAI API key 的功能：
- 提示用户输入 API key
- 自动创建 .env 文件
- 验证 API key 格式（必须以 sk- 开头）
- 可选测试 API 连接
- 支持 --check 参数检查当前配置状态

使用方法：
    python setup_api.py            # 交互式配置
    python setup_api.py --check    # 检查当前配置状态
"""

import os
import sys
import argparse
from pathlib import Path

# 脚本所在目录，.env 文件将创建在此目录下
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
ENV_EXAMPLE_FILE = SCRIPT_DIR / ".env.example"

# .env 文件中需要写入的配置项模板
ENV_TEMPLATE = """# OpenAI API Configuration
OPENAI_API_KEY={api_key}
OPENAI_MODEL={model}
OPENAI_BASE_URL={base_url}
"""

# 默认配置值
DEFAULT_MODEL = "gpt-4"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def validate_api_key(api_key):
    """验证 API key 格式是否合法。

    规则：必须以 'sk-' 开头，且长度大于 3。

    参数:
        api_key (str): 待验证的 API key。

    返回:
        bool: 合法返回 True，否则返回 False。
    """
    if not api_key:
        return False
    return api_key.startswith("sk-") and len(api_key) > 3


def write_env_file(api_key, model=DEFAULT_MODEL, base_url=DEFAULT_BASE_URL):
    """将配置写入 .env 文件。

    参数:
        api_key (str): OpenAI API key。
        model (str): 使用的模型名称。
        base_url (str): API 基础 URL。

    返回:
        Path: 写入的 .env 文件路径。
    """
    content = ENV_TEMPLATE.format(
        api_key=api_key.strip(),
        model=model.strip(),
        base_url=base_url.strip(),
    )
    ENV_FILE.write_text(content, encoding="utf-8")
    return ENV_FILE


def read_env_file():
    """读取并解析 .env 文件中的配置。

    返回:
        dict: 配置字典，键为变量名，值为对应内容。
              若文件不存在则返回空字典。
    """
    if not ENV_FILE.exists():
        return {}

    config = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # 跳过空行与注释行
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    return config


def test_api_connection(api_key, model=DEFAULT_MODEL, base_url=DEFAULT_BASE_URL):
    """测试与 OpenAI API 的连接是否正常。

    尝试导入 openai 库并发送一个简单请求，捕获并报告错误。

    参数:
        api_key (str): OpenAI API key。
        model (str): 测试使用的模型。
        base_url (str): API 基础 URL。

    返回:
        bool: 连接成功返回 True，否则返回 False。
    """
    try:
        import openai
    except ImportError:
        print("[警告] 未安装 openai 库，无法进行连接测试。")
        print("       可通过 `pip install openai` 安装。")
        return False

    print(f"正在测试连接 {base_url} ...")
    try:
        # 兼容 openai >= 1.0.0 的新版客户端接口
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        print("[成功] API 连接测试通过。")
        return True
    except Exception as e:
        print(f"[失败] API 连接测试失败：{e}")
        return False


def check_config():
    """检查当前配置状态并打印结果。

    读取 .env 文件，输出各项配置值以及 API key 的格式校验结果。

    返回:
        bool: 配置完整且合法返回 True，否则返回 False。
    """
    print("=" * 50)
    print("当前 OpenAI API 配置状态")
    print("=" * 50)

    if not ENV_FILE.exists():
        print(f"[未配置] 未找到 .env 文件：{ENV_FILE}")
        if ENV_EXAMPLE_FILE.exists():
            print(f"[提示] 可参考模板文件：{ENV_EXAMPLE_FILE}")
        print("[提示] 运行 `python setup_api.py` 进行交互式配置。")
        return False

    config = read_env_file()
    api_key = config.get("OPENAI_API_KEY", "")
    model = config.get("OPENAI_MODEL", "")
    base_url = config.get("OPENAI_BASE_URL", "")

    print(f".env 文件路径: {ENV_FILE}")
    print(f"OPENAI_API_KEY : {mask_api_key(api_key) if api_key else '<未设置>'}")
    print(f"OPENAI_MODEL   : {model or '<未设置>'}")
    print(f"OPENAI_BASE_URL: {base_url or '<未设置>'}")
    print("-" * 50)

    if not api_key:
        print("[错误] OPENAI_API_KEY 未设置。")
        return False

    if validate_api_key(api_key):
        print("[OK] API key 格式校验通过。")
        return True
    else:
        print("[错误] API key 格式不合法，必须以 'sk-' 开头。")
        return False


def mask_api_key(api_key):
    """对 API key 做掩码处理，只显示前缀与末尾几位。

    参数:
        api_key (str): 原始 API key。

    返回:
        str: 掩码后的字符串。
    """
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return api_key[:3] + "****"
    return api_key[:3] + "****" + api_key[-4:]


def prompt_input(prompt, default=None):
    """交互式获取用户输入，支持默认值。

    参数:
        prompt (str): 提示信息。
        default (str): 默认值，用户直接回车时使用。

    返回:
        str: 用户输入内容。
    """
    if default:
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw or default
    return input(f"{prompt}: ").strip()


def interactive_setup():
    """交互式配置流程。

    引导用户输入 API key 与可选参数，验证格式后写入 .env 文件，
    并询问是否进行连接测试。

    返回:
        int: 退出码，0 表示成功，非 0 表示失败。
    """
    print("=" * 50)
    print("OpenAI API 交互式配置")
    print("=" * 50)

    # 读取已有配置作为默认值，方便修改单项
    existing = read_env_file()
    default_key = existing.get("OPENAI_API_KEY", "")
    default_model = existing.get("OPENAI_MODEL", DEFAULT_MODEL)
    default_base_url = existing.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)

    # 输入 API key，循环直到格式合法或用户放弃
    while True:
        api_key = prompt_input("请输入 OPENAI_API_KEY", default_key if default_key else None)
        if not api_key:
            print("[错误] API key 不能为空。")
            continue
        if not validate_api_key(api_key):
            print("[错误] API key 格式不合法，必须以 'sk-' 开头。")
            retry = input("是否重新输入？(y/n，默认 y): ").strip().lower()
            if retry in ("", "y", "yes"):
                continue
            print("[中止] 用户取消配置。")
            return 1
        break

    # 输入模型名称与 base URL
    model = prompt_input("请输入 OPENAI_MODEL", default_model)
    base_url = prompt_input("请输入 OPENAI_BASE_URL", default_base_url)

    # 写入 .env 文件
    try:
        env_path = write_env_file(api_key, model, base_url)
    except OSError as e:
        print(f"[错误] 写入 .env 文件失败：{e}")
        return 1

    print(f"\n[成功] 配置已写入：{env_path}")

    # 询问是否进行连接测试
    choice = input("\n是否立即测试 API 连接？(y/n，默认 n): ").strip().lower()
    if choice in ("y", "yes"):
        test_api_connection(api_key, model, base_url)
    else:
        print("[跳过] 未进行连接测试。")

    print("\n配置完成。")
    return 0


def main():
    """主入口函数，解析命令行参数并分发到对应流程。"""
    parser = argparse.ArgumentParser(
        description="OpenAI API 配置脚本，支持交互式配置与状态检查。"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查当前配置状态，不进行交互式配置。",
    )
    args = parser.parse_args()

    if args.check:
        ok = check_config()
        sys.exit(0 if ok else 1)

    sys.exit(interactive_setup())


if __name__ == "__main__":
    main()
