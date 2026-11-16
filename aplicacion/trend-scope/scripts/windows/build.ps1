Set-Location (Resolve-Path "$PSScriptRoot\..\..")

$PROJECT_NAME = "trend-scope"

if (-not (Test-Path "src-tauri\pyembed\python\python.exe")) {
    throw "Falta el Python embebido. Corré primero scripts\windows\download-py.ps1."
}

$env:PYTAURI_STANDALONE = "1"
$env:PYO3_PYTHON = (Resolve-Path -LiteralPath "src-tauri\pyembed\python\python.exe").Path
# The embedded Python must not see a development virtual environment.
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# Install the app and its dependencies into the embedded Python (uv if available, pip otherwise).
if (Get-Command uv.exe -ErrorAction SilentlyContinue) {
    uv.exe pip install `
        --exact `
        --compile-bytecode `
        --python="$env:PYO3_PYTHON" `
        --reinstall-package="$PROJECT_NAME" `
        .\src-tauri
} else {
    & $env:PYO3_PYTHON -m pip install --compile .\src-tauri
    & $env:PYO3_PYTHON -m pip install --compile --force-reinstall --no-deps .\src-tauri
}
if ($LASTEXITCODE) { throw "No se pudo instalar el paquete en el Python embebido." }

# pnpm if available, the project's own Tauri CLI otherwise.
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    pnpm -- tauri build --config="src-tauri\tauri.bundle.json" -- --profile bundle-release
} else {
    & .\node_modules\.bin\tauri.cmd build --config "src-tauri\tauri.bundle.json" -- --profile bundle-release
}
