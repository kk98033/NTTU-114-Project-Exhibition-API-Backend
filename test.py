import torch

def test_cuda():
    print("是否支援 CUDA：", torch.cuda.is_available())

    if torch.cuda.is_available():
        print("可用 GPU 數量：", torch.cuda.device_count())
        for i in range(torch.cuda.device_count()):
            print(f"GPU {i} 名稱：", torch.cuda.get_device_name(i))
            print(f"GPU {i} 記憶體使用狀況：{torch.cuda.memory_allocated(i) / 1024 ** 2:.2f} MB")
    else:
        print("⚠️ 找不到 CUDA 裝置，請確認已安裝正確的 NVIDIA 驅動和 CUDA Toolkit")

if __name__ == "__main__":
    test_cuda()
