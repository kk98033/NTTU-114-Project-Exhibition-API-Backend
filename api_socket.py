from flask import Flask, request
from flask_socketio import SocketIO, emit
import eventlet
import logging
import os
import threading
import requests
from core.chatbot_core import ChatBot
from utils.WhisperTranscriber import WhisperTranscriber
from utils.Denoiser import Denoiser

# 套用 eventlet monkey patch
eventlet.monkey_patch()

# 加入 ffmpeg 路徑
os.environ["PATH"] = r"D:\0520申請入學\2025March專題\ffmpeg\bin" + os.pathsep + os.environ["PATH"]

# Flask 與 SocketIO 初始化
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 設定 log 輸出與檔案記錄
file_handler = logging.FileHandler('server_log.txt', mode='a', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

if app.logger.hasHandlers():
    app.logger.handlers.clear()
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# 模型初始化
denoiser = Denoiser()
transcriber = WhisperTranscriber('medium')

class ChatAgentManager:
    def __init__(self):
        self.chat_agent = ChatBot()
        self.query_count = 0
        self.lock = threading.Lock()

    def get_agent(self):
        with self.lock:
            self.query_count += 1
            if self.query_count > 2:
                self.query_count = 0
                threading.Thread(target=self.reset_agent).start()
            return self.chat_agent

    def reset_agent(self):
        with self.lock:
            try:
                app.logger.info("[重置] Chat agent 開始重置")
                self.chat_agent = ChatBot()
                app.logger.info("[重置] Chat agent 已重置")
            except Exception as e:
                app.logger.error(f"[錯誤] Chat agent 重置失敗: {e}")

chat_agent_manager = ChatAgentManager()

@socketio.on('voice_chat')
def handle_voice_chat(data):
    try:
        print("[音訊接收] bytes 數量:", len(data.get('audio', b'')))

        audio_bytes = data.get('audio')
        if not audio_bytes:
            emit('error', {'message': '未收到音訊'}, to=request.sid)
            return

        upload_path = os.path.join("uploads", 'input.wav')
        denoised_path = os.path.join("denoised", 'denoised.wav')

        with open(upload_path, 'wb') as f:
            f.write(audio_bytes)

        print("[處理] 開始音訊降噪")
        denoiser.process(upload_path, denoised_path)

        print("[處理] 語音轉文字中")
        transcription = transcriber.transcribe(denoised_path)
        print("[結果] 轉錄完成:", transcription)
        emit('transcription', {'text': transcription}, to=request.sid)

        emit('thinking_status', '思考中...', to=request.sid)

        chat_agent = chat_agent_manager.get_agent()
        response = chat_agent.normal_chat(transcription)
        response_text = response.response
        print("[處理] LLM 回應完成")

        tool_usage = chat_agent.get_last_tool_usage_raw()

        emit('bot_response', {
            'text': response_text,
            'tools_used': tool_usage
        }, to=request.sid)

        emit('thinking_status', '生成語音中...', to=request.sid)

        print("[請求] 呼叫 TTS API")
        uri = f"http://127.0.0.1:9880/?text={response_text}&text_language=zh"
        r = requests.get(uri, stream=True)

        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                emit('audio_stream', chunk, binary=True, to=request.sid)
        print("[完成] 音訊串流完畢")
        emit('audio_done', to=request.sid)

    except Exception as e:
        print("[錯誤]", e)
        app.logger.error(f"處理錯誤: {e}")
        emit('error', {'message': '伺服器錯誤'}, to=request.sid)


@socketio.on('text_chat')
def handle_text_chat(data):
    try:
        text = data.get('text', '').strip()
        if not text:
            emit('error', {'message': '未提供文字'}, to=request.sid)
            return

        emit('thinking_status', '思考中...', to=request.sid)

        chat_agent = chat_agent_manager.get_agent()
        response = chat_agent.normal_chat(text)
        response_text = response.response

        tool_usage = chat_agent.get_last_tool_usage_raw()
        print('Tool usage: ', tool_usage)
        emit('bot_response', {
            'text': response_text,
            'tools_used': tool_usage
        }, to=request.sid)

        emit('thinking_status', '生成語音中...', to=request.sid)

        uri = f"http://127.0.0.1:9880/?text={response_text}&text_language=zh"
        r = requests.get(uri, stream=True)
        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                emit('audio_stream', chunk, binary=True, to=request.sid)
        emit('audio_done', to=request.sid)
    except Exception as e:
        app.logger.error(f"文字聊天錯誤: {e}")
        emit('error', {'message': '伺服器錯誤'}, to=request.sid)

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('denoised', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    socketio.run(app, host='0.0.0.0', port=6969, debug=True)
