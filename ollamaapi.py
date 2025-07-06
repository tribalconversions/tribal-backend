from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import subprocess

app = FastAPI()

# Allow requests from your frontend (adjust in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

@app.post("/generate")
async def generate(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")

    try:
        # Run ollama CLI with prompt, timeout to prevent hangs
        result = subprocess.run(
            ['ollama', 'run', 'mistral', '--prompt', prompt],
            capture_output=True,
            text=True,
            timeout=15
        )
        output = result.stdout.strip()
    except subprocess.TimeoutExpired:
        output = "Error: Timeout expired when calling Ollama."

    return {"response": output}
