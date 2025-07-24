#!/usr/bin/env python3
"""
Simple test server to verify static file serving configuration
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
import uvicorn

app = FastAPI(title="BingX Trading Bot - Test Server")

# Static files configuration - same as in the main web_api.py
frontend_path = Path(__file__).parent / "frontend"
static_path = frontend_path / "static"

print(f"Frontend path: {frontend_path}")
print(f"Static path: {static_path}")
print(f"Frontend exists: {frontend_path.exists()}")
print(f"Static exists: {static_path.exists()}")

# Mount static assets first (more specific routes should come first)
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    print("✅ Mounted /static")

# Test API endpoint
@app.get("/api/test")
async def test_endpoint():
    return {"status": "API working", "message": "FastAPI is serving correctly"}

# Mount the frontend directory last to serve index.html and other files
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    print("✅ Mounted / (frontend)")

if __name__ == "__main__":
    print("🚀 Starting test server...")
    print("📋 Test URLs:")
    print("  - Frontend: http://localhost:8000/")
    print("  - CSS: http://localhost:8000/static/css/styles.css")
    print("  - JS: http://localhost:8000/static/js/app.py")
    print("  - API: http://localhost:8000/api/test")
    print("  - Favicon: http://localhost:8000/favicon.ico")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )