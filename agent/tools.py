from google.genai import types


def _decl(name, description, properties, required=None):
    """Helper to create a FunctionDeclaration."""
    params = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=params,
    )


TOOL_DECLARATIONS = [
    types.Tool(function_declarations=[
        _decl(
            "navigate",
            "Navigate the browser to a specific URL. Use full URLs including https://.",
            {
                "url": {"type": "string", "description": "The full URL to navigate to (e.g. https://www.google.com)"}
            },
            required=["url"],
        ),
        _decl(
            "click",
            "Click at a specific position on the page. Specify x,y pixel coordinates based on what you see in the screenshot. The screenshot is 1280x720 pixels.",
            {
                "x": {"type": "integer", "description": "X pixel coordinate (0-1280)"},
                "y": {"type": "integer", "description": "Y pixel coordinate (0-720)"},
                "click_type": {"type": "string", "enum": ["single", "double", "right"], "description": "Type of click. Default is single."},
            },
            required=["x", "y"],
        ),
        _decl(
            "type_text",
            "Type text into the currently focused element or at specific coordinates. If coordinates are provided, clicks there first. Use press_enter=true to submit forms.",
            {
                "text": {"type": "string", "description": "The text to type"},
                "x": {"type": "integer", "description": "Optional X coordinate to click before typing"},
                "y": {"type": "integer", "description": "Optional Y coordinate to click before typing"},
                "clear_first": {"type": "boolean", "description": "Clear the field before typing. Default false."},
                "press_enter": {"type": "boolean", "description": "Press Enter after typing. Default false."},
            },
            required=["text"],
        ),
        _decl(
            "scroll",
            "Scroll the page up or down to see content not visible in the current screenshot.",
            {
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Direction to scroll"},
                "amount": {"type": "integer", "description": "Number of scroll clicks, each ~100px. Default 3."},
            },
            required=["direction"],
        ),
        _decl(
            "go_back",
            "Go back to the previous page in browser history.",
            {},
        ),
        _decl(
            "go_forward",
            "Go forward to the next page in browser history.",
            {},
        ),
        _decl(
            "wait",
            "Wait for a specified number of seconds for the page to load dynamic content.",
            {
                "seconds": {"type": "number", "description": "Seconds to wait (0.5-10). Default 2."},
            },
        ),
        _decl(
            "get_page_text",
            "Extract all visible text from the current page. Use when you need precise text, prices, or data that's hard to read in screenshots.",
            {},
        ),
        _decl(
            "press_key",
            "Press a keyboard key or combination (e.g. Enter, Tab, Escape, Control+a, ArrowDown).",
            {
                "key": {"type": "string", "description": "Key to press (e.g. 'Enter', 'Tab', 'Escape', 'Control+a')"},
            },
            required=["key"],
        ),
        _decl(
            "hover",
            "Move the mouse to hover over a position to reveal tooltips, dropdowns, or hover states.",
            {
                "x": {"type": "integer", "description": "X pixel coordinate"},
                "y": {"type": "integer", "description": "Y pixel coordinate"},
            },
            required=["x", "y"],
        ),
        _decl(
            "get_accessibility_tree",
            "Get a simplified accessibility tree showing interactive elements (links, buttons, inputs) with their roles and names. Use when screenshots are ambiguous.",
            {},
        ),
    ])
]


def build_tool_mapping(browser_mgr):
    """Build a dict mapping tool names to async callables on the BrowserManager."""
    return {
        "navigate": browser_mgr.navigate,
        "click": browser_mgr.click,
        "type_text": browser_mgr.type_text,
        "scroll": browser_mgr.scroll,
        "go_back": browser_mgr.go_back,
        "go_forward": browser_mgr.go_forward,
        "wait": browser_mgr.wait,
        "get_page_text": browser_mgr.get_page_text,
        "press_key": browser_mgr.press_key,
        "hover": browser_mgr.hover,
        "get_accessibility_tree": browser_mgr.get_accessibility_tree,
    }
