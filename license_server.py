# license_server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Example database (in-memory for now)
VALID_LICENSES = {
    "john-smith": "XYZ123",
    "client-two": "ABC789"
}

class LicenseCheck(BaseModel):
    client_id: str
    license_key: str

@app.post("/verify-license")
def verify_license(data: LicenseCheck):
    if VALID_LICENSES.get(data.client_id) == data.license_key:
        return { "status": "valid" }
    raise HTTPException(status_code=403, detail="invalid")