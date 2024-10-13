# tests/test_torchaudio.py
import torchaudio
import logging

def test_torchaudio_load_save(file_path, save_path):
    logger = logging.getLogger('TestTorchaudio')
    logging.basicConfig(level=logging.INFO)
    try:
        waveform, sample_rate = torchaudio.load(file_path)
        logger.info(f"Loaded waveform with shape: {waveform.shape}, sample rate: {sample_rate}")
        torchaudio.save(save_path, waveform, sample_rate)
        logger.info(f"Saved waveform to: {save_path}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == '__main__':
    test_file = 'uploads/tests_test.wav'
    output_file = 'uploads/output_test.wav'
    test_torchaudio_load_save(test_file, output_file)
