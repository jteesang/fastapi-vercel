import replicate, time
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

@app.get("/", tags=["Root"])
async def read_root() -> dict:
    return {
        "message": "fastapi-vercel example"
    }

@app.get("/replicate")
async def get_image():
    output = await call_replicate()
    return output

async def call_replicate():
    path = "https://fiabfmfxtsqxyresiqcw.supabase.co/storage/v1/object/public/playscene/uploads/arts-club-night-dinner.jpeg"
    input = {
        "image": path,
        "clip_model_name": "ViT-L-14/openai"
    }    
    prediction = replicate.predictions.create(
        version="8151e1c9f47e696fa316146a2e35812ccf79cfc9eba05b11c7f450155102af70",
        input= input,
    )

    while prediction.status not in {"succeeded", "failed", "canceled"}:
        prediction.reload()
        time.sleep(2)
        print(f"status : {prediction.status}")

    return prediction.output



