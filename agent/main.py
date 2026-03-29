import asyncio
import json
import logging
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from browser_manager import BrowserManager, DEFAULT_VIEWPORT_WIDTH, DEFAULT_VIEWPORT_HEIGHT
from gemini_session import GeminiSession
from system_prompt import SYSTEM_PROMPT
from tools import TOOL_DECLARATIONS, build_tool_mapping

load_dotenv()

logging.basicConfig(level=logging.INFO)
logging.getLogger("gemini_session").setLevel(logging.DEBUG)
logging.getLogger(__name__).setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("MODEL", "gemini-3.1-flash-live-preview")
VIEWPORT_W = int(os.getenv("VIEWPORT_WIDTH", str(DEFAULT_VIEWPORT_WIDTH)))
VIEWPORT_H = int(os.getenv("VIEWPORT_HEIGHT", str(DEFAULT_VIEWPORT_HEIGHT)))
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"

IMG_PREFIX = b"IMG:"
SCREENSHOT_INTERVAL = 0.5  # 2 FPS

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/api/config")
async def get_config():
    return JSONResponse({
        "viewport_width": VIEWPORT_W,
        "viewport_height": VIEWPORT_H,
        "model": MODEL,
        "has_api_key": bool(GEMINI_API_KEY),
    })


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    if not GEMINI_API_KEY:
        await websocket.send_json({"type": "error", "error": "GEMINI_API_KEY not set. Create a .env file with your key."})
        await websocket.close()
        return

    browser_mgr = BrowserManager(headless=HEADLESS, viewport_width=VIEWPORT_W, viewport_height=VIEWPORT_H)
    try:
        await browser_mgr.start()
    except Exception as e:
        await websocket.send_json({"type": "error", "error": f"Failed to start browser: {e}"})
        await websocket.close()
        return

    ws_open = True

    audio_input_queue = asyncio.Queue()
    video_input_queue = asyncio.Queue()
    text_input_queue = asyncio.Queue()

    tool_mapping = build_tool_mapping(browser_mgr)

    gemini_client = GeminiSession(
        api_key=GEMINI_API_KEY,
        model=MODEL,
        input_sample_rate=16000,
        system_instruction=SYSTEM_PROMPT,
        tools=TOOL_DECLARATIONS,
        tool_mapping=tool_mapping,
    )

    async def audio_output_callback(data):
        if not ws_open:
            return
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass

    async def audio_interrupt_callback():
        if not ws_open:
            return
        try:
            await websocket.send_json({"type": "interrupted"})
        except Exception:
            pass

    async def screenshot_loop():
        """Capture screenshots and send to both Gemini and the frontend."""
        try:
            while ws_open:
                if not browser_mgr.is_running:
                    await asyncio.sleep(1)
                    continue
                jpeg_bytes = await browser_mgr.get_screenshot_bytes()
                if jpeg_bytes is None:
                    await asyncio.sleep(1)
                    continue
                # Send to Gemini as video input
                await video_input_queue.put(jpeg_bytes)
                # Send to frontend for live preview
                if ws_open:
                    try:
                        await websocket.send_bytes(IMG_PREFIX + jpeg_bytes)
                    except Exception:
                        break
                await asyncio.sleep(SCREENSHOT_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Screenshot loop error: {e}")

    async def receive_from_client():
        """Route incoming messages: binary=audio, JSON=text/navigate/config."""
        nonlocal ws_open
        try:
            while True:
                message = await websocket.receive()
                if message.get("bytes"):
                    await audio_input_queue.put(message["bytes"])
                elif message.get("text"):
                    text = message["text"]
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        await text_input_queue.put(text)
                        continue

                    msg_type = payload.get("type") if isinstance(payload, dict) else None

                    if msg_type == "text":
                        await text_input_queue.put(payload["text"])
                    elif msg_type == "navigate":
                        # Direct URL navigation from the frontend URL bar
                        url = payload.get("url", "").strip()
                        if url:
                            result = await browser_mgr.navigate(url)
                            try:
                                await websocket.send_json({"type": "nav_result", **result})
                            except Exception:
                                pass
                    else:
                        await text_input_queue.put(text)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error receiving from client: {e}")
        finally:
            ws_open = False

    screenshot_task = asyncio.create_task(screenshot_loop())
    receive_task = asyncio.create_task(receive_from_client())

    try:
        async for event in gemini_client.start_session(
            audio_input_queue=audio_input_queue,
            video_input_queue=video_input_queue,
            text_input_queue=text_input_queue,
            audio_output_callback=audio_output_callback,
            audio_interrupt_callback=audio_interrupt_callback,
        ):
            if event and ws_open:
                try:
                    await websocket.send_json(event)
                except Exception:
                    break
    except Exception as e:
        logger.error(f"Session error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        ws_open = False
        screenshot_task.cancel()
        receive_task.cancel()
        # Wait for tasks to finish before closing browser
        for task in [screenshot_task, receive_task]:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await browser_mgr.stop()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Session cleaned up")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="localhost", port=port)
