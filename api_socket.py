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
import asyncio
from queue import Queue
from llama_index.core.agent.workflow import AgentStream, ToolCallResult

# 套用 eventlet monkey patch
# eventlet.monkey_patch()

# 加入 ffmpeg 路徑
os.environ["PATH"] = r"D:\0520申請入學\2025March專題\ffmpeg\bin" + os.pathsep + os.environ["PATH"]

# Flask 與 SocketIO 初始化
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

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

@socketio.on('text_chat_stream')
def handle_text_chat_stream(data):
    text = data.get('text', '').strip()
    print("[接收] 接收文字:", text)

    if not text:
        emit('error', {'message': '未提供文字'}, to=request.sid)
        return

    emit('thinking_status', '思考中...', to=request.sid)

    chat_agent = chat_agent_manager.get_agent()
    sid = request.sid

    def run_chat():
        async def chat_async():
            ctx = chat_agent.ctx
            handler = chat_agent.agent.run(text, ctx=ctx)

            full_response = ""

            async for ev in handler.stream_events():
                if isinstance(ev, AgentStream):
                    # 即時送出 partial_response
                    delta = ev.delta
                    full_response += delta
                    socketio.emit('partial_response', {'text': delta}, to=sid)

                    # 嘗試 parse Thought / Action
                    if "Thought:" in delta or "Action:" in delta:
                        lines = delta.strip().splitlines()
                        step_data = {}
                        for line in lines:
                            if line.startswith("Thought:"):
                                step_data["thought"] = line[len("Thought:"):].strip()
                            elif line.startswith("Action:"):
                                step_data["action"] = line[len("Action:"):].strip()
                        if step_data:
                            socketio.emit("thought_step", step_data, to=sid)

                elif isinstance(ev, ToolCallResult):
                    socketio.emit('thought_step', {
                        "action": ev.tool_name,
                        "tool_input": ev.tool_kwargs,
                        "observation": str(ev.tool_output)
                    }, to=sid)

                    # socketio.emit('partial_response', {
                    #     'text': f"\n工具回應：{str(ev.tool_output)}"
                    # }, to=sid)

            final_response = await handler
            chat_agent.response = final_response

            print("[完成] 回應：", final_response.response)

            socketio.emit('bot_response', {
                'text': str(final_response.response), 
                'tools_used': chat_agent.get_last_tool_usage_raw()
            }, to=sid)

            socketio.emit('thinking_status', '生成語音中...', to=sid)

            # TTS 播放
            uri = f"http://127.0.0.1:9880/?text={final_response.response}&text_language=zh"
            r = requests.get(uri, stream=True)
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    socketio.emit('audio_stream', chunk, to=sid)
            socketio.emit('audio_done', to=sid)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(chat_async())

    threading.Thread(target=run_chat).start()

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

@socketio.on('voice_chat_stream')
def handle_voice_chat_stream(data):
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
        sid = request.sid

        def run_chat():
            async def chat_async():
                ctx = chat_agent.ctx
                handler = chat_agent.agent.run(transcription, ctx=ctx)

                full_response = ""

                async for ev in handler.stream_events():
                    if isinstance(ev, AgentStream):
                        # 即時送出 partial_response
                        delta = ev.delta
                        full_response += delta
                        socketio.emit('partial_response', {'text': delta}, to=sid)

                        # 嘗試 parse Thought / Action
                        if "Thought:" in delta or "Action:" in delta:
                            lines = delta.strip().splitlines()
                            step_data = {}
                            for line in lines:
                                if line.startswith("Thought:"):
                                    step_data["thought"] = line[len("Thought:"):].strip()
                                elif line.startswith("Action:"):
                                    step_data["action"] = line[len("Action:"):].strip()
                            if step_data:
                                socketio.emit("thought_step", step_data, to=sid)

                    elif isinstance(ev, ToolCallResult):
                        socketio.emit('thought_step', {
                            "action": ev.tool_name,
                            "tool_input": ev.tool_kwargs,
                            "observation": str(ev.tool_output)
                        }, to=sid)

                        # socketio.emit('partial_response', {
                        #     'text': f"\n工具回應：{str(ev.tool_output)}"
                        # }, to=sid)

                final_response = await handler
                chat_agent.response = final_response

                print("[完成] 回應：", final_response.response)

                socketio.emit('bot_response', {
                    'text': str(final_response.response), 
                    'tools_used': chat_agent.get_last_tool_usage_raw()
                }, to=sid)

                socketio.emit('thinking_status', '生成語音中...', to=sid)

                # TTS 播放
                uri = f"http://127.0.0.1:9880/?text={final_response.response}&text_language=zh"
                r = requests.get(uri, stream=True)
                for chunk in r.iter_content(chunk_size=4096):
                    if chunk:
                        socketio.emit('audio_stream', chunk, to=sid)
                socketio.emit('audio_done', to=sid)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(chat_async())

        threading.Thread(target=run_chat).start()

    except Exception as e:
        print("[錯誤]", e)
        app.logger.error(f"語音串流聊天錯誤: {e}")
        emit('error', {'message': '伺服器錯誤'}, to=request.sid)


if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('denoised', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    socketio.run(app, host='0.0.0.0', port=6969, debug=True)
