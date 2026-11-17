import librosa as lr
import numpy as np
import torch
from transformers import AutoProcessor, ClapModel

MODEL_NAME = "./clap-ai"
processor = AutoProcessor.from_pretrained(MODEL_NAME)
model = ClapModel.from_pretrained(MODEL_NAME)
model.eval()


def get_audio_embedding(file_path):
    try:
        duration = lr.get_duration(path=file_path)
        embeddings = []
        for ratio in (0.1, 0.5, 0.8):
            y, sr = lr.load(file_path, sr=48000, offset=duration * ratio, duration=10.0)
            inputs = processor(audio=y, return_tensors="pt", sampling_rate=sr)
            with torch.no_grad():
                features = model.get_audio_features(**inputs).pooler_output
                features = features / features.norm(dim=-1, keepdim=True)
                embeddings.append(features.numpy()[0])

        mean_emb = np.mean(embeddings, axis=0)
        return mean_emb / np.linalg.norm(mean_emb)
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")
        return None


def analyze_playlist(file_path):
    return 0
