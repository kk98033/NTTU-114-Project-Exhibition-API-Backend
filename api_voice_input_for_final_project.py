from core.chatbot_core import ChatBot
from utils.WhisperTranscriber import WhisperTranscriber
from utils.Denoiser import Denoiser

from flask import Flask, request, jsonify, send_file, make_response, Response
from requests_toolbelt.multipart.encoder import MultipartEncoder
from werkzeug.utils import secure_filename
import requests
import logging
import base64
import os
import re
import subprocess
import threading
import time

import os

ffmpeg_path = r"D:\0520申請入學\2025March專題\ffmpeg\bin"
os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]

# 用於保存共享狀態
class ChatAgentManager:
    def __init__(self):
        self.chat_agent = ChatBot()
        self.query_count = 0
        self.lock = threading.Lock()

    def get_agent(self):
        with self.lock:
            self.query_count += 1
            if self.query_count > 2:  # 問答2句後觸發重置
                self.query_count = 0  # 重置計數器
                threading.Thread(target=self.reset_agent).start()  # 非同步重置
            return self.chat_agent

    def reset_agent(self):
        with self.lock:
            try:
                app.logger.info("\033[93m[提醒] Chat agent 重置開始...\033[0m")  # 黃色提醒
                time.sleep(1)  # 模擬重置的耗時操作
                new_agent = ChatBot()  # 初始化新的 ChatBot
                self.chat_agent = new_agent  # 替換舊的 ChatBot
                app.logger.info("\033[92m[成功] Chat agent 重置完成！\033[0m")  # 綠色成功消息
            except Exception as e:
                app.logger.error(f"\033[91m[錯誤] Chat agent 重置失敗: {e}\033[0m")  # 紅色錯誤消息

chat_agent_manager = ChatAgentManager()

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',  # 藍色
        'INFO': '\033[92m',   # 綠色
        'WARNING': '\033[93m', # 黃色
        'ERROR': '\033[91m',  # 紅色
        'CRITICAL': '\033[1;91m', # 粗體紅色
        'PURPLE': '\033[95m'  # 紫色
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, '\033[0m')
        reset_color = '\033[0m'
        message = super().format(record)
        return f"{log_color}{message}{reset_color}"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['DENOSIED_FOLDER'] = os.path.join(os.getcwd(), 'denoised')
app.config['OUTPUT_FOLDER'] = os.path.join(os.getcwd(), 'output')
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg'}

print("Current working directory:", os.getcwd())

# 設置日誌記錄器
handler = logging.StreamHandler()
formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 清除現有的所有處理器
if app.logger.hasHandlers():
    app.logger.handlers.clear()

