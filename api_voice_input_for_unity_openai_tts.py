from core.chatbot_core import ChatBot
from utils.WhisperTranscriber import WhisperTranscriber
from utils.Denoiser import Denoiser

from flask import Flask, request, jsonify, send_file, make_response
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
import uuid

import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

# 用於保存共享狀態
class ChatAgentManager:
    def __init__(self):
        self.chat_agent = ChatBot()
        self.query_count = 0
        self.lock = threading.Lock()
        self.is_resetting = False  # 新增狀態變數

    def get_agent(self):
        with self.lock:
            self.query_count += 1
            if self.query_count > 2 and not self.is_resetting:  # 問答2句後觸發重置，但避免重複觸發
                self.query_count = 0  # 重置計數器
                threading.Thread(target=self.reset_agent).start()  # 非同步重置
            return self.chat_agent

    def reset_agent(self):
        with self.lock:
            if self.is_resetting:  # 檢查是否已在重置
                return
            self.is_resetting = True
        try:
            app.logger.info("\033[93m[提醒] Chat agent 重置開始...\033[0m")  # 黃色提醒
            time.sleep(1)  # 模擬重置的耗時操作
            new_agent = ChatBot()  # 初始化新的 ChatBot
            with self.lock:
                self.chat_agent = new_agent  # 替換舊的 ChatBot
            app.logger.info("\033[92m[成功] Chat agent 重置完成！\033[0m")  # 綠色成功消息
        except Exception as e:
            app.logger.error(f"\033[91m[錯誤] Chat agent 重置失敗: {e}\033[0m")  # 紅色錯誤消息
        finally:
            with self.lock:
                self.is_resetting = False  # 重置完成

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

