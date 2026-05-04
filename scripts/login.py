#!/usr/bin/env python3
"""
B站登录验证脚本

用法：
    python scripts/login.py              # 扫码登录（推荐）
    python scripts/login.py --cookie     # 手动输入 Cookie
    python scripts/login.py --check      # 仅验证当前 Cookie
    python scripts/login.py --help       # 显示帮助

功能：
    1. 扫码登录：生成二维码，手机扫码即可登录（推荐）
    2. 手动输入：支持粘贴完整 Cookie
    3. 自动校验 Cookie 必需字段
    4. 验证 Cookie 有效性
    5. 获取用户信息并保存
"""

import json
import logging
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lib.api import BilibiliAPI, CookieExpiredError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config.json"

# Cookie必需字段
REQUIRED_COOKIE_FIELDS = ["SESSDATA", "bili_jct"]
RECOMMENDED_COOKIE_FIELDS = ["buvid3", "buvid4", "DedeUserID"]

# B站扫码登录 API
QRCODE_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


# ==================== 扫码登录 ====================

def generate_qrcode() -> Tuple[str, str]:
    """生成登录二维码

    Returns:
        元组：(二维码URL, qrcode_key)
    """
    try:
        resp = requests.get(QRCODE_GENERATE_URL, timeout=10)
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(data.get("message", "生成二维码失败"))

        return data["data"]["url"], data["data"]["qrcode_key"]
    except Exception as e:
        raise Exception(f"请求二维码失败: {e}")


def poll_qrcode_status(qrcode_key: str) -> Tuple[int, str, Optional[str]]:
    """轮询扫码状态

    Args:
        qrcode_key: 二维码密钥

    Returns:
        元组：(状态码, 状态描述, Cookie字符串或None)

    状态码说明：
        0: 登录成功
        86101: 未扫码
        86090: 已扫码未确认
        86038: 二维码已过期
    """
    try:
        resp = requests.get(f"{QRCODE_POLL_URL}?qrcode_key={qrcode_key}", timeout=10)
        data = resp.json()

        code = data.get("code", -1)
        message = data.get("message", "未知状态")

        # 登录成功，提取 Cookie
        if code == 0:
            cookie_parts = []
            # 从响应头或返回数据中提取 Cookie
            set_cookie = resp.headers.get("Set-Cookie", "")
            if set_cookie:
                cookie_parts.append(set_cookie)

            # 从 data 中提取
            if data.get("data"):
                # 尝试从 url 参数中提取
                url = data["data"].get("url", "")
                if "SESSDATA=" in url:
                    match = re.search(r'SESSDATA=([^&]+)', url)
                    if match:
                        cookie_parts.append(f"SESSDATA={match.group(1)}")

            return code, "登录成功", None  # Cookie 需要从 Set-Cookie 提取

        return code, message, None

    except Exception as e:
        return -1, f"请求失败: {e}", None


