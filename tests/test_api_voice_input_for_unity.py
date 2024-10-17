import os
import requests
import subprocess
import base64
from requests_toolbelt.multipart import decoder

# API 伺服器的 URL
BASE_URL = 'http://localhost:6969/voice_chat'

# 測試檔案路徑
audio_file_path = os.path.join(os.getcwd(), 'tests', 'test.wav')  # 測試音頻文件路徑
output_wav_path = os.path.join(os.getcwd(), 'tests', 'output.wav')  # WAV 輸出路徑

# 手動指定 ffmpeg 的完整路徑
ffmpeg_path = r'ffmpeg\bin\ffmpeg.exe'  # 請確保此路徑正確

def parse_multipart_response(response):
    """
    使用 requests_toolbelt 的 MultipartDecoder 解析多部分表單數據回應，
    提取 JSON 和 Base64 音訊文件。
    """
    content_type = response.headers.get('Content-Type', '')
    print(f"Content-Type: {content_type}")

    if 'multipart/' not in content_type:
        print("Error: Response is not multipart.")
        return None, None

    try:
        multipart_data = decoder.MultipartDecoder.from_response(response)
    except Exception as e:
        print(f"Error initializing MultipartDecoder: {e}")
        return None, None

    json_data = None
    audio_base64 = None

    print(f"Number of parts in multipart response: {len(multipart_data.parts)}")

    for i, part in enumerate(multipart_data.parts):
        part_content_type = part.headers.get(b'Content-Type', b'').decode('utf-8')
        disposition = part.headers.get(b'Content-Disposition', b'').decode('utf-8')
        print(f"\nPart {i+1}:")
        print(f"  Content-Type: {part_content_type}")
        print(f"  Content-Disposition: {disposition}")

        if 'application/json' in part_content_type:
            try:
                json_data = part.text
                print(f"  Received JSON: {json_data}")
            except Exception as e:
                print(f"  Error reading JSON part: {e}")
        elif 'audio/wav' in part_content_type:  # 修改檢查點為 'audio/wav'
            try:
                audio_base64 = part.text
                print(f"  Received audio data of type {part_content_type}")
            except Exception as e:
                print(f"  Error reading audio part: {e}")

    return json_data, audio_base64

def test_voice_input():
    # 檢查測試音頻文件是否存在
    if not os.path.exists(audio_file_path):
        print(f"Error: Test audio file {audio_file_path} not found.")
        return

    print(f"Audio file found: {audio_file_path}")

    # 構建要發送的多部分表單數據
    try:
        with open(audio_file_path, 'rb') as audio_file:
            files = {'file': ('test.wav', audio_file, 'audio/wav')}
            print("Sending POST request to API...")
            response = requests.post(BASE_URL, files=files)
    except Exception as e:
        print(f"Error occurred while sending request: {e}")
        return

    print(f"Response status code: {response.status_code}")

    if response.status_code == 200:
        print("Response from /voice_chat received.")

        json_data, audio_base64 = parse_multipart_response(response)

        if json_data is None or audio_base64 is None:
            print("Error: Failed to parse multipart response.")
            return

        # 將 Base64 音訊數據解碼並保存為 WAV 文件
        try:
            audio_bytes = base64.b64decode(audio_base64)
            with open(output_wav_path, 'wb') as wav_file:
                wav_file.write(audio_bytes)
            print(f"Audio saved as {output_wav_path}")
        except Exception as e:
            print(f"Error occurred while decoding/saving WAV file: {e}")
            return

        # 檢查 WAV 文件是否正確保存
        if not os.path.exists(output_wav_path):
            print(f"Error: WAV file {output_wav_path} not saved properly.")
            return
    else:
        print(f"Error: API returned status code {response.status_code}")
        print(f"Response text: {response.text}")

if __name__ == '__main__':
    print(f"Using ffmpeg at: {ffmpeg_path}")
    print("Current working directory:", os.getcwd())
    print("Testing /voice_chat endpoint with audio input...")
    test_voice_input()
