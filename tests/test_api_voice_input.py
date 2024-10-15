import os
import requests
import subprocess
from io import BytesIO

# API 伺服器的 URL
BASE_URL = 'http://localhost:6969/voice_chat'

# 測試檔案路徑
audio_file_path = os.path.join(os.getcwd(), 'tests', 'test.wav')  # 獲取完整的測試音頻文件路徑
output_mp3_path = os.path.join(os.getcwd(), 'tests', 'output.mp3')  # 獲取完整的 MP3 輸出路徑
output_ogg_path = os.path.join(os.getcwd(), 'tests', 'output.ogg')  # 獲取完整的 OGG 輸出路徑

# 手動指定 ffmpeg 的完整路徑
ffmpeg_path = r'ffmpeg\bin\ffmpeg.exe'  # 請確保此路徑正確

def test_voice_input():
    # 檢查測試音頻文件是否存在
    if not os.path.exists(audio_file_path):
        print(f"Error: Test audio file {audio_file_path} not found.")
        return
    
    print(f"Audio file found: {audio_file_path}")

    # 構建要發送的多部分表單數據
    try:
        with open(audio_file_path, 'rb') as audio_file:
            files = {'file': (audio_file_path, audio_file, 'audio/wav')}
            print("Sending POST request to API...")
            response = requests.post(BASE_URL, files=files, stream=True)  # 使用 stream=True 來處理流式響應
    except Exception as e:
        print(f"Error occurred while sending request: {e}")
        return
    
    print(f"Response status code: {response.status_code}")
    
    if response.status_code == 200:
        print("Response from /voice_chat received. Saving audio...")

        # 保存流式響應為 OGG 文件
        try:
            with open(output_ogg_path, 'wb') as ogg_file:
                for chunk in response.iter_content(chunk_size=1024):  # 每次讀取 1024 bytes
                    if chunk:
                        ogg_file.write(chunk)
            print(f"Audio saved as {output_ogg_path}")
        except Exception as e:
            print(f"Error occurred while saving OGG file: {e}")
            return

        # 檢查 OGG 文件是否正確保存
        if not os.path.exists(output_ogg_path):
            print(f"Error: OGG file {output_ogg_path} not saved properly.")
            return
        
        # 使用 ffmpeg 將 OGG 轉換為 MP3
        try:
            print("Starting ffmpeg conversion...")
            result = subprocess.run([
                ffmpeg_path, '-i', output_ogg_path, output_mp3_path
            ], check=True, capture_output=True, text=True)
            print(f"FFmpeg output: {result.stdout}")
            print(f"Audio converted and saved as {output_mp3_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error occurred during audio conversion: {e}")
            print(f"FFmpeg error output: {e.stderr}")
        except FileNotFoundError:
            print(f"Error: ffmpeg not found. Please ensure ffmpeg is correctly installed and the path is correct.")
    else:
        print(f"Error: API returned status code {response.status_code}")
        print(f"Response text: {response.text}")

if __name__ == '__main__':
    print(f"Using ffmpeg at: {ffmpeg_path}")
    print("Current working directory:", os.getcwd())
    print("Testing /voice_chat endpoint with audio input...")
    test_voice_input()