def extract_cookie_from_response(resp) -> str:
    """从响应中提取完整 Cookie

    Args:
        resp: requests 响应对象

    Returns:
        Cookie 字符串
    """
    cookies = {}

    # 从 Set-Cookie 头提取
    set_cookie_header = resp.headers.get("Set-Cookie", "")
    if set_cookie_header:
        # 解析多个 cookie
        for part in set_cookie_header.split(","):
            if "=" in part:
                key_val = part.split(";")[0].strip()
                if "=" in key_val:
                    key, val = key_val.split("=", 1)
                    cookies[key.strip()] = val.strip()

    # 合并请求中的 cookie
    for cookie in resp.cookies:
        cookies[cookie] = resp.cookies[cookie]

    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def login_by_qrcode() -> Optional[str]:
    """扫码登录

    Returns:
        Cookie 字符串，失败返回 None
    """
    print("\n" + "=" * 60)
    print("📱 B站扫码登录")
    print("=" * 60)

    try:
        # 生成二维码
        print("\n正在生成登录二维码...")
        qrcode_url, qrcode_key = generate_qrcode()

        print("\n" + "-" * 60)
        print("请使用 B站 App 扫描下方二维码登录：")
        print("-" * 60)

        # 生成终端二维码（ASCII）
        print_qrcode_ascii(qrcode_url)

        print("\n或直接访问以下链接扫码：")
        print(f"\n  {qrcode_url}\n")

        # 尝试打开浏览器
        try:
            print("正在打开浏览器...")
            webbrowser.open(qrcode_url)
        except:
            pass

        print("-" * 60)
        print("等待扫码（二维码有效期约 3 分钟）...\n")

        # 轮询扫码状态
        start_time = time.time()
        timeout = 180  # 3 分钟超时

        import requests as req

        while time.time() - start_time < timeout:
            resp = req.get(f"{QRCODE_POLL_URL}?qrcode_key={qrcode_key}", timeout=10)
            data = resp.json()

            code = data.get("code", -1)
            message = data.get("message", "")

            if code == 0:
                # 登录成功，提取 Cookie
                cookie_str = extract_cookie_from_response(resp)
                if not cookie_str:
                    # 尝试从 Set-Cookie 提取
                    set_cookie = resp.headers.get("Set-Cookie", "")
                    cookie_str = set_cookie

                print("\n" + "=" * 60)
                print("✅ 登录成功！")
                print("=" * 60)
                return cookie_str

            elif code == 86101:
                # 未扫码，继续等待
                print(".", end="", flush=True)
                time.sleep(2)

            elif code == 86090:
                # 已扫码，等待确认
                print("\n已扫码，请在手机上确认登录...")
                time.sleep(2)

            elif code == 86038:
                # 二维码过期
                print("\n❌ 二维码已过期，请重新运行脚本")
                return None

            else:
                print(f"\n状态: {message}")
                time.sleep(2)

        print("\n❌ 登录超时，请重新运行脚本")
        return None

    except Exception as e:
        print(f"\n❌ 扫码登录失败: {e}")
        return None


def print_qrcode_ascii(url: str) -> None:
    """打印 ASCII 二维码（简化版）

    由于标准库限制，这里只显示链接和提示
    实际使用建议安装 qrcode 库

    Args:
        url: 二维码链接
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        # 没有安装 qrcode 库，显示简化提示
        print("""
    ╔══════════════════════════════╗
    ║                              ║
    ║   请使用手机扫描上方链接    ║
    ║   或打开 B站 App 扫码登录   ║
    ║                              ║
    ╚══════════════════════════════╝
        """)
        print("提示: 安装 qrcode 库可显示二维码图案")
        print("pip install qrcode")


# ==================== Cookie 解析 ====================

import requests


def parse_cookie(cookie_str: str) -> Dict[str, str]:
    """解析Cookie字符串为字典

    支持多种格式：
    - 分号分隔：SESSDATA=xxx; bili_jct=xxx
    - 换行分隔：每行一个键值对

    Args:
        cookie_str: Cookie字符串

    Returns:
        Cookie键值对字典
    """
    cookies: Dict[str, str] = {}

    # 支持多种格式：分号分隔、换行分隔
    parts = re.split(r'[;\n]', cookie_str.strip())

    for part in parts:
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            cookies[key.strip()] = value.strip()

    return cookies


def validate_cookie_format(
    cookie_str: str
) -> Tuple[bool, List[str], List[str], Dict[str, str]]:
    """校验Cookie格式

    Args:
        cookie_str: Cookie字符串

    Returns:
        元组：(是否有效, 缺失的必需字段, 缺失的推荐字段, 解析后的Cookie字典)
    """
    cookies = parse_cookie(cookie_str)

    missing_required = [f for f in REQUIRED_COOKIE_FIELDS if f not in cookies]
    missing_recommended = [f for f in RECOMMENDED_COOKIE_FIELDS if f not in cookies]

    is_valid = len(missing_required) == 0

    return is_valid, missing_required, missing_recommended, cookies


# ==================== 用户交互 ====================

def get_cookie_from_user() -> str:
    """交互式获取Cookie

    Returns:
        用户输入的Cookie字符串
    """
    print("\n" + "=" * 50)
    print("获取完整 Cookie 的方法")
    print("=" * 50)
    print("""
1. 登录 bilibili.com
2. 按 F12 打开开发者工具
3. 切换到 Network（网络）标签
4. 刷新页面，点击任意请求
5. 在 Headers → Request Headers 中找到 Cookie
6. 复制整行 Cookie（包含所有字段）

