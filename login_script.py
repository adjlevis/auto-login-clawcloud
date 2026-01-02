# 文件名: login_script.py
# 作用: 自动登录 ClawCloud Run，支持 GitHub 账号密码 + 2FA 自动验证

import os
import time
import pyotp  # 用于生成 2FA 验证码
import requests
from playwright.sync_api import sync_playwright


def send_tg_message(text: str):
    """发送 Telegram 消息（不影响主流程）"""
    bot_token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")

    if not bot_token or not chat_id:
        print("ℹ️ 未配置 TG_BOT_TOKEN / TG_CHAT_ID，跳过 TG 通知")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=10
        )
    except Exception as e:
        print(f"⚠️ TG 消息发送失败: {e}")


def run_login():
    # 1. 获取环境变量中的敏感信息
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")

    if not username or not password:
        msg = "❌ ClawCloud 登录失败：缺少 GH_USERNAME 或 GH_PASSWORD"
        print(msg)
        send_tg_message(msg)
        return

    print("🚀 [Step 1] 启动浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        # 2. 访问 ClawCloud 登录页
        target_url = "https://ap-northeast-1.run.claw.cloud/"
        print(f"🌐 [Step 2] 正在访问: {target_url}")
        page.goto(target_url)
        page.wait_for_load_state("networkidle")

        # 3. 点击 GitHub 登录按钮
        print("🔍 [Step 3] 寻找 GitHub 按钮...")
        try:
            login_button = page.locator("button:has-text('GitHub')")
            login_button.wait_for(state="visible", timeout=10000)
            login_button.click()
            print("✅ 按钮已点击")
        except Exception as e:
            print(f"⚠️ 未找到 GitHub 按钮: {e}")

        # 4. GitHub 登录表单
        print("⏳ [Step 4] 等待跳转到 GitHub...")
        try:
            page.wait_for_url(lambda url: "github.com" in url, timeout=15000)
            if "login" in page.url:
                print("🔒 输入账号密码...")
                page.fill("#login_field", username)
                page.fill("#password", password)
                page.click("input[name='commit']")
                print("📤 登录表单已提交")
        except Exception as e:
            print(f"ℹ️ 跳过账号密码填写: {e}")

        # 5. 2FA
        page.wait_for_timeout(3000)
        if "two-factor" in page.url or page.locator("#app_totp").count() > 0:
            print("🔐 [Step 5] 检测到 2FA 双重验证请求！")

            if totp_secret:
                try:
                    totp = pyotp.TOTP(totp_secret)
                    token = totp.now()
                    print(f"生成的验证码: {token}")
                    page.fill("#app_totp", token)
                except Exception as e:
                    msg = f"❌ 2FA 验证码填写失败: {e}"
                    print(msg)
                    send_tg_message(msg)
            else:
                msg = "❌ 致命错误：检测到 2FA 但未配置 GH_2FA_SECRET"
                print(msg)
                send_tg_message(msg)
                exit(1)

        # 6. 授权页
        page.wait_for_timeout(3000)
        if "authorize" in page.url.lower():
            try:
                page.click("button:has-text('Authorize')", timeout=5000)
            except:
                pass

        # 7. 等待最终跳转
        print("⏳ [Step 6] 等待跳转回 ClawCloud 控制台...")
        page.wait_for_timeout(20000)

        final_url = page.url
        page.screenshot(path="login_result.png")

        # 8. 判断是否成功
        is_success = False
        if page.get_by_text("App Launchpad").count() > 0 or page.get_by_text("Devbox").count() > 0:
            is_success = True
        elif "private-team" in final_url or "console" in final_url:
            is_success = True
        elif "signin" not in final_url and "github.com" not in final_url:
            is_success = True

        if is_success:
            msg = f"🎉 ClawCloud 登录成功\n{final_url}"
            print(msg)
            send_tg_message(msg)
        else:
            msg = "❌ ClawCloud 登录失败，请查看 login_result.png"
            print(msg)
            send_tg_message(msg)
            exit(1)

        browser.close()


if __name__ == "__main__":
    run_login()
