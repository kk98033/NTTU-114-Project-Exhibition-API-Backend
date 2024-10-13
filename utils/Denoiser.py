# utils/Denoiser.py
import torch
import torchaudio
import subprocess
from denoiser import pretrained
from denoiser.dsp import convert_audio
import logging

class Denoiser:
    def __init__(self, model_path='dns64', device='cuda'):
        # 列出可用的後端並設置一個
        available_backends = torchaudio.list_audio_backends()
        print(f"Available torchaudio backends: {available_backends}")
        if "sox_io" in available_backends:
            torchaudio.set_audio_backend("sox_io")
        elif "soundfile" in available_backends:
            torchaudio.set_audio_backend("soundfile")
        else:
            raise RuntimeError("No suitable torchaudio backend found.")
        
        self.model = pretrained.dns64().to(device)
        self.device = device

    def load_audio(self, file_path):
        try:
            wav, sr = torchaudio.load(file_path)
            return wav.to(self.device), sr
        except Exception as e:
            logging.getLogger('Denoiser').error(f"Failed to load audio file: {e}")
            raise

    def denoise_audio(self, wav, sr):
        wav = convert_audio(wav, sr, self.model.sample_rate, self.model.chin)
        with torch.no_grad():
            denoised = self.model(wav[None])[0]
        return denoised

    def save_audio(self, audio_tensor, file_path, sample_rate):
        try:
            torchaudio.save(file_path, audio_tensor.cpu(), sample_rate)
        except Exception as e:
            logging.getLogger('Denoiser').error(f"Failed to save audio file: {e}")
            raise

    def convert_to_mp3(self, wav_file, mp3_file):
        subprocess.run(['ffmpeg', '-i', wav_file, mp3_file])

    def process(self, input_path, output_wav, output_mp3=None):
        wav, sr = self.load_audio(input_path)
        denoised = self.denoise_audio(wav, sr)
        self.save_audio(denoised, output_wav, self.model.sample_rate)

        if output_mp3:
            self.convert_to_mp3(output_wav, output_mp3)

if __name__ == '__main__':
    denoiser = Denoiser()
    denoiser.process('..\tests\test.wav', 'denoised.wav', 'denoised.mp3')