示例格式：
SESSDATA=xxx; bili_jct=xxx; buvid3=xxx; DedeUserID=123; ...
""")
    print("=" * 50)
    print("\n请粘贴完整 Cookie（粘贴后按回车）：")
    print("（直接 Ctrl+V 粘贴，支持多行）")
    print("-" * 50)

    # 支持多行输入（直到遇到空行）
    lines: List[str] = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except EOFError:
        pass

    cookie_str = " ".join(lines) if lines else ""
    return cookie_str


def display_cookie_info(cookies: Dict[str, str]) -> None:
    """显示解析后的Cookie信息

    Args:
        cookies: Cookie字典
    """
    print("\n已识别的 Cookie 字段：")

    # 只显示前8个字段
    display_count = min(8, len(cookies))

    for key in list(cookies.keys())[:display_count]:
        value = cookies[key]
        # 截断长值
        value_preview = value[:20] + "..." if len(value) > 20 else value

        # 标记字段类型
        if key in REQUIRED_COOKIE_FIELDS:
            field_type = "[必需]"
        elif key in RECOMMENDED_COOKIE_FIELDS:
            field_type = "[推荐]"
        else:
            field_type = ""

        print(f"  - {key}: {value_preview} {field_type}")


# ==================== 配置管理 ====================

def load_config() -> Optional[Dict]:
    """加载配置文件

    Returns:
        配置字典，如果文件不存在则返回None
    """
    if not CONFIG_PATH.exists():
        return None

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取配置文件失败: {e}")
        return None


def save_config(config: Dict) -> bool:
    """保存配置文件

    Args:
        config: 配置字典

    Returns:
        是否保存成功
    """
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"配置已保存到 {CONFIG_PATH}")
        return True
    except IOError as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


def do_login() -> bool:
    """执行登录流程（扫码优先）

    Returns:
        是否登录成功
    """
    print("\n请选择登录方式：")
    print("  [1] 扫码登录（推荐）")
    print("  [2] 手动输入 Cookie")
    print("  [q] 退出")

    try:
        choice = input("\n请输入选择: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return False

    if choice == "1":
        cookie_str = login_by_qrcode()
        if not cookie_str:
            return False
    elif choice == "2":
        cookie_str = get_cookie_from_user()
        if not cookie_str:
            print("\n[FAIL] 未输入 Cookie")
            return False
    elif choice == "q":
        print("已取消")
        return False
    else:
        print("无效选择")
        return False

    # 校验格式
    is_valid, missing_required, missing_recommended, cookies = validate_cookie_format(cookie_str)

    if not is_valid:
        print(f"\n[FAIL] Cookie 缺少必需字段: {missing_required}")
        print("\n必需字段说明：")
        print("  - SESSDATA: 登录凭证（必须有）")
        print("  - bili_jct: CSRF Token（必须有）")
        print("\n请重新尝试")
        return False

    if missing_recommended:
        print(f"\n[提示] Cookie 缺少推荐字段: {missing_recommended}")
        print("继续验证...")

    # 显示解析结果
    display_cookie_info(cookies)

    # 验证Cookie
    print("\n正在验证 Cookie...")
    api = BilibiliAPI(cookie_str)
    result = api.validate_cookie()

    if not result.get("valid"):
        print(f"\n[FAIL] Cookie 无效")
        print(f"错误: {result.get('error')}")
        print("\n可能原因：")
        print("  1. Cookie 已过期（有效期约30天）")
        print("  2. 账号在其他设备登录导致Cookie失效")
        print("  3. 复制不完整")
        print("\n请重新尝试")
        return False

    print("\n[OK] Cookie 有效！")

    # 保存配置
    config = {
        "user_id": result.get("mid"),
        "user_name": result.get("name"),
        "cookie": cookie_str,
        "vip_status": result.get("vip_status", False),
        "last_sync": None,
        "sync_interval_hours": 24
    }

    if not save_config(config):
        return False

    print(f"\n用户信息：")
    print(f"  - 用户ID: {result.get('mid')}")
    print(f"  - 用户名: {result.get('name')}")
    if result.get("vip_status"):
        print(f"  - 会员状态: 大会员")

    print(f"\n[OK] 配置已保存到 config.json")
    print("\n下一步：")
    print("  python scripts/sync.py  # 同步收藏数据")

    return True


def check_existing_cookie() -> bool:
    """验证现有Cookie

    Returns:
        Cookie是否有效
    """
    print("=== B站登录验证 ===\n")

    config = load_config()

    if config is None:
        print("[FAIL] 配置文件不存在")
        print("\n请运行: python scripts/login.py")
        return False

    if not config.get("cookie"):
        print("[FAIL] Cookie 未配置")
        print("\n请运行: python scripts/login.py")
        return False

    # 校验格式
    is_valid, missing_required, missing_recommended, cookies = validate_cookie_format(config["cookie"])

    print("Cookie 格式检查：")
    if is_valid:
        print("  [OK] 必需字段完整")
    else:
        print(f"  [X] 缺少必需字段: {missing_required}")

    if missing_recommended:
        print(f"  [!] 缺少推荐字段: {missing_recommended}")

    print("\n正在验证 Cookie...")

    # 验证有效性
    api = BilibiliAPI(config["cookie"])
    result = api.validate_cookie()

    if not result.get("valid"):
        print(f"\n[FAIL] Cookie 无效")
        print(f"错误: {result.get('error')}")

        error = result.get("error", "")
        if "过期" in error or "-101" in error:
            print("\nCookie 已过期，请重新获取")
        print("\n请运行: python scripts/login.py 更新 Cookie")
        return False

    print("\n[OK] Cookie 有效")
    print(f"用户ID: {result.get('mid')}")
    print(f"用户名: {result.get('name')}")

    # 更新用户信息
    config["user_id"] = result.get("mid")
    config["user_name"] = result.get("name")
    config["vip_status"] = result.get("vip_status", False)

    save_config(config)

    last_sync = config.get("last_sync")
    if last_sync:
        sync_time = last_sync[:19] if len(last_sync) > 19 else last_sync
        print(f"\n上次同步: {sync_time}")
    else:
        print("\n尚未同步数据")

    print("\n[OK] 配置已更新")
    return True


# ==================== 帮助信息 ====================

def show_help() -> None:
    """显示帮助信息"""
    print("""
