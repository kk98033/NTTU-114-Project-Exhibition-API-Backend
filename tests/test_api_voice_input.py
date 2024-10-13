import os
import requests

# API 伺服器的 URL
BASE_URL = 'http://localhost:6969/voice_chat'

# 測試檔案路徑
audio_file_path = os.path.join('tests', 'test.wav')

def test_voice_input():
    # 構建要發送的多部分表單數據
    with open(audio_file_path, 'rb') as audio_file:
        files = {'file': (audio_file_path, audio_file, 'audio/wav')}
        response = requests.post(BASE_URL, files=files)
        
        if response.status_code == 200:
            print("Response from /voice_chat:")
            print(response.text)
        else:
            print(f"Error {response.status_code}: {response.text}")

if __name__ == '__main__':
    print("Current working directory:", os.getcwd())
    print("Testing /voice_chat endpoint with audio input...")
    test_voice_input()
