import os
import pyaudio
import numpy as np
import wave
import threading
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from langchain_groq import ChatGroq
import edge_tts
import asyncio
import platform

load_dotenv()

# =============================================
# CONFIGURATION
# =============================================
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # Whisper expects 16kHz
SILENCE_THRESHOLD = 500  # Noise floor
SILENCE_DURATION = 2.0  # Seconds of silence to stop recording

# =============================================
# INITIALIZE MODELS
# =============================================
print("[*] Loading Whisper model (base, int8)...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

print("[*] Initializing LLM (Groq - llama-3.3-70b)...")
llm = ChatGroq(model='llama-3.3-70b-versatile')

# =============================================
# HELPER FUNCTIONS
# =============================================
def is_silent(audio_chunk, threshold=SILENCE_THRESHOLD):
    """Detect if audio chunk is silent."""
    audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
    return np.abs(audio_array).mean() < threshold

def record_audio_with_silence_detection():
    """
    Record audio from microphone until silence is detected.
    Returns raw audio bytes.
    """
    p = pyaudio.PyAudio()
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("\n🎤 Listening... (speak now, stop after 2s of silence)")
    frames = []
    silent_chunks = 0
    silent_chunks_needed = int(SILENCE_DURATION * RATE / CHUNK)
    
    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            
            if is_silent(data):
                silent_chunks += 1
                if silent_chunks >= silent_chunks_needed:
                    print("✓ Silence detected. Processing...")
                    break
            else:
                silent_chunks = 0  # Reset counter if sound detected
    
    except KeyboardInterrupt:
        print("\n[!] Recording interrupted by user.")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
    
    audio_bytes = b''.join(frames)
    return audio_bytes

def speech_to_text(audio_bytes):
    """Convert audio bytes to text using Faster Whisper."""
    # Save temporarily
    temp_file = "temp_audio.wav"
    
    # Write as WAV file
    with wave.open(temp_file, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(RATE)
        wav_file.writeframes(audio_bytes)
    
    # Transcribe
    segments, info = whisper_model.transcribe(temp_file, language="en")
    text = " ".join([segment.text for segment in segments])
    
    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)
    
    return text.strip()

async def text_to_speech(text):
    """Convert text to speech and save as MP3."""
    output_file = "response.mp3"
    
    print(f"🔊 Converting to speech...")
    communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
    await communicate.save(output_file)
    
    return output_file

def play_audio(file_path):
    """Play audio file cross-platform."""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        os.system(f"afplay {file_path}")
    elif system == "Windows":
        os.system(f"start {file_path}")
    elif system == "Linux":
        os.system(f"aplay {file_path}")
    else:
        print(f"[!] Platform '{system}' not supported for audio playback")

# =============================================
# MAIN PIPELINE
# =============================================

async def process_audio():
    """Process audio: STT -> LLM -> TTS -> Play"""
    try:
        # 1. Record audio with silence detection
        audio_bytes = record_audio_with_silence_detection()
        
        if not audio_bytes:
            print("[!] No audio recorded.")
            return
        
        # 2. Convert speech to text
        print("📝 Transcribing audio...")
        user_text = speech_to_text(audio_bytes)
        
        if not user_text:
            print("[!] Could not transcribe audio.")
            return
        
        print(f"\n👤 You said: {user_text}")
        
        # 3. Get LLM response
        print("🤖 Generating response...")
        response = llm.invoke(user_text)
        
        if hasattr(response, 'content'):
            response_text = response.content
        else:
            response_text = str(response)
        
        print(f"🤖 AI said: {response_text}\n")
        
        # 4. Convert response to speech
        audio_file = await text_to_speech(response_text)
        
        # 5. Play audio
        print("▶️  Playing response...")
        play_audio(audio_file)
        
    except Exception as e:
        print(f"[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()

async def main():
    """Main conversation loop."""
    print("=" * 50)
    print("  Saarthi AI - PyAudio STT/TTS Pipeline")
    print("=" * 50)
    
    while True:
        try:
            await process_audio()
            
            # Ask user if they want to continue
            response = input("\n🔄 Continue? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("👋 Goodbye!")
                break
                
        except KeyboardInterrupt:
            print("\n👋 Interrupted by user. Goodbye!")
            break
        except Exception as e:
            print(f"[!] Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())