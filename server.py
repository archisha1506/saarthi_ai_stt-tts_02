import asyncio
import websockets

import os
import numpy as np
import edge_tts
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from faster_whisper import WhisperModel


load_dotenv()
# -----------------------------
# Load models (only once)
# -----------------------------
print("Loading Whisper model...")
model = WhisperModel("base", device="cpu", compute_type="int8")
# stt_model = whisper.load_model("base")

# -----------------------------
# Dummy LangGraph (replace later)
# -----------------------------
def call_langgraph(user_text):
    print("Sending to LangGraph:", user_text)
    
    # Replace this with your real LangGraph
    response = f"testing the pipeline without external langgraph -> {user_text}"
    
    return response

llm= ChatGroq(
    model='llama-3.3-70b-versatile'
)    

# -----------------------------
# Convert audio buffer to text
# -----------------------------
def speech_to_text(audio_bytes):
    temp_file = "temp_input.webm"
    with open(temp_file, "wb") as f:
        f.write(audio_bytes)
        
    result = stt_model.transcribe(temp_file)
    return result["text"]

# -----------------------------
# Convert text to audio
# -----------------------------
async def text_to_speech(text, output_file):
    communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
    await communicate.save(output_file)
audio_text=""
# -----------------------------
# WebSocket handler
# -----------------------------
async def handler(websocket):
    print("Client connected ✅")

    audio_buffer = []

    try:
        while True:
            data = await websocket.recv()

            # -----------------------------
            # If frontend sends "END"
            # -----------------------------
            if isinstance(data, str) and data == "END":
                print("End of speech detected 🎤")

                # Get audio bytes
                audio_bytes = b''.join(audio_buffer)

                # Clear buffer
                audio_buffer = []

                # -----------------------------
                # STT
                # -----------------------------
                text = speech_to_text(audio_bytes)
                print("User said:", text)
                audio_text=llm.invoke(text)

                # Send transcript (optional)
                await websocket.send(f"TRANSCRIPT:{text}")

                # -----------------------------
                # LangGraph
                # -----------------------------
                response_text = call_langgraph(audio_text)
                print("AI response:", response_text)

                # -----------------------------
                # TTS
                # -----------------------------
                output_file = "output.mp3"
                await text_to_speech(response_text, output_file)

                # -----------------------------
                # Send audio back in chunks
                # -----------------------------
                with open(output_file, "rb") as f:
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        await websocket.send(chunk)

                # Signal end of audio
                await websocket.send("AUDIO_END")

            else:
                # -----------------------------
                # Receive audio chunk
                # -----------------------------
                audio_buffer.append(data)

                # -----------------------------
                # Partial transcription (Every 8 chunks ~ 2 seconds)
                # -----------------------------
                if len(audio_buffer) % 8 == 0:
                    audio_bytes = b''.join(audio_buffer)
                    partial_text = speech_to_text(audio_bytes)
                    print(f"Partial text (2s update): {partial_text}")
                    await websocket.send(f"PARTIAL:{partial_text}")

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected ❌")


# -----------------------------
# Start server
# -----------------------------
async def main():
    print("Starting WebSocket server 🚀")
    async with websockets.serve(handler, "localhost", 8767):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())