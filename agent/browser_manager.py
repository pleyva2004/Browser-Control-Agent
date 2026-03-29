import asyncio
import logging

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 720
ACTION_TIMEOUT = 15000  # ms


class BrowserManager:
    """Manages a headless Playwright browser for the agent to control."""

    def __init__(self, headless=True, viewport_width=DEFAULT_VIEWPORT_WIDTH, viewport_height=DEFAULT_VIEWPORT_HEIGHT):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None
        self._stopped = False

    async def start(self, url="https://www.google.com"):
        """Launch browser and navigate to initial URL."""
        self._stopped = False
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.page = await self._context.new_page()
        await Stealth().apply_stealth_async(self.page)
        self.page.set_default_timeout(ACTION_TIMEOUT)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=ACTION_TIMEOUT)
        logger.info(f"Browser started at {url}")

    async def stop(self):
        """Close browser and clean up. Safe to call multiple times."""
        if self._stopped:
            return
        self._stopped = True
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._playwright = None
        self.page = None
        logger.info("Browser stopped")

    @property
    def is_running(self):
        return self.page is not None and not self._stopped

    async def get_screenshot_bytes(self):
        """Capture current page as JPEG bytes."""
        if not self.is_running:
            return None
        return await self.page.screenshot(type="jpeg", quality=75)

    async def get_page_url(self):
        return self.page.url

    async def get_page_title(self):
        return await self.page.title()

    # --- Browser action methods ---

    async def _page_info(self):
        """Return current url + title for action results."""
        return {"url": self.page.url, "title": await self.page.title()}

    async def navigate(self, url):
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=ACTION_TIMEOUT)
            return {"status": "ok", **(await self._page_info())}
        except PlaywrightTimeout:
            return {"status": "error", "message": f"Navigation to {url} timed out after {ACTION_TIMEOUT // 1000}s"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def click(self, x, y, click_type="single"):
        try:
            x, y = int(x), int(y)
            if click_type == "double":
                await self.page.mouse.dblclick(x, y)
            elif click_type == "right":
                await self.page.mouse.click(x, y, button="right")
            else:
                await self.page.mouse.click(x, y)
            await asyncio.sleep(0.3)
            return {"status": "ok", **(await self._page_info())}
        except PlaywrightTimeout:
            return {"status": "error", "message": f"Click at ({x},{y}) timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def type_text(self, text, x=None, y=None, clear_first=False, press_enter=False):
        try:
            if x is not None and y is not None:
                await self.page.mouse.click(int(x), int(y))
                await asyncio.sleep(0.2)
            if clear_first:
                await self.page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
            await self.page.keyboard.type(str(text), delay=50)
            if press_enter:
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Enter")
            await asyncio.sleep(0.3)
            return {"status": "ok", **(await self._page_info())}
        except PlaywrightTimeout:
            return {"status": "error", "message": "Typing timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def scroll(self, direction, amount=3):
        try:
            amount = int(amount)
            delta_y = amount * 100 if direction == "down" else -(amount * 100)
            await self.page.mouse.wheel(0, delta_y)
            await asyncio.sleep(0.3)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def go_back(self):
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=ACTION_TIMEOUT)
            return {"status": "ok", **(await self._page_info())}
        except PlaywrightTimeout:
            return {"status": "error", "message": "Go back timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def go_forward(self):
        try:
            await self.page.go_forward(wait_until="domcontentloaded", timeout=ACTION_TIMEOUT)
            return {"status": "ok", **(await self._page_info())}
        except PlaywrightTimeout:
            return {"status": "error", "message": "Go forward timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def wait(self, seconds=2.0):
        seconds = min(float(seconds), 10.0)
        await asyncio.sleep(seconds)
        return {"status": "ok", "waited": seconds}

    async def get_page_text(self):
        try:
            text = await self.page.inner_text("body")
            truncated = len(text) > 4000
            return {"status": "ok", "text": text[:4000], "truncated": truncated}
        except PlaywrightTimeout:
            return {"status": "error", "message": "Extracting page text timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def press_key(self, key):
        try:
            await self.page.keyboard.press(str(key))
            await asyncio.sleep(0.2)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def hover(self, x, y):
        try:
            await self.page.mouse.move(int(x), int(y))
            await asyncio.sleep(0.3)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_accessibility_tree(self):
        try:
            snapshot = await self.page.accessibility.snapshot()
            if not snapshot:
                return {"status": "ok", "tree": "No accessibility tree available"}
            tree_text = _format_a11y_tree(snapshot)
            truncated = len(tree_text) > 4000
            return {"status": "ok", "tree": tree_text[:4000], "truncated": truncated}
        except PlaywrightTimeout:
            return {"status": "error", "message": "Accessibility tree snapshot timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def _format_a11y_tree(node, indent=0):
    """Format accessibility tree into readable text, focusing on interactive elements."""
    lines = []
    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")

    interactive_roles = {
        "link", "button", "textbox", "searchbox", "combobox",
        "checkbox", "radio", "tab", "menuitem", "option",
        "heading", "img", "list", "listitem",
    }

    if role in interactive_roles or indent == 0:
        prefix = "  " * indent
        desc = f"{prefix}[{role}]"
        if name:
            desc += f' "{name}"'
        if value:
            desc += f" value={value}"
        lines.append(desc)

    for child in node.get("children", []):
        lines.extend(_format_a11y_tree(child, indent + 1).split("\n"))

    return "\n".join(line for line in lines if line.strip())
