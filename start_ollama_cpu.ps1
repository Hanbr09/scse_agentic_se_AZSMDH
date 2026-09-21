$ErrorActionPreference = 'Stop'
$command = Get-Command ollama -ErrorAction SilentlyContinue
if ($command) {
    $ollamaPath = $command.Source
} else {
    $ollamaPath = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
}
if (-not (Test-Path -LiteralPath $ollamaPath)) {
    throw 'Ollama is not installed. No model or software has been downloaded.'
}

# These settings affect this terminal and its child server only.
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:GGML_VK_VISIBLE_DEVICES = '-1'
$env:OLLAMA_VULKAN = '0'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_CONTEXT_LENGTH = '2048'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_KEEP_ALIVE = '0'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NOPRUNE = '1'
$env:NO_PROXY = 'localhost,127.0.0.1'

Write-Output 'Starting CPU-only Ollama in this terminal. Press Ctrl+C when finished.'
Write-Output 'If port 11434 is occupied, stop the other Ollama server before continuing.'
& $ollamaPath serve
exit $LASTEXITCODE
