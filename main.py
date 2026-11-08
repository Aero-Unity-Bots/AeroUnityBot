import threading
import uvicorn
import os
from bot import bot

def run_fastapi():
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_fastapi, daemon=True)
    server_thread.start()

    print("🚀 Starting Aero_Unity Telegram Bot & Stream Server...")
    bot.run()
