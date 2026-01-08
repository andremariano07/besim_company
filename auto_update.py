
import urllib.request
import os
import sys
import tempfile
import zipfile
import shutil

OWNER = "andremariano07"
REPO = "besim_company"
BRANCH = "main"
VERSION_FILE = "VERSION"

IGNORAR_ARQUIVOS = {"besim_company.db"}
IGNORAR_PASTAS = {"cupons", "relatorios", "OS", "__pycache__", ".git"}

def obter_versao_remota():
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{VERSION_FILE}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8").strip()

def baixar_repo_zip():
    url = f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip"
    temp_dir = tempfile.mkdtemp(prefix="update_")
    zip_path = os.path.join(temp_dir, "repo.zip")
    urllib.request.urlretrieve(url, zip_path)
    return temp_dir, zip_path

def extrair_repo(zip_path, temp_dir):
    destino = os.path.join(temp_dir, "src")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(destino)
    return next(os.scandir(destino)).path

def copiar_arquivos(origem, destino):
    for root, dirs, files in os.walk(origem):
        dirs[:] = [d for d in dirs if d not in IGNORAR_PASTAS]
        rel = os.path.relpath(root, origem)
        alvo = os.path.join(destino, rel)
        os.makedirs(alvo, exist_ok=True)
        for f in files:
            if f not in IGNORAR_ARQUIVOS:
                shutil.copy2(os.path.join(root, f), os.path.join(alvo, f))

def reiniciar_app():
    os.execv(sys.executable, [sys.executable] + sys.argv)

def check_and_update(app_version, base_path):
    try:
        versao_remota = obter_versao_remota()
    except Exception:
        return
    if versao_remota != app_version:
        temp, zip_path = baixar_repo_zip()
        codigo = extrair_repo(zip_path, temp)