B站登录验证脚本

用法：
    python scripts/login.py              # 扫码登录（推荐）
    python scripts/login.py --cookie     # 手动输入 Cookie
    python scripts/login.py --check      # 验证当前 Cookie

登录方式：
    [推荐] 扫码登录：生成二维码，手机扫码即可登录
    [备选] 手动输入：从浏览器复制完整 Cookie

Cookie必需字段：
    - SESSDATA: 登录凭证
    - bili_jct: CSRF Token

推荐字段（提高稳定性）：
    - buvid3, buvid4: 设备指纹
    - DedeUserID: 用户ID

更多信息：docs/troubleshooting.md
""")


# ==================== 主函数 ====================

def main() -> None:
    """主函数"""
    # 解析参数
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
        sys.exit(0)

    if "--check" in args:
        success = check_existing_cookie()
        sys.exit(0 if success else 1)

    if "--cookie" in args:
        # 强制使用手动输入 Cookie
        print("=== B站登录配置 ===\n")
        cookie_str = get_cookie_from_user()
        if not cookie_str:
            print("\n[FAIL] 未输入 Cookie")
            sys.exit(1)
        # 继续验证流程...
        is_valid, missing_required, missing_recommended, cookies = validate_cookie_format(cookie_str)
        if not is_valid:
            print(f"\n[FAIL] Cookie 缺少必需字段: {missing_required}")
            sys.exit(1)

        display_cookie_info(cookies)
        print("\n正在验证 Cookie...")
        api = BilibiliAPI(cookie_str)
        result = api.validate_cookie()

        if not result.get("valid"):
            print(f"\n[FAIL] Cookie 无效: {result.get('error')}")
            sys.exit(1)

        config = {
            "user_id": result.get("mid"),
            "user_name": result.get("name"),
            "cookie": cookie_str,
            "vip_status": result.get("vip_status", False),
            "last_sync": None,
            "sync_interval_hours": 24
        }
        save_config(config)
        print(f"\n[OK] 配置已保存，用户: {result.get('name')}")
        sys.exit(0)

    # 默认：智能登录流程
    config = load_config()

    if config is not None:
        # 已有配置，验证并可选更新
        print("发现已有配置文件\n")
        success = check_existing_cookie()

        if not success:
            print("\n" + "-" * 50)
            print("是否要重新登录？(y/n)")

            try:
                choice = input().strip().lower()
                if choice == 'y':
                    success = do_login()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                success = False
    else:
        # 无配置，执行登录
        success = do_login()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
