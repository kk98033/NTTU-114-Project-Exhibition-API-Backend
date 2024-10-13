import requests
import json

# 設定 API 伺服器的 URL
BASE_URL = 'http://localhost:6969'

def test_chat():
    url = f'{BASE_URL}/chat'
    payload = {
        'message': 'Hello, chatbot!'
    }
    headers = {
        'Content-Type': 'application/json'
    }

    # 使用 stream=True 來處理 streaming 回應
    response = requests.post(url, data=json.dumps(payload), headers=headers, stream=True)

    if response.status_code == 200:
        print("Chat Response (Streaming):")
        try:
            # 逐行讀取 streaming 回應
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    print(line)
        except Exception as e:
            print(f"Error processing stream: {e}")
    else:
        print(f"Error {response.status_code}: {response.text}")

def test_normal_chat():
    url = f'{BASE_URL}/normal_chat'
    payload = {
        'message': 'Tell me a joke'
    }
    headers = {
        'Content-Type': 'application/json'
    }

    response = requests.post(url, data=json.dumps(payload), headers=headers)

    if response.status_code == 200:
        print("Normal Chat Response:", response.json())
    else:
        print(f"Error {response.status_code}: {response.text}")

if __name__ == '__main__':
    print("Testing /chat endpoint:")
    test_chat()
    
    print("\nTesting /normal_chat endpoint:")
    test_normal_chat()