app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# 新增 FileHandler 將 log 寫入檔案（以附加模式）
file_handler = logging.FileHandler('server_log.txt', mode='a', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
app.logger.addHandler(file_handler)

# 設置日誌記錄器
handler = logging.StreamHandler()
formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 清除現有的所有處理器
if app.logger.hasHandlers():
    app.logger.handlers.clear()

app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# 新增 FileHandler 寫入本地 txt 檔
file_handler = logging.FileHandler('server_log.txt', mode='a', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
app.logger.addHandler(file_handler)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def parse_custom_tag(response):
    pattern = r'<action>(\d+)</action>'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        action_value = match.group(1)
        return {"action": int(action_value)}
    else:
        return {"action": -1}

@app.route('/voice_chat', methods=['POST'])
def normal_chat():
    if 'file' not in request.files:
        app.logger.warning("No file part in the request")
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        app.logger.warning("No selected file in the request")
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            denoised_wav = os.path.join(app.config['DENOSIED_FOLDER'], 'denoised.wav')
            output_audio = os.path.join(app.config['OUTPUT_FOLDER'], 'output.ogg')
            file.save(input_path)

            app.logger.info(f"Saved uploaded file to: {input_path}")

            denoiser.process(input_path, denoised_wav)
            transcription = transcriber.transcribe(denoised_wav)
            app.logger.info(f"Transcription: {transcription}")

            chat_agent = chat_agent_manager.get_agent()
            response = chat_agent.normal_chat(transcription)
            response_text = response.response
            app.logger.info(f"Bot response: {response_text}")

            parsed_response = parse_custom_tag(response_text)
            app.logger.info(f"Parsed response: {parsed_response}")

            call_tts_and_save(response_text, output_audio)

            if not os.path.exists(output_audio):
                app.logger.error(f"Error: Output audio file {output_audio} not found.")
                return jsonify({"error": "Audio file not found"}), 500

            # 將音訊檔案編碼為 Base64
            with open(output_audio, 'rb') as f:
                audio_base64 = base64.b64encode(f.read()).decode('utf-8')

            with open("debug_output.ogg", "wb") as debug_file:
                debug_file.write(base64.b64decode(audio_base64))

            # 返回 JSON 回應，增加 transcription
            return jsonify({
                "response_text": response_text,
                "parsed_response": parsed_response,
                "transcription": transcription,
                "audio": audio_base64
            }), 200

        except Exception as e:
            app.logger.error(f"Error processing file: {e}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
        finally:
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(denoised_wav):
                os.remove(denoised_wav)
    else:
        app.logger.warning(f"File type not allowed: {file.filename}")
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/text_chat', methods=['POST'])
def text_chat():
    """
    通用純文字聊天 API，可選擇是否產生語音

    請求類型：application/json
        {
            "text": "你想問的內容",
            "generate_audio": true 或 false（可選，預設為 true），
            "tts_service": "local" 或 "openai"（可選，預設為 local）
        }

    回傳：
        若 generate_audio 為 false：
            - JSON: {"response": 回應文字}
        若 generate_audio 為 true：
            - multipart/form-data:
                - json: {"response": 回應文字}
                - file: base64 編碼的 output.wav

    用途：前端通用文字輸入，支援語音輸出功能
    """
    try:
        # 獲取請求中的文字輸入
        if not request.json or 'text' not in request.json:
            app.logger.warning("No 'text' parameter in the request")
            return jsonify({"error": "No 'text' parameter in the request"}), 400

        text_input = request.json['text']
        if not text_input.strip():
            app.logger.warning("Empty 'text' parameter in the request")
            return jsonify({"error": "Empty 'text' parameter"}), 400

        # 獲取可選參數 generate_audio（預設為 True）
        generate_audio = request.json.get('generate_audio', True)
        if isinstance(generate_audio, str):
            generate_audio = generate_audio.lower() == 'true'

        app.logger.info(f"Received text input: {text_input}, Generate Audio: {generate_audio}")

        # 使用 ChatBot 處理文字輸入
        chat_agent = chat_agent_manager.get_agent()
        response = chat_agent.normal_chat(text_input)
        response_text = response.response

        app.logger.info(f"\033[94m[Bot response] {response_text}\033[0m")

        if not generate_audio:
            # 如果不需要生成音訊，直接返回文字回應
            return jsonify({
                "response": response_text
            }), 200

        # 生成音訊檔案
        output_audio = os.path.join(app.config['OUTPUT_FOLDER'], 'output.wav')
        call_tts_and_save(response_text, output_audio)

        # 檢查文件是否成功保存
        if not os.path.exists(output_audio):
            app.logger.error(f"Error: Output audio file {output_audio} not found.")
            return jsonify({"error": "Audio file not found"}), 500

        # 構建多部分表單數據響應
        with open(output_audio, 'rb') as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

            return jsonify({
                "response": response_text,
                "audio": audio_base64
            })

            encoder = MultipartEncoder(
                fields={
                    'json': ('json', jsonify({
                        'response': response_text
                    }).get_data(as_text=True), 'application/json'),
                    'file': ('output.wav', audio_base64, 'audio/wav')
                }
            )
            response = make_response(encoder.to_string())
            response.headers['Content-Type'] = encoder.content_type
            return response

    except Exception as e:
        app.logger.error(f"Error processing text input: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
    
def call_tts_and_save(text, save_path):
    uri = f"http://127.0.0.1:9880/?text={text}&text_language=zh"
    stream_audio_from_api(uri, save_path)

def stream_audio_from_api(uri, save_path):
    try:
        response = requests.get(uri, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as audio_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # 檢查 chunk 是否有數據
                    audio_file.write(chunk)
        
        print(f"Audio saved to {save_path}")
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    project_root = os.path.abspath(os.path.dirname(__file__))
    ffmpeg_path = os.path.join(project_root, 'ffmpeg', 'bin')
    os.environ['PATH'] += os.pathsep + ffmpeg_path

    # 確認 ffmpeg 是否可用
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, check=True)
        app.logger.info(f"ffmpeg is accessible:\n{result.stdout}")
    except Exception as e:
        app.logger.error(f"ffmpeg is not accessible: {e}")

    current_working_directory = os.getcwd()
    app.logger.info(f"Current working directory: {current_working_directory}")

    app.logger.info("Loading Denoiser...")
    denoiser = Denoiser()
    app.logger.info("Denoiser initialized!")

    app.logger.info("Loading chat bot...")
    chat_agent = ChatBot()
    app.logger.info("Chat bot loaded!")

    app.logger.info("Loading Whisper model...")
    transcriber = WhisperTranscriber('medium')
    app.logger.info('Model loaded!')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DENOSIED_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=6969, debug=True, use_reloader=False)
