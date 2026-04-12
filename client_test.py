import asyncio
import websockets
import pyaudio
import wave
import os

# Audio settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # Whisper expects 16kHz
RECORD_SECONDS = 25  # Record for 15 seconds

async def record_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

    print("Recording...")
    frames = []

    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
 
    print("Recording chunk:", len(data))
    print("Recording finished.")
    stream.stop_stream()
    stream.close()
    p.terminate()

    return b''.join(frames)

async def client():
    uri = "ws://localhost:8767"
    async with websockets.connect(uri) as websocket:
        print("Connected to server.")

        # Record audio
        audio_data = await record_audio()

        # Send audio in chunks
        for i in range(0, len(audio_data), CHUNK):
            chunk = audio_data[i:i+CHUNK]
            await websocket.send(chunk)

        # Send end signal
        await websocket.send("END")
        print("Sent audio data.")

        # Receive transcript
        response = await websocket.recv()
        if response.startswith("TRANSCRIPT:"):
            transcript = response[11:]
            print("Transcript:", transcript)

        # Receive audio
        audio_chunks = []
        while True:
            data = await websocket.recv()
            if data == "AUDIO_END":
                break
            audio_chunks.append(data)

        # Save and play audio
        with open("response.mp3", "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)

        print("Saved response.mp3")
        import platform
        if platform.system() == "Darwin":
            os.system("afplay response.mp3")  # Play on Mac
        elif platform.system() == "Windows":
            os.system("start response.mp3")  # Play on Windows
        else:
            os.system("aplay response.mp3")  # Play on Linux

asyncio.run(client())
