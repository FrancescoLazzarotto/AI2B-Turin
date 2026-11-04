#!/usr/bin/env bash
export HF_HOME="${HF_HOME:-/mnt/storage/flazzarotto/hf-cache-sonde}"
VLLM=/mnt/storage/flazzarotto/venvs/vllm-serve/bin/vllm
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/../logs"
CUDA_VISIBLE_DEVICES=1 setsid nohup "$VLLM" serve RedHatAI/Qwen3.8-27B-INT4 \
  --revision 2fb0debc365fb6c1683d7d3ad7722470919627a8 \
  --served-model-name llm --gpu-memory-utilization 0.80 --max-model-len 16384 \
  --max-num-seqs 8 --limit-mm-per-prompt '{"image":0}' --enable-prefix-caching \
  --chat-template "$DIR/qwen38_nothink.jinja" --host 127.0.0.1 --port 8001 \
  > "$DIR/../logs/llm.log" 2>&1 &
CUDA_VISIBLE_DEVICES=1 setsid nohup "$VLLM" serve intfloat/multilingual-e5-base \
  --served-model-name embed --gpu-memory-utilization 0.08 --host 127.0.0.1 --port 8002 \
  > "$DIR/../logs/embed.log" 2>&1 &
