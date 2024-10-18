import openai
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve the API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Make the API call to generate speech
response = openai.audio.speech.create(
    model="tts-1",  # or "tts-1-hd"
    voice="nova",   # Use lowercase "nova"
    input="你好，謝謝，小籠包!"  # Your input text
)

# Save the output to a file
with open("output_tts.wav", "wb") as f:
    f.write(response.read())