@app.before_request
def before_request_hooks():
    # 設置請求唯一 ID
    request.id = str(uuid.uuid4())
    app.logger.info(f"\033[94m[Request ID: {request.id}] Incoming request: {request.url}\033[0m")

    # 確保請求數據是 UTF-8 解碼
    try:
        if request.data:
            request.data = request.data.decode('utf-8')
    except UnicodeDecodeError as e:
        app.logger.error(f"Unicode decode error: {e}")
        return jsonify({"error": "Invalid UTF-8 encoding"}), 400


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
            output_audio = os.path.join(app.config['OUTPUT_FOLDER'], 'output.wav')
            file.save(input_path)

            app.logger.info(f"Saved uploaded file to: {input_path}")

            # 檢查檔案是否存在
            if not os.path.exists(input_path):
                app.logger.error(f"Uploaded file does not exist at: {input_path}")
                return jsonify({"error": "File save failed"}), 500

            # Initialize Denoiser and process the file
            denoiser = Denoiser()
            app.logger.info(f"Processing file with Denoiser: {input_path}")
            denoiser.process(input_path, denoised_wav)

            # Initialize WhisperTranscriber and transcribe the denoised file
            transcriber = WhisperTranscriber()
            app.logger.info(f"Transcribing file with WhisperTranscriber: {denoised_wav}")
            transcription = transcriber.transcribe(denoised_wav)
            app.logger.info(f"\033[94m [Whisper transcription] {transcription}\033[0m")

            chat_agent = chat_agent_manager.get_agent()
            response = chat_agent.normal_chat(transcription)
            
            response_text = response.response
            
            app.logger.info(f'\033[94m [Bot response] {response_text}')

            parsed_response = parse_custom_tag(response_text)
            action = parsed_response.get('action')
            app.logger.info(f'Parsed action: {action}')

            call_tts_and_save(response_text, output_audio)

            # 檢查文件是否成功保存
            if not os.path.exists(output_audio):
                app.logger.error(f"Error: Output audio file {output_audio} not found.")
                return jsonify({"error": "Audio file not found"}), 500

            # 構建多部分表單數據響應
            with open(output_audio, 'rb') as audio_file:
                audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

                encoder = MultipartEncoder(
                    fields={
                        'json': ('json', jsonify({
                            'action': action,
                            'response': response_text
                        }).get_data(as_text=True), 'application/json'),
                        'file': ('output.wav', audio_base64, 'audio/wav')
                    }
                )
                response = make_response(encoder.to_string())
                response.headers['Content-Type'] = encoder.content_type
                return response
        
        except Exception as e:
            app.logger.error(f"Error processing file: {e}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
        finally:
            if os.path.exists(input_path):
                os.remove(input_path)
                app.logger.info(f"Removed input file: {input_path}")
            if os.path.exists(denoised_wav):
                os.remove(denoised_wav)
                app.logger.info(f"Removed denoised file: {denoised_wav}")
            # if os.path.exists(output_audio):
            #     os.remove(output_audio)
            #     app.logger.info(f"Removed output audio file: {output_audio}")
    else:
        app.logger.warning(f"File type not allowed: {file.filename}")
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/text_chat_unity', methods=['POST'])
def text_chat_unity():
    try:
        # 確認請求中是否有 JSON 並包含 'text' 參數
        if not request.json or 'text' not in request.json:
            app.logger.warning("No 'text' parameter in the request")
            return jsonify({"error": "No 'text' parameter in the request"}), 400

        text_input = request.json['text']
        if not text_input.strip():
            app.logger.warning("Empty 'text' parameter in the request")
            return jsonify({"error": "Empty 'text' parameter"}), 400

        app.logger.info(f"Received text input: {text_input}")

        # 獲取 ChatBot 實例並處理文字輸入
        chat_agent = chat_agent_manager.get_agent()
        response = chat_agent.normal_chat(text_input)
        response_text = response.response

        app.logger.info(f"\033[94m[Bot response] {response_text}\033[0m")

        # 解析回應中的自定義標籤
        parsed_response = parse_custom_tag(response_text)
        action = parsed_response.get('action')
        app.logger.info(f'Parsed action: {action}')

        # 生成音訊檔案
        output_audio = os.path.join(app.config['OUTPUT_FOLDER'], 'output.wav')
        call_tts_and_save(response_text, output_audio)

        # 檢查音訊檔案是否成功生成
        if not os.path.exists(output_audio):
            app.logger.error(f"Error: Output audio file {output_audio} not found.")
            return jsonify({"error": "Audio file not found"}), 500

        # 構建多部分表單數據響應
        with open(output_audio, 'rb') as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

            encoder = MultipartEncoder(
                fields={
                    'json': ('json', jsonify({
                        'action': action,
                        'response': response_text
                    }).get_data(as_text=True), 'application/json'),
                    'file': ('output.wav', audio_base64, 'audio/wav')
                }
            )
            response = make_response(encoder.to_string())
            response.headers['Content-Type'] = encoder.content_type
            return response

    except Exception as e:
        app.logger.error(f"Error in text_chat_unity: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/text_chat', methods=['POST'])
def text_chat():
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

@app.route('/test_api', methods=['GET'])
def test_api():
    try:
        # 獲取請求中的文字輸入
        text_prompt = request.args.get('prompt')
        if not text_prompt:
            app.logger.warning("No 'prompt' parameter in the request")
            return jsonify({"error": "Missing 'prompt' parameter"}), 400

        app.logger.info(f"Received text prompt: {text_prompt}")

        # 傳遞文字到 LLM 處理
        chat_agent = chat_agent_manager.get_agent()
        response = chat_agent.normal_chat(text_prompt)
        response_text = response.response

        app.logger.info(f"[Bot response] {response_text}")

        # 生成音訊檔案
        output_audio = os.path.join(app.config['OUTPUT_FOLDER'], 'test_output.wav')
        call_tts_and_save(response_text, output_audio)

        # 檢查音訊檔案是否成功生成
        if not os.path.exists(output_audio):
            app.logger.error(f"Error: Output audio file {output_audio} not found.")
            return jsonify({"error": "Audio file not found"}), 500

        # 傳回音訊檔案，讓瀏覽器直接播放
        return send_file(output_audio, mimetype='audio/wav', as_attachment=False)

    except Exception as e:
        app.logger.error(f"Error in test_api: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


def call_tts_and_save(text, save_path):
    try:
        # 呼叫 OpenAI 的 TTS API
        response = openai.audio.speech.create(
            model="tts-1",  # 可以使用 tts-1-hd 來獲得更高品質的音頻
            voice="nova",   # 指定所需的聲音
            input=text      # 輸入文字
        )
        
        # 暫時將 TTS 生成的音頻保存為中間檔案
        temp_output = save_path.replace(".wav", "_temp.wav")
        with open(temp_output, "wb") as f:
            f.write(response.read())
        print(f"暫存音頻已保存到 {temp_output}")
        
        # 使用 ffmpeg 將暫存音頻轉換為 PCM 格式的 .wav 檔案
        ffmpeg_command = [
            'ffmpeg',
            '-y',                   # 加入 -y 強制覆蓋已存在的檔案
            '-i', temp_output,       # 輸入文件
            '-acodec', 'pcm_s16le',  # 使用 PCM 格式
            '-ar', '44100',          # 設置採樣率
            save_path                # 輸出文件
        ]
        subprocess.run(ffmpeg_command, check=True)
        print(f"已轉換音頻並保存到 {save_path}")
        
        # 刪除暫存文件
        if os.path.exists(temp_output):
            os.remove(temp_output)
            print(f"刪除了暫存音頻文件: {temp_output}")
    
    except Exception as e:
        print(f"調用 TTS API 時發生錯誤: {e}")

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

    app.logger.info("Loading chat bot...")
    chat_agent = ChatBot()
    app.logger.info("Chat bot loaded!")

    app.logger.info("Loading Whisper model...")
    transcriber = WhisperTranscriber('medium')
    app.logger.info('Model loaded!')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DENOSIED_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=443, debug=True, use_reloader=False)
