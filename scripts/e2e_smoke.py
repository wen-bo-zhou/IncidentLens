import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="chromium")
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    console_errors: list[str] = []
    http_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(f"{message.text} @ {message.location}")
        if message.type == "error"
        else None,
    )
    page.on(
        "response",
        lambda response: http_errors.append(f"{response.status} {response.url}")
        if response.status >= 400
        else None,
    )

    page.goto("http://127.0.0.1:3000")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=ARTIFACTS / "incidentlens-initial.png", full_page=True)
    try:
        page.get_by_role("heading", name="结算发布后支付超时").wait_for(timeout=15_000)
    except Exception:
        print("INITIAL BODY:\n", page.locator("body").inner_text())
        print("CONSOLE ERRORS:\n", console_errors)
        raise
    page.get_by_text("事故因果时间线").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-desktop.png", full_page=True)

    page.get_by_role("button", name=re.compile("查看证据 .*:latency$")).click()
    page.get_by_label("指标趋势图").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-metric.png", full_page=True)
    page.get_by_role("button", name="关闭证据详情").click()

    page.get_by_role("button", name=re.compile("查看证据 .*:trace$")).click()
    page.get_by_label("Trace 瀑布图").wait_for()
    page.get_by_role("button", name="关闭证据详情").click()

    page.get_by_role("button", name="实时调查").click()
    page.get_by_label("Runner 令牌").fill("runner-demo-token")
    page.get_by_role("button", name="确认启动").click()
    page.get_by_text("completed", exact=True).wait_for(timeout=15_000)
    page.get_by_role("button", name="需要管理员审批").click()
    page.get_by_label("管理员令牌").fill("admin-demo-token")
    page.get_by_role("button", name="批准并模拟").click()
    page.get_by_role("button", name="沙箱模拟已完成").wait_for(timeout=15_000)

    page.get_by_role("button", name=re.compile("库存服务连接池耗尽")).click()
    page.get_by_role("heading", name="库存服务连接池耗尽").wait_for()
    page.get_by_role("button", name=re.compile("^查看证据")).first.click()
    page.get_by_role("dialog", name="证据详情").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-evidence.png", full_page=True)
    page.get_by_role("button", name="关闭证据详情").click()

    page.goto("http://127.0.0.1:3000/evaluations")
    page.wait_for_load_state("networkidle")
    page.get_by_role("heading", name="调查质量评测").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-evaluations.png", full_page=True)

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    mobile.goto("http://127.0.0.1:3000")
    mobile.wait_for_load_state("networkidle")
    mobile.get_by_role("heading", name="结算发布后支付超时").wait_for()
    mobile.screenshot(path=ARTIFACTS / "incidentlens-mobile.png", full_page=True)

    assert not console_errors, (
        f"Browser console errors: {console_errors}; HTTP errors: {http_errors}"
    )
    browser.close()

print(
    "E2E smoke passed: dashboard, live SSE run, metric/trace evidence, "
    "sandbox approval, evaluations, mobile"
)
