import requests

response = requests.post(
    "http://127.0.0.1:8000/generate",
    json={"prompt": "Hello, Ollama!"}
)

print(response.json())
