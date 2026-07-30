import json
import os
import re
from hashlib import sha256
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
RUNNER_TOKEN = os.getenv("E2E_RUNNER_TOKEN", "runner-demo-token")
ADMIN_TOKEN = os.getenv("E2E_ADMIN_TOKEN", "admin-demo-token")
BROWSER_CHANNEL = os.getenv("E2E_BROWSER_CHANNEL", "chromium")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.set_default_navigation_timeout(60_000)
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
        print("INITIAL BODY:\n", ascii(page.locator("body").inner_text()))
        print("CONSOLE ERRORS:\n", ascii(console_errors))
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
    page.get_by_label("Runner 令牌").fill(RUNNER_TOKEN)
    page.get_by_role("button", name="确认启动").click()
    try:
        page.get_by_text("completed", exact=True).wait_for(timeout=15_000)
    except Exception:
        page.screenshot(path=ARTIFACTS / "incidentlens-live-failure.png", full_page=True)
        print("LIVE BODY:\n", ascii(page.locator("body").inner_text()))
        print("CONSOLE ERRORS:\n", ascii(console_errors))
        print("HTTP ERRORS:\n", ascii(http_errors))
        raise
    page.get_by_role("button", name="需要管理员审批").click()
    page.get_by_label("管理员令牌").fill(ADMIN_TOKEN)
    page.get_by_role("button", name="批准并模拟").click()
    page.get_by_role("button", name="沙箱模拟已完成").wait_for(timeout=15_000)

    imported_excerpt = "No recognized failure signature is present in this sample."
    imported_pack = {
        "id": "browser-imported-incident",
        "title": "浏览器导入的待调查事故",
        "summary": "用于验证无标签事故导入、时间窗和证据不足结果。",
        "scenario_family": "unknown",
        "visibility": "showcase",
        "starts_at": "2026-07-27T09:00:00Z",
        "ends_at": "2026-07-27T10:00:00Z",
        "services": ["customer-service"],
        "evidence": [
            {
                "id": "browser-imported-incident:sample",
                "kind": "log",
                "timestamp": "2026-07-27T09:15:00Z",
                "service": "customer-service",
                "source": "browser/import",
                "locator": "line:1",
                "excerpt": imported_excerpt,
                "content_hash": sha256(imported_excerpt.encode()).hexdigest(),
                "attributes": {"level": "INFO"},
            }
        ],
        "severity": "SEV-3",
    }
    page.get_by_role("button", name="导入事故包").click()
    page.get_by_label("JSON 事故包").set_input_files(
        {
            "name": "browser-imported-incident.json",
            "mimeType": "application/json",
            "buffer": json.dumps(imported_pack, ensure_ascii=False).encode(),
        }
    )
    page.get_by_label("管理员令牌").fill(ADMIN_TOKEN)
    page.get_by_role("button", name="确认导入").click()
    try:
        page.get_by_role("heading", name="浏览器导入的待调查事故").wait_for(
            timeout=15_000
        )
    except Exception:
        print("IMPORT BODY:\n", ascii(page.locator("body").inner_text()))
        print("CONSOLE ERRORS:\n", ascii(console_errors))
        print("HTTP ERRORS:\n", ascii(http_errors))
        raise
    page.get_by_role("button", name="私有目录已解锁").wait_for()
    page.get_by_role("button", name="实时调查").click()
    assert page.get_by_label("开始时间（UTC）").input_value() == "2026-07-27T09:00"
    assert page.get_by_label("结束时间（UTC）").input_value() == "2026-07-27T10:00"
    page.get_by_label("Runner 令牌").fill(RUNNER_TOKEN)
    page.get_by_role("button", name="确认启动").click()
    page.get_by_text("inconclusive", exact=True).wait_for(timeout=15_000)
    page.get_by_role("heading", name="证据不足，无法判定根因").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-inconclusive.png", full_page=True)

    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.get_by_text("浏览器导入的待调查事故", exact=True).count() == 0
    page.get_by_role("button", name="打开私有目录").click()
    page.get_by_label("Runner / Admin 令牌").fill(RUNNER_TOKEN)
    page.get_by_role("button", name="加载私有事故").click()
    page.get_by_text("浏览器导入的待调查事故", exact=True).click()
    page.get_by_role("heading", name="浏览器导入的待调查事故").wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-private-catalog.png", full_page=True)

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

    page.goto("http://127.0.0.1:3000/operations")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Runner 或 Admin 令牌").fill(ADMIN_TOKEN)
    page.get_by_role("button", name="查看调查历史").click()
    page.get_by_role("heading", name="运行与审计").wait_for()
    page.get_by_role("heading", name="调查历史").wait_for()
    page.get_by_text("investigation.created", exact=True).first.wait_for()
    page.locator("button[aria-label^='打开报告']").first.click()
    page.locator(".history-report-panel").wait_for()
    page.locator(".history-hypotheses h4").first.wait_for()
    page.screenshot(path=ARTIFACTS / "incidentlens-operations.png", full_page=True)

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    mobile.goto("http://127.0.0.1:3000")
    mobile.wait_for_load_state("networkidle")
    mobile.get_by_role("heading", name="结算发布后支付超时").wait_for()
    mobile.screenshot(path=ARTIFACTS / "incidentlens-mobile.png", full_page=True)

    mobile.goto("http://127.0.0.1:3000/operations")
    mobile.wait_for_load_state("networkidle")
    mobile.get_by_label("Runner 或 Admin 令牌").fill(RUNNER_TOKEN)
    mobile.get_by_role("button", name="查看调查历史").click()
    mobile.get_by_role("heading", name="调查历史", exact=True).first.wait_for()
    mobile.get_by_text("仅显示你创建的调查", exact=True).wait_for()
    assert mobile.get_by_role("heading", name="审计轨迹").count() == 0
    mobile.screenshot(path=ARTIFACTS / "incidentlens-operations-mobile.png", full_page=True)

    assert not console_errors and not http_errors, (
        f"Browser console errors: {console_errors}; HTTP errors: {http_errors}"
    )
    browser.close()

print(
    "E2E smoke passed: dashboard, private import catalog, bounded live SSE, "
    "inconclusive handling, metric/trace evidence, sandbox approval, evaluations, "
    "recoverable Admin/Runner history, operations ledger, mobile"
)
