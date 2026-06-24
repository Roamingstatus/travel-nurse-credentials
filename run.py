import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
