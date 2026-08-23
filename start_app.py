import os
import sys
import uvicorn

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")

def start_backend(host="127.0.0.1", port=8000, reload=True):
    sys.path.insert(0, BACKEND_DIR)
    os.chdir(BACKEND_DIR)
    print("\n=======================================================")
    print(f" Starting MPLADS AI FastAPI Backend on http://{host}:{port}")
    print(f" Interactive API Docs: http://{host}:{port}/docs")
    print("=======================================================\n")
    uvicorn.run("main:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    start_backend()
