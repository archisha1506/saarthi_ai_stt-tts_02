import asyncio
import io
import websockets
# NOTE: This is the WebSocket-based implementation (web browser frontend)
# For a direct PyAudio implementation (microphone input, CLI-based), see: server_pyaudio.py

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
stt_model = WhisperModel("base", device="cpu", compute_type="int8")
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
    # Use io.BytesIO to avoid saving a temporary file to disk
    audio_buffer = io.BytesIO(audio_bytes)
    segments, info = stt_model.transcribe(audio_buffer, beam_size=5)
    text = "".join([segment.text for segment in segments])
    return text.strip()

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
                # STT (In-Memory)
                # -----------------------------
                text = speech_to_text(audio_bytes)
                print("User said:", text)
                await websocket.send(f"TRANSCRIPT:{text}")

                # -----------------------------
                # Streaming LLM -> TTS Pipeline
                # -----------------------------
                sentence_buffer = ""
                
                print("Starting LLM stream...")
                for chunk in llm.stream(text):
                    content = chunk.content
                    if not content:
                        continue
                        
                    sentence_buffer += content
                    
                    # Detect sentence end to trigger early TTS
                    if any(p in content for p in [".", "?", "!"]):
                        clean_sentence = sentence_buffer.strip()
                        if clean_sentence:
                            print(f"Streaming sentence: {clean_sentence}")
                            await websocket.send(f"AI_RESPONSE:{clean_sentence}")
                            
                            # Stream TTS immediately for this sentence
                            communicate = edge_tts.Communicate(clean_sentence, "en-US-AriaNeural")
                            async for audio_chunk in communicate.stream():
                                if audio_chunk["type"] == "audio":
                                    await websocket.send(audio_chunk["data"])
                            
                            # Signal end of THIS sentence audio
                            await websocket.send("AUDIO_END")
                        
                        sentence_buffer = ""

                # Handle final lingering text
                if sentence_buffer.strip():
                    clean_sentence = sentence_buffer.strip()
                    print(f"Streaming final sentence: {clean_sentence}")
                    await websocket.send(f"AI_RESPONSE:{clean_sentence}")
                    communicate = edge_tts.Communicate(clean_sentence, "en-US-AriaNeural")
                    async for audio_chunk in communicate.stream():
                        if audio_chunk["type"] == "audio":
                            await websocket.send(audio_chunk["data"])
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