
# -*- coding: utf-8 -*-
"""
Sistema Loja - versão unificada com auto-update (após login), splash estilizada e barra de progresso real.
Garantias:
- Roda sem erro
- Atualiza apenas uma vez (sem loop) ✅ (compara remote VERSION com VERSION local)
- Splash bonita com logo (se existir) e SEMPRE em primeiro plano
- Barra de progresso real
- Login abre normalmente
- Banco (besim_company.db) nunca é sobrescrito
- Pronto para virar EXE (PyInstaller)
- Operadores lógicos somente em inglês (or / and / not)
- Um único APP_VERSION e um único __main__
- Melhoria: janela volta para frente após abrir PDF (bring_app_to_front)
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import sqlite3
import datetime
import calendar
import re

# ===================== UTIL: Datas BR flexíveis =====================
# Aceita 'd/m/aaaa' ou 'dd/mm/aaaa' e retorna tupla (d, m, a) como ints.
# Retorna None se não conseguir interpretar.
def _parse_br_date_flex(s: str):
    try:
        s = str(s or '').strip()
        m = re.match(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$', s)
        if not m:
            return None
        d = int(m.group(1)); mo = int(m.group(2)); y = int(m.group(3))
        if d < 1 or d > 31 or mo < 1 or mo > 12:
            return None
        return d, mo, y
    except Exception:
        return None

import os
import sys
import hashlib
import platform
import logging
import urllib.request
import tempfile
import zipfile
import shutil
import ssl
import glob
import certifi
from functools import partial
from reportlab.lib.pagesizes import A4
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
import mimetypes
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import subprocess
import hmac
import secrets
import getpass
from io import BytesIO

# ===================== COMMON HELPERS (Refatoração incremental) =====================
# Objetivo: reduzir repetição e deixar o código mais fluido sem quebrar a arquitetura.
# - Paths seguros (script/EXE)
# - Loader genérico de config KEY=VALUE
# - Abrir arquivo no app padrão do SO (PDF)
# - Decorator para callbacks Tkinter com log + mensagem

from pathlib import Path as _Path

def _app_base_dir() -> _Path:
    """Diretório base do app (compatível com PyInstaller)."""
    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return _Path(getattr(sys, '_MEIPASS'))
    except Exception:
        pass
    return _Path(__file__).resolve().parent

BASE_DIR = _app_base_dir()

def P(*parts) -> _Path:
    """Join de caminho relativo ao diretório base do app."""
    return BASE_DIR.joinpath(*parts)


def load_kv_config(path) -> dict:
    """Lê arquivo no formato KEY=VALUE (ignorando vazias e comentários)."""
    cfg = {}
    try:
        pth = str(path)
        if os.path.isfile(pth):
            with open(pth, 'r', encoding='utf-8') as f:
                for line in f:
                    line = (line or '').strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    cfg[k.strip()] = v.strip()
    except Exception as ex:
        logging.error('Falha ao ler config %s: %s', path, ex, exc_info=True)
    return cfg


def open_in_default_app(file_path: str) -> bool:
    """Abre um arquivo no aplicativo padrão do SO (Windows/macOS/Linux)."""
    try:
        fp = str(file_path)
        system = platform.system()
        if system == 'Windows':
            os.startfile(fp)  # noqa
        elif system == 'Darwin':
            subprocess.run(['open', fp], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(['xdg-open', fp], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as ex:
        logging.error('Falha ao abrir arquivo: %s', ex, exc_info=True)
        return False


from functools import wraps as _wraps

def ui_safe(title: str = 'Erro'):
    """Decorator para handlers Tkinter: loga erro e mostra mensagem amigável."""
    def deco(fn):
        @_wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as ex:
                logging.error('Erro em %s: %s', getattr(fn, '__name__', 'callback'), ex, exc_info=True)
                try:
                    messagebox.showerror(title, f'Ocorreu um erro:\n{ex}')
                except Exception:
                    pass
                return None
        return wrapper
    return deco

# Controle: manter o comportamento de toast para showinfo (se quiser)
USE_TOAST_FOR_INFO = True

# ===================== FIM COMMON HELPERS =====================


# ---- Gráficos para relatório mensal (matplotlib, modo headless) ----
# O app continua funcionando mesmo sem matplotlib (gera PDF sem gráfico).
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    plt = None
    _HAS_MPL = False



# ===================== VISUAL KIT (Windows 11 dark / light) =====================
# Preferência: Modern Dark (grafite) com destaques azul/verde + toasts empilhados
try:
    import sv_ttk  # pip install sv-ttk
    _HAS_SV_TTK = True
except Exception:
    sv_ttk = None
    _HAS_SV_TTK = False

THEME_DARK = {
    "bg": "#1f1f1f",
    "panel": "#252526",
    "panel2": "#2b2b2b",
    "text": "#f2f2f2",
    "muted": "#c7c7c7",
    "border": "#3a3a3a",
    "accent": "#2563eb",   # azul
    "accent2": "#22c55e",  # verde
    "warn": "#f6c453",
    "danger": "#ef4444",
}

THEME_LIGHT = {
    "bg": "#f5f6f7",
    "panel": "#ffffff",
    "panel2": "#f3f4f6",
    "text": "#111827",
    "muted": "#4b5563",
    "border": "#e5e7eb",
    "accent": "#2563eb",
    "accent2": "#16a34a",
    "warn": "#d97706",
    "danger": "#dc2626",
}


# ===================== SOM AGRADÁVEL (boas-vindas pós-login) =====================
def tocar_som_agradavel(path_wav: str = None):
    """
    Toca um som agradável de boas-vindas.
    - Se 'path_wav' existir, toca o WAV.
    - Se não existir ou falhar, usa um beep suave como fallback.
    Suporta Windows (winsound), macOS (afplay) e Linux (paplay/aplay).
    """
    try:
        if not path_wav:
            path_wav = os.path.join(os.getcwd(), "media", "welcome.wav")
        if os.path.isfile(path_wav):
            sistema = platform.system()
            if sistema == "Windows":
                try:
                    import winsound
                    winsound.PlaySound(path_wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                except Exception:
                    pass
            elif sistema == "Darwin":
                try:
                    subprocess.Popen(["afplay", path_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    pass
            else:
                for player in (["paplay", path_wav], ["aplay", path_wav]):
                    try:
                        subprocess.Popen(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    except Exception:
                        continue
        try:
            root_tmp = tk._default_root
            if root_tmp and root_tmp.winfo_exists():
                root_tmp.bell()
                return
        except Exception:
            pass
        try:
            if platform.system() == "Windows":
                import winsound
                winsound.Beep(880, 120)
        except Exception:
            pass
    except Exception:
        pass


BASE_FONT = ("Segoe UI", 10)
HEADING_FONT = ("Segoe UI", 11, "bold")
BUTTON_FONT = ("Segoe UI", 10, "bold")
PADX = 10
PADY = 8

# ================= ENVIO DE CUPOM POR E-MAIL (movido para topo) =================

def _load_email_config():
    """Lê email_config.txt (chaves: EMAIL_GMAIL, EMAIL_GMAIL_APP)."""
    return load_kv_config(P('email_config.txt'))





def enviar_cupom_email(destinatario_email, caminho_pdf):
    """Envia o cupom por e-mail usando Gmail.
    Retorna (True, "OK") em caso de sucesso; em falha retorna (False, mensagem_detalhada)."""
    try:
        if not destinatario_email or "@" not in destinatario_email:
            msg = "E-mail do destinatário vazio ou inválido."
            logging.error(msg)
            return False, msg
        if not os.path.isfile(caminho_pdf):
            msg = f"Arquivo PDF não encontrado: {caminho_pdf}"
            logging.error(msg)
            return False, msg
        cfg = _load_email_config()
        EMAIL_REMETENTE = cfg.get("EMAIL_GMAIL") or os.getenv("EMAIL_GMAIL")
        SENHA_APP = cfg.get("EMAIL_GMAIL_APP") or os.getenv("EMAIL_GMAIL_APP")
        if not EMAIL_REMETENTE or not SENHA_APP:
            msg = ("Credenciais não configuradas. Configure EMAIL_GMAIL e EMAIL_GMAIL_APP em "
                   "email_config.txt ou variáveis de ambiente.")
            logging.error(msg)
            return False, msg
        msg_obj = EmailMessage()
        msg_obj["Subject"] = "Seu cupom de compra - BESIM COMPANY"
        msg_obj["From"] = EMAIL_REMETENTE
        msg_obj["To"] = destinatario_email
        msg_obj["Date"] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S')
        msg_obj.set_content("""Olá!
Segue em anexo o cupom da sua compra.
Obrigado pela preferência!""")
        with open(caminho_pdf, "rb") as fpdf:
            msg_obj.add_attachment(
                fpdf.read(), maintype="application", subtype="pdf",
                filename=os.path.basename(caminho_pdf)
            )
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                smtp.login(EMAIL_REMETENTE, SENHA_APP)
                smtp.send_message(msg_obj)
                return True, "OK"
        except smtplib.SMTPAuthenticationError as e:
            logging.error("Falha de autenticação SMTP: %s", str(e))
            return False, f"Autenticação SMTP falhou: {e}"
        except Exception as e_ssl:
            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(EMAIL_REMETENTE, SENHA_APP)
                    smtp.send_message(msg_obj)
                    return True, "OK"
            except Exception as e_tls:
                logging.error("Erro ao enviar e-mail (SSL e TLS falharam): %s | %s", str(e_ssl), str(e_tls))
                return False, f"Falha SSL/TLS: {e_ssl} | {e_tls}"
    except Exception as e:
        logging.error("Erro inesperado ao enviar e-mail: %s", str(e), exc_info=True)
        return False, f"Erro inesperado: {e}"

def garantir_pastas_backup():
    try:
        for pasta in ("banco", "cupons", "OS", "relatorios"):
            os.makedirs(os.path.join(GOOGLE_DRIVE_BACKUP, pasta), exist_ok=True)
    except Exception as ex:
        logging.error(f"Falha ao criar pastas de backup: {ex}", exc_info=True)
def backup_banco():
    try:
        garantir_pastas_backup()
        if os.path.exists(DB_PATH):
            agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            destino = os.path.join(
                GOOGLE_DRIVE_BACKUP, "banco", f"besim_company_{agora}.db"
            )
            shutil.copy2(DB_PATH, destino)
            logging.info(f"Backup do banco -> {destino}")
    except Exception as ex:
        logging.error(f"Falha no backup do DB: {ex}", exc_info=True)
def backup_pdf(caminho_pdf: str, tipo: str):
    try:
        garantir_pastas_backup()
        destino_dir = os.path.join(GOOGLE_DRIVE_BACKUP, tipo)
        os.makedirs(destino_dir, exist_ok=True)
        if os.path.exists(caminho_pdf):
            shutil.copy2(caminho_pdf, destino_dir)
            logging.info(
                f"Backup PDF ({tipo}) -> {os.path.join(destino_dir, os.path.basename(caminho_pdf))}"
            )
    except Exception as ex:
        logging.error(f"Falha no backup PDF: {ex}", exc_info=True)
def backup_bulk_dir(local_dir: str, tipo: str):
    try:
        garantir_pastas_backup()
        destino_dir = os.path.join(GOOGLE_DRIVE_BACKUP, tipo)
        os.makedirs(destino_dir, exist_ok=True)
        if os.path.exists(local_dir):
            for pdf in glob.glob(os.path.join(local_dir, "*.pdf")):
                shutil.copy2(pdf, destino_dir)
            logging.info(f"Backup em lote de {local_dir} -> {destino_dir}")
    except Exception as ex:
        logging.error(f"Falha no backup em lote: {ex}", exc_info=True)


# ===================== STATUSBAR GLOBAL (VERSÃO + LICENÇA) =====================
# Objetivo: exibir em TODAS as janelas (Tk e Toplevel) um rodapé com:
# - Versão local (arquivo VERSION; fallback APP_VERSION)
# - Dias restantes da licença (get_tempo_restante_licenca_str)
# - Relógio (HH:MM:SS)
# Implementação: hook seguro no __init__ de tk.Tk e tk.Toplevel.

_STATUSBAR_HOOK_INSTALLED = False

def _statusbar_text_version_and_license():
    try:
        ver = get_local_version()
    except Exception:
        ver = APP_VERSION
    try:
        lic = get_tempo_restante_licenca_str()
    except Exception:
        lic = 'Licença: indisponível'
    return f"v{ver} • {lic}"

def _install_global_statusbar_hook():
    global _STATUSBAR_HOOK_INSTALLED
    if _STATUSBAR_HOOK_INSTALLED:
        return
    _STATUSBAR_HOOK_INSTALLED = True

    # Guarda init originais
    _orig_tk_init = tk.Tk.__init__
    _orig_top_init = tk.Toplevel.__init__

    def _attach_statusbar_later(win):
        """Anexa rodapé se janela for 'normal' (não overrideredirect) e ainda não tiver rodapé."""
        try:
            if getattr(win, '_no_statusbar', False):
                return
            if getattr(win, '_statusbar_attached', False):
                return
            # se for splash/overlay, costuma ser overrideredirect=True
            try:
                if bool(win.overrideredirect()):
                    return
            except Exception:
                pass

            # Cria container
            bar = tk.Frame(win, bd=1, relief='flat')
            bar.pack(side='bottom', fill='x', pady=(0, 4))

            # Esquerda: versão + licença
            lbl_left = tk.Label(bar, text=_statusbar_text_version_and_license(), anchor='w', padx=10)
            lbl_left.pack(side='left')

            # Direita: relógio
            lbl_clock = tk.Label(bar, text='', anchor='e', padx=10)
            lbl_clock.pack(side='right')

            # Atualiza licença periodicamente (1 min)
            def _tick_license():
                try:
                    lbl_left.config(text=_statusbar_text_version_and_license())
                except Exception:
                    return
                try:
                    win.after(60000, _tick_license)
                except Exception:
                    pass
            _tick_license()

            # Relógio (1s)
            import datetime as _dt
            def _tick_clock():
                try:
                    lbl_clock.config(text=_dt.datetime.now().strftime('%H:%M:%S'))
                except Exception:
                    return
                try:
                    win.after(1000, _tick_clock)
                except Exception:
                    pass
            _tick_clock()

            # Marca referências
            win._statusbar_attached = True
            win._statusbar_widget = bar
            win._statusbar_left = lbl_left
            win._statusbar_clock = lbl_clock

            # Aplica tema (se existir infraestrutura)
            try:
                if 'current_theme' in globals() and isinstance(globals().get('current_theme'), dict):
                    pal = globals().get('current_theme')
                    # melhor esforço: pode ser dict com chaves bg/panel/text/muted
                    bg = pal.get('panel') or pal.get('bg')
                    fg = pal.get('muted') or pal.get('text')
                    if bg:
                        bar.configure(bg=bg)
                        lbl_left.configure(bg=bg)
                        lbl_clock.configure(bg=bg)
                    if fg:
                        lbl_left.configure(fg=fg)
                        lbl_clock.configure(fg=fg)
            except Exception:
                pass

        except Exception:
            # Nunca quebrar criação de janelas
            return

    def _tk_init_hook(self, *args, **kwargs):
        _orig_tk_init(self, *args, **kwargs)
        try:
            # agenda após a janela existir
            self.after(1, lambda: _attach_statusbar_later(self))
        except Exception:
            try:
                _attach_statusbar_later(self)
            except Exception:
                pass

    def _top_init_hook(self, *args, **kwargs):
        _orig_top_init(self, *args, **kwargs)
        try:
            self.after(1, lambda: _attach_statusbar_later(self))
        except Exception:
            try:
                _attach_statusbar_later(self)
            except Exception:
                pass

    tk.Tk.__init__ = _tk_init_hook
    tk.Toplevel.__init__ = _top_init_hook

# Instala o hook o quanto antes
try:
    _install_global_statusbar_hook()
except Exception:
    pass
# =================== FIM STATUSBAR GLOBAL ===================

# --- FORÇA STATUSBAR NA JANELA PRINCIPAL (fallback) ---
# Em alguns ambientes o hook global pode não anexar por timing/tema.
# Este fallback cria/mostra o rodapé explicitamente quando chamado.
def force_attach_statusbar(win):
    try:
        if win is None or not hasattr(win, 'winfo_exists') or not win.winfo_exists():
            return
        # Se já existe, apenas garanta que está visível
        bar = getattr(win, '_statusbar_widget', None)
        if bar is not None and hasattr(bar, 'winfo_exists') and bar.winfo_exists():
            try:
                bar.pack_forget()
            except Exception:
                pass
            bar.pack(side='bottom', fill='x', pady=(0, 4))
            try:
                bar.lift()
            except Exception:
                pass
            return
        # Caso não exista, cria igual ao hook, porém com altura/relief para ficar visível
        bar = tk.Frame(win, bd=1, relief='groove')
        bar.pack(side='bottom', fill='x', pady=(0, 4))
        lbl_left = tk.Label(bar, text=_statusbar_text_version_and_license(), anchor='w', padx=10)
        lbl_left.pack(side='left')
        lbl_clock = tk.Label(bar, text='', anchor='e', padx=10)
        lbl_clock.pack(side='right')
        import datetime as _dt
        def _tick_license():
            try:
                lbl_left.config(text=_statusbar_text_version_and_license())
                win.after(60000, _tick_license)
            except Exception:
                return
        def _tick_clock():
            try:
                lbl_clock.config(text=_dt.datetime.now().strftime('%H:%M:%S'))
                win.after(1000, _tick_clock)
            except Exception:
                return
        _tick_license(); _tick_clock()
        win._statusbar_attached = True
        win._statusbar_widget = bar
        win._statusbar_left = lbl_left
        win._statusbar_clock = lbl_clock
        # tema best-effort
        try:
            if 'current_theme' in globals() and isinstance(globals().get('current_theme'), dict):
                pal = globals().get('current_theme')
                bg = pal.get('panel') or pal.get('bg')
                fg = pal.get('muted') or pal.get('text')
                if bg:
                    bar.configure(bg=bg)
                    lbl_left.configure(bg=bg)
                    lbl_clock.configure(bg=bg)
                if fg:
                    lbl_left.configure(fg=fg)
                    lbl_clock.configure(fg=fg)
        except Exception:
            pass
    except Exception:
        return
# --- FIM FORÇA STATUSBAR ---


# ===================== CONFIGURAÇÕES =====================
DISABLE_AUTO_UPDATE = (
    False # <-- Evita que a atualização automática sobrescreva este patch
)
APP_VERSION = "5.3"
OWNER = "andremariano07"
REPO = "besim_company"
BRANCH = "main"
VERSION_FILE = "VERSION"
DB_PATH = "besim_company.db"
IGNORE_FILES = {"besim_company.db"}
IGNORE_DIRS = {"cupons", "relatorios", "OS", "__pycache__", ".git"}
# Caminho base para backups (Google Drive).
# NÃO altera a lógica de backup existente; apenas define o caminho caso não exista.
# Você pode definir via variável de ambiente GOOGLE_DRIVE_BACKUP.
# Caso não definido, será usado um diretório local dentro da pasta do app.
GOOGLE_DRIVE_BACKUP = os.getenv("GOOGLE_DRIVE_BACKUP") or os.path.join(os.getcwd(), "google_drive_backup")

# ===================== LOG =====================
LOG_FILE = "sistema_loja_errors.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ===================== TELEGRAM NOTIFY (uso pessoal) =====================
# Crie um arquivo telegram_config.txt na pasta do app:
# TELEGRAM_BOT_TOKEN=xxxxx
# TELEGRAM_CHAT_ID=8529045753
# TELEGRAM_ENABLED=1
# TELEGRAM_SEND_PDF=1
# (Opcional) TELEGRAM_DEDUPE_HOURS_LOW=6
# (Opcional) TELEGRAM_DEDUPE_HOURS_ZERO=12
import urllib.parse
import urllib.request
import threading
import time

_TELEGRAM_CFG_CACHE = None
_LAST_TG_SENT = {}  # {dedupe_key: last_ts}

def _load_telegram_config():
    """Lê telegram_config.txt (ou variáveis de ambiente)."""
    global _TELEGRAM_CFG_CACHE
    if _TELEGRAM_CFG_CACHE is not None:
        return _TELEGRAM_CFG_CACHE
    cfg = {}
    try:
        path = os.path.join(os.getcwd(), 'telegram_config.txt')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = (line or '').strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        cfg[k.strip()] = v.strip()
    except Exception as ex:
        logging.error('Falha ao ler telegram_config.txt: %s', ex)

    def _get(key, default=None):
        return cfg.get(key) or os.getenv(key) or default

    token = (_get('TELEGRAM_BOT_TOKEN', '') or '').strip()
    chat_id = (_get('TELEGRAM_CHAT_ID', '') or '').strip()
    enabled = str(_get('TELEGRAM_ENABLED', '1')).strip().lower() not in ('0','false','no','off')
    send_pdf = str(_get('TELEGRAM_SEND_PDF', '1')).strip().lower() not in ('0','false','no','off')
    dedupe_low_h = int(float(_get('TELEGRAM_DEDUPE_HOURS_LOW', '6') or 6))
    dedupe_zero_h = int(float(_get('TELEGRAM_DEDUPE_HOURS_ZERO', '12') or 12))

    _TELEGRAM_CFG_CACHE = {
        'token': token,
        'chat_id': chat_id,
        'enabled': enabled,
        'send_pdf': send_pdf,
        'dedupe_low_sec': max(60, dedupe_low_h * 3600),
        'dedupe_zero_sec': max(60, dedupe_zero_h * 3600),
    }
    return _TELEGRAM_CFG_CACHE


def telegram_notify(text: str, dedupe_key: str = None, dedupe_window_sec: int = 30):
    """Envia mensagem Telegram em background (não trava UI)."""
    try:
        cfg = _load_telegram_config()
        if not cfg.get('enabled', True):
            return
        token = (cfg.get('token') or '').strip()
        chat_id = (cfg.get('chat_id') or '').strip()
        if not token or not chat_id:
            return

        if dedupe_key:
            now = time.time()
            last = _LAST_TG_SENT.get(dedupe_key, 0)
            if (now - last) < int(dedupe_window_sec):
                return
            _LAST_TG_SENT[dedupe_key] = now

        def _send():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': 'true',
                }
                data = urllib.parse.urlencode(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, method='POST')
                with urllib.request.urlopen(req, context=_SSL_CTX, timeout=10) as r:
                    _ = r.read()
            except Exception as ex:
                logging.error('Erro ao enviar Telegram: %s', ex)

        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass


def telegram_send_pdf(caption: str, file_path: str, dedupe_key: str = None, dedupe_window_sec: int = 30):
    """Envia PDF para o Telegram (opcional)."""
    try:
        cfg = _load_telegram_config()
        if not cfg.get('enabled', True) or not cfg.get('send_pdf', True):
            return
        token = (cfg.get('token') or '').strip()
        chat_id = (cfg.get('chat_id') or '').strip()
        if not token or not chat_id:
            return
        if not file_path or not os.path.isfile(file_path):
            return

        if dedupe_key:
            now = time.time()
            last = _LAST_TG_SENT.get(dedupe_key, 0)
            if (now - last) < int(dedupe_window_sec):
                return
            _LAST_TG_SENT[dedupe_key] = now

        def _send_doc():
            try:
                boundary = '----TGBOUNDARY1234567890'
                url = f"https://api.telegram.org/bot{token}/sendDocument"
                with open(file_path, 'rb') as f:
                    file_bytes = f.read()

                parts = []
                def add_field(name, value):
                    parts.append(f"--{boundary}\r\n".encode())
                    parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
                    parts.append((value or '').encode('utf-8'))
                    parts.append(b"\r\n")

                def add_file(name, filename, content_type, content):
                    parts.append(f"--{boundary}\r\n".encode())
                    parts.append(
                        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                        f"Content-Type: {content_type}\r\n\r\n".encode()
                    )
                    parts.append(content)
                    parts.append(b"\r\n")

                add_field('chat_id', chat_id)
                add_field('caption', caption or '')
                add_file('document', os.path.basename(file_path), 'application/pdf', file_bytes)
                parts.append(f"--{boundary}--\r\n".encode())
                body = b''.join(parts)

                req = urllib.request.Request(url, data=body, method='POST')
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('Content-Length', str(len(body)))
                with urllib.request.urlopen(req, context=_SSL_CTX, timeout=25) as r:
                    _ = r.read()
            except Exception as ex:
                logging.error('Erro ao enviar PDF no Telegram: %s', ex)

        threading.Thread(target=_send_doc, daemon=True).start()
    except Exception:
        pass

# =================== FIM TELEGRAM NOTIFY ===================

# ===================== AGENDAMENTO: NOTIFICAÇÃO (hoje ao abrir) =====================
def _meta_get(key: str, default: str = "") -> str:
    """Lê uma chave da tabela app_meta."""
    try:
        cursor.execute("SELECT value FROM app_meta WHERE key=?", (key,))
        r = cursor.fetchone()
        if r and r[0] is not None:
            return str(r[0])
    except Exception:
        pass
    return default


def _meta_set(key: str, value: str):
    """Grava uma chave na tabela app_meta."""
    try:
        with conn:
            cursor.execute(
                "INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)",
                (key, str(value)),
            )
    except Exception:
        pass


def notify_agendamentos_hoje_once():
    """Se houver agendamento para HOJE, envia Telegram uma vez por dia (ao abrir o sistema)."""
    try:
        hoje = datetime.date.today()
        iso = hoje.strftime("%Y-%m-%d")
        meta_key = f"ag_today_notified_{iso}"
        if _meta_get(meta_key, "0") == "1":
            return

        cursor.execute("SELECT responsavel FROM agendamentos_celulares WHERE data_iso=?", (iso,))
        r = cursor.fetchone()
        texto = (r[0] if r and r[0] else "").strip()
        if not texto:
            return

        nomes = [l.strip() for l in texto.splitlines() if l.strip()]
        qtd = len(nomes)
        br = hoje.strftime("%d/%m/%Y")
        lista = "\n".join(nomes)
        msg = (
            "📅 <b>RETIRADAS HOJE</b>\n"
            f"🗓 Data: {br}\n"
            f"👥 Responsáveis: {qtd}\n\n"
            f"{lista}"
        )
        telegram_notify(
            msg,
            dedupe_key=f"ag_hoje_{iso}",
            dedupe_window_sec=120,
        )

        _meta_set(meta_key, "1")
    except Exception:
        pass


def start_agendamento_notify_on_open(root_widget):
    """Agenda a checagem para alguns segundos após abrir o sistema."""
    try:
        root_widget.after(2500, notify_agendamentos_hoje_once)
    except Exception:
        notify_agendamentos_hoje_once()



# ===================== AGENDAMENTO: DEVEDORES (cobrança no dia) =====================
def notify_devedores_hoje_once():
    """Se houver devedores com vencimento HOJE, envia Telegram uma vez por dia (ao abrir / em background)."""
    try:
        hoje = datetime.date.today()
        iso = hoje.strftime("%Y-%m-%d")
        meta_key = f"dev_today_notified_{iso}"
        if _meta_get(meta_key, "0") == "1":
            return

        cursor.execute(
            """SELECT nome, cpf, COALESCE(valor,0) AS valor
               FROM devedores
               WHERE data_iso=? AND COALESCE(pago,0)=0
               ORDER BY nome""",
            (iso,),
        )
        rows = cursor.fetchall() or []
        if not rows:
            return

        br = hoje.strftime("%d/%m/%Y")
        total = sum(float(r[2] or 0.0) for r in rows)
        linhas = []
        for nome, cpf, valor in rows:
            nome = (nome or "(sem nome)").strip()
            cpf = (cpf or "").strip()
            try:
                v = float(valor or 0.0)
            except Exception:
                v = 0.0
            linhas.append(f"• {nome} ({cpf}) — R$ {v:.2f}")

        msg = (
            f"💰 <b>COBRAR HOJE</b>\n"
            f"🗓 Data: {br}\n"
            f"👥 Devedores: {len(rows)}\n"
            f"💵 Total: R$ {total:.2f}\n\n"
            + "\n".join(linhas)
        )
        telegram_notify(
            msg,
            dedupe_key=f"dev_hoje_{iso}",
            dedupe_window_sec=120,
        )
        _meta_set(meta_key, "1")
    except Exception:
        pass


def start_devedores_notify_on_open(root_widget):
    """Agenda a checagem de devedores (HOJE) alguns segundos após abrir e depois periodicamente."""
    def _tick():
        try:
            notify_devedores_hoje_once()
        finally:
            try:
                # Revalida a cada 60 minutos para cobrir virada do dia com o app aberto
                root_widget.after(60 * 60 * 1000, _tick)
            except Exception:
                pass

    try:
        root_widget.after(3200, _tick)
    except Exception:
        try:
            _tick()
        except Exception:
            pass

# ===================== FIM AGENDAMENTO: DEVEDORES =====================
# ===================== FIM AGENDAMENTO: NOTIFICAÇÃO =====================


# ===================== BANCO =====================
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# >>> NOVO: garante tabela CLIENTES (evita erro: no such table: clientes)
def ensure_clientes_table_and_columns():
    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS clientes (cpf TEXT PRIMARY KEY, nome TEXT, telefone TEXT)")
        # Migração segura: adiciona colunas faltantes se o banco for antigo
        cursor.execute("PRAGMA table_info(clientes)")
        cols = {c[1] for c in (cursor.fetchall() or [])}
        altered = False
        if 'telefone' not in cols:
            cursor.execute("ALTER TABLE clientes ADD COLUMN telefone TEXT")
            altered = True
        if 'nome' not in cols:
            cursor.execute("ALTER TABLE clientes ADD COLUMN nome TEXT")
            altered = True
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome)")
        conn.commit()
    except Exception:
        try:
            conn.commit()
        except Exception:
            pass

ensure_clientes_table_and_columns()
# <<< FIM NOVO: CLIENTES

# >>> NOVO: agendamento de retirada de celulares
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS agendamentos_celulares (
    data_iso TEXT PRIMARY KEY,
    responsavel TEXT,
    atualizado_em TEXT
)
"""
)
conn.commit()

# >>> NOVO: Licença do app (1 instalação = 1 licença ativa)
cursor.execute(
    """CREATE TABLE IF NOT EXISTS app_licenca (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    machine_id TEXT,
    chave TEXT,
    expira_em TEXT,        -- ISO: YYYY-MM-DD
    ativada_em TEXT,       -- ISO: YYYY-MM-DD HH:MM:SS
    atualizado_em TEXT     -- ISO: YYYY-MM-DD HH:MM:SS
)
"""
)
conn.commit()



# >>> NOVO: meta de app (flags de migração)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""
)
conn.commit()

# >>> ATUALIZADO: tabela caixa já contempla hora e motivo para novos bancos
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL,
    data TEXT,
    hora TEXT,
    motivo TEXT
)
"""
)
# >>>>>> NOVO: Tabela Devedores (cobranças)
cursor.execute("""
CREATE TABLE IF NOT EXISTS devedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT,
    nome TEXT,
    data_pagamento TEXT,
    data_iso TEXT,
    valor REAL,
    pago INTEGER DEFAULT 0,
    criado_em TEXT,
    pago_em TEXT
)
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_devedores_data_iso ON devedores(data_iso)")
conn.commit()
# <<<<<< FIM NOVO: Devedores

cursor.execute("""
CREATE TABLE IF NOT EXISTS devolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT,
    motivo TEXT,
    nome TEXT,
    data TEXT,
    hora TEXT
)
""")
conn.commit()
# <<<<<< FIM NOVO: Devedores

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS fechamento_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT UNIQUE,
    total REAL
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS manutencao (
    os INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT,
    nome TEXT,
    telefone TEXT,
    descricao TEXT,
    data TEXT,
    valor REAL DEFAULT 0,
    aprovado INTEGER DEFAULT 0
)
"""
)
# >>> NOVO: Pontuação (Programa de Pontos)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS pontuacao (
    cpf TEXT PRIMARY KEY,
    pontos INTEGER DEFAULT 0,
    atualizado_em TEXT
)
"""
)

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS produtos (
    codigo TEXT PRIMARY KEY,
    nome TEXT,
    tipo TEXT,
    custo REAL,
    preco REAL,
    estoque INTEGER
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS resgates_pontos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT,
    item TEXT,
    pontos_usados INTEGER,
    data TEXT,
    hora TEXT
)
"""
)
conn.commit()
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT,
    is_admin INTEGER DEFAULT 0
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    cpf TEXT,
    produto TEXT,
    quantidade INTEGER,
    total REAL,
    pagamento TEXT,
    data TEXT,
    hora TEXT
)
"""
)
# <<< FIM NOVO: Pontuação
# ====== UTIL: hash de senha / migrações ======
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()
def ensure_is_admin_column():
    try:
        cursor.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cursor.fetchall()]
        if "is_admin" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass
ensure_is_admin_column()

# >>> NOVO: força troca de senha no primeiro login
def ensure_force_password_change_column():
    try:
        cursor.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cursor.fetchall()]
        if "force_password_change" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN force_password_change INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass

ensure_force_password_change_column()

# >>> NOVO: força troca de senha para TODOS os usuários UMA ÚNICA VEZ (primeira execução desta versão)
def run_force_password_change_migration_once():
    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        cursor.execute("SELECT value FROM app_meta WHERE key=?", ('forced_pw_change_v1',))
        r = cursor.fetchone()
        if r and str(r[0] or '').strip() == '1':
            return
        cursor.execute("UPDATE users SET force_password_change=1")
        cursor.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)", ('forced_pw_change_v1','1'))
        conn.commit()
    except Exception:
        pass

run_force_password_change_migration_once()


def ensure_admin_user():
    try:
        cursor.execute("SELECT username, is_admin, COALESCE(password_last_changed,'') FROM users WHERE username=?", ("admin",))
        r = cursor.fetchone()
        today = datetime.datetime.now().strftime("%d/%m/%Y")
        if not r:
            admin_hash = hash_password("admin1234")
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin, password_last_changed, force_password_change) VALUES (?,?,1,?,1)",
                ("admin", admin_hash, today)
            )
            cursor.execute(
                "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                ("admin", admin_hash, today)
            )
            conn.commit()
        else:
            if r[1] != 1:
                cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", ("admin",))
            if not r[2]:
                cursor.execute("SELECT password_hash FROM users WHERE username=?", ("admin",))
                cur_hash = cursor.fetchone()[0]
                cursor.execute("UPDATE users SET password_last_changed=? WHERE username=?", (today, "admin"))
                cursor.execute(
                    "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                    ("admin", cur_hash, today)
                )
            conn.commit()
    except Exception:
        pass

ensure_admin_user()

# >>> NOVO: migração segura das colunas hora/motivo da tabela caixa (para bancos existentes)
def ensure_caixa_columns():
    try:
        cursor.execute("PRAGMA table_info(caixa)")
        cols = {c[1] for c in cursor.fetchall()}
        altered = False
        if "hora" not in cols:
            cursor.execute("ALTER TABLE caixa ADD COLUMN hora TEXT")
            altered = True
        if "motivo" not in cols:
            cursor.execute("ALTER TABLE caixa ADD COLUMN motivo TEXT")
            altered = True
        if altered:
            conn.commit()
    except Exception:
        pass
ensure_caixa_columns()


def ensure_password_policy_tables():
    # Tabela de histórico de senhas (uma entrada por troca)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS user_password_history (
        username TEXT,
        password_hash TEXT,
        changed_at TEXT,
        PRIMARY KEY (username, changed_at)
    )
    """
    )
    # Adiciona coluna 'password_last_changed' na tabela users, se ainda não existir
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "password_last_changed" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN password_last_changed TEXT")
        conn.commit()

ensure_password_policy_tables()


# ===================== PONTUAÇÃO (1 R$ = 1 ponto) =====================
PONTOS_POR_REAL = 1
CUSTO_CAPA_PONTOS = 300
CUSTO_PELICULA_PONTOS = 250

def _pontos_de_valor(valor: float) -> int:
    """Converte um valor em R$ para pontos (inteiro).
    Regra solicitada: truncar (ex.: R$ 29,90 -> 29 pontos).
    """
    try:
        v = float(valor or 0.0)
    except Exception:
        v = 0.0
    v = max(0.0, v)
    return max(0, int(v * float(PONTOS_POR_REAL)))

def get_pontos_cliente(cpf: str) -> int:
    try:
        cpf = (cpf or '').strip()
        if not cpf:
            return 0
        cursor.execute("SELECT COALESCE(pontos,0) FROM pontuacao WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        return int(r[0]) if r else 0
    except Exception:
        return 0

def set_pontos_cliente(cpf: str, pontos: int):
    cpf = (cpf or '').strip()
    if not cpf:
        return
    try:
        pts = int(pontos or 0)
    except Exception:
        pts = 0
    pts = max(0, pts)
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with conn:
        cursor.execute(
            "INSERT OR REPLACE INTO pontuacao(cpf,pontos,atualizado_em) VALUES(?,?,?)",
            (cpf, pts, agora),
        )

def adicionar_pontos_cliente(cpf: str, valor_em_reais: float) -> int:
    """Adiciona pontos ao cliente com base no valor final pago."""
    cpf = (cpf or '').strip()
    if not cpf:
        return 0
    pts_add = _pontos_de_valor(valor_em_reais)
    if pts_add <= 0:
        return 0
    set_pontos_cliente(cpf, get_pontos_cliente(cpf) + pts_add)
    return pts_add

@ui_safe('Pontuação')
def registrar_resgate_pontos(cpf: str, item: str) -> tuple:
    """Registra resgate (Capa/Película) e debita pontos.
    Retorna (ok, msg, novo_saldo).
    """
    cpf = (cpf or '').strip()
    item = (item or '').strip()
    if not cpf:
        return False, "CPF inválido.", 0
    if item not in ("Capa", "Película", "Pelicula"):
        return False, "Item inválido. Use Capa ou Película.", get_pontos_cliente(cpf)

    custo = CUSTO_CAPA_PONTOS if item == "Capa" else CUSTO_PELICULA_PONTOS
    saldo = get_pontos_cliente(cpf)
    if saldo < custo:
        return False, f"Pontos insuficientes. Saldo: {saldo} pts. Necessário: {custo} pts.", saldo

    novo = max(0, saldo - custo)
    data = datetime.datetime.now().strftime("%d/%m/%Y")
    hora = datetime.datetime.now().strftime("%H:%M:%S")
    with conn:
        set_pontos_cliente(cpf, novo)
        cursor.execute(
            "INSERT INTO resgates_pontos(cpf,item,pontos_usados,data,hora) VALUES(?,?,?,?,?)",
            (cpf, "Película" if item in ("Película", "Pelicula") else "Capa", int(custo), data, hora),
        )
    return True, f"Resgate registrado: {item} (-{custo} pts).", novo

def run_pontos_migration_once():
    """Migra pontos iniciais a partir do histórico de vendas (uma vez)."""
    try:
        cursor.execute("SELECT value FROM app_meta WHERE key=?", ('pontos_migracao_v1',))
        r = cursor.fetchone()
        if r and str(r[0] or '').strip() == '1':
            return
        cursor.execute("SELECT COUNT(1) FROM pontuacao")
        if int(cursor.fetchone()[0] or 0) > 0:
            cursor.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)", ('pontos_migracao_v1','1'))
            conn.commit()
            return
        cursor.execute("SELECT cpf, COALESCE(SUM(total),0) FROM vendas GROUP BY cpf")
        for cpf, soma in (cursor.fetchall() or []):
            cpf = (cpf or '').strip()
            if not cpf:
                continue
            set_pontos_cliente(cpf, _pontos_de_valor(float(soma or 0.0)))
        cursor.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)", ('pontos_migracao_v1','1'))
        conn.commit()
    except Exception:
        pass

# Executa migração inicial de pontos (apenas 1 vez)
run_pontos_migration_once()

# ====== POLÍTICA DE SENHA (centralizada) ======
PASSWORD_MIN_LEN = 8

def validate_password_policy(pw: str):
    """
    Regras:
    - mínimo 8 caracteres
    - pelo menos 1 letra maiúscula (A-Z)
    - pelo menos 1 número (0-9)
    """
    pw = (pw or "").strip()
    if len(pw) < PASSWORD_MIN_LEN:
        return False, f"A senha deve ter pelo menos {PASSWORD_MIN_LEN} caracteres."
    if not re.search(r"[A-Z]", pw):
        return False, "A senha deve conter pelo menos 1 letra MAIÚSCULA (A-Z)."
    if not re.search(r"\d", pw):
        return False, "A senha deve conter pelo menos 1 número (0-9)."
    return True, "OK"


# Utilitários de política de senha (30 dias + últimas 3)
def _parse_br_date(d: str):
    try:
        return datetime.datetime.strptime(d, "%d/%m/%Y").date()
    except Exception:
        return None

def days_since_last_change(username: str) -> int:
    try:
        cursor.execute("SELECT password_last_changed FROM users WHERE username=?", (username,))
        d = cursor.fetchone()
        if not d or not d[0]:
            return 9999
        dt = _parse_br_date(d[0])
        if not dt:
            return 9999
        return (datetime.date.today() - dt).days
    except Exception:
        return 9999

def get_last_password_hashes(username: str, n: int = 3):
    cursor.execute(
        "SELECT password_hash FROM user_password_history WHERE username=? ORDER BY date(substr(changed_at,7,4)||'-'||substr(changed_at,4,2)||'-'||substr(changed_at,1,2)) DESC",
        (username,)
    )
    rows = cursor.fetchall()
    return [r[0] for r in rows[:n]]

def password_reuse_forbidden(username: str, new_hash: str, n: int = 3) -> bool:
    return new_hash in get_last_password_hashes(username, n)

def set_new_password(username: str, new_plain: str):
    """Define nova senha aplicando política (complexidade), histórico e marcação de primeira troca."""
    ok, msg = validate_password_policy(new_plain)
    if not ok:
        raise ValueError(msg)

    new_hash = hash_password(new_plain)
    if password_reuse_forbidden(username, new_hash, 3):
        raise ValueError("A nova senha não pode repetir nenhuma das últimas 3 senhas.")

    today = datetime.datetime.now().strftime("%d/%m/%Y")
    with conn:
        cursor.execute(
            "UPDATE users SET password_hash=?, password_last_changed=?, force_password_change=0 WHERE username=?",
            (new_hash, today, username),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
            (username, new_hash, today),
        )




# ====== Criação de usuário restrita a ADMIN ======
def create_user_admin(current_user: str, new_username: str, new_password_plain: str, make_admin: int = 0):
    """Cria novo usuário *apenas* se current_user for admin.
    Aplica política de senha, marca force_password_change=1 no novo usuário
    e registra no histórico de senhas."""
    if not is_admin(current_user):
        raise PermissionError("Apenas administradores podem criar usuários.")
    ok, msg = validate_password_policy(new_password_plain)
    if not ok:
        raise ValueError(msg)
    new_hash = hash_password(new_password_plain)
    today = datetime.datetime.now().strftime("%d/%m/%Y")
    with conn:
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin, password_last_changed, force_password_change) VALUES (?,?,?,?,1)",
            (new_username, new_hash, int(make_admin), today)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
            (new_username, new_hash, today)
        )

def is_admin(username: str) -> bool:
    try:
        cursor.execute("SELECT is_admin FROM users WHERE username=?", (username,))
        r = cursor.fetchone()
        return bool(r and r[0] == 1)
    except Exception:
        return False


# ===================== LICENÇA DO APP (30 dias) =====================
# Regra solicitada: válida ATÉ O FIM DO DIA do vencimento.
LICENCA_DIAS = 30

# IMPORTANTE:
# Troque esse segredo por um valor grande e único (e mantenha privado).
# Em EXE ainda é possível engenharia reversa, mas isso já evita chaves fáceis.
LICENSE_SECRET = b"MUDE-ESSE-SEGREDO-PRA-UM-VALOR-GRANDE-E-UNICO-123456789"

def _today_date():
    return datetime.date.today()

def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _add_days_iso(days: int):
    return (_today_date() + datetime.timedelta(days=int(days))).strftime("%Y-%m-%d")

def get_machine_id() -> str:
    """Identificador simples do computador para amarrar a licença."""
    try:
        base = f"{platform.node()}|{platform.system()}|{platform.release()}|{getpass.getuser()}|{sys.platform}"
    except Exception:
        base = f"{platform.node()}|{platform.system()}|{platform.release()}|{sys.platform}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest().upper()

def _hmac8(data: str) -> str:
    sig = hmac.new(LICENSE_SECRET, data.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return sig[:8]

def gerar_chave_licenca(expira_em_iso: str, machine_id: str = None) -> str:
    """Formato: YYYYMMDD-MID8-RND4-SIG8"""
    machine_id = (machine_id or get_machine_id()).upper()
    exp = (expira_em_iso or "").replace("-", "")
    mid8 = machine_id[:8]
    rnd4 = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
    payload = f"{exp}-{mid8}-{rnd4}"
    sig8 = _hmac8(payload)
    return f"{exp}-{mid8}-{rnd4}-{sig8}"

def validar_chave_licenca(chave: str, machine_id: str = None):
    """Retorna (ok, msg, expira_iso)."""
    try:
        machine_id = (machine_id or get_machine_id()).upper()
        key = (chave or "").strip().upper()
        parts = key.split("-")
        if len(parts) != 4:
            return False, "Formato inválido. Use: YYYYMMDD-XXXX-XXXX-XXXX", ""
        exp_yyyymmdd, mid8, rnd4, sig8 = parts
        if len(exp_yyyymmdd) != 8 or (not exp_yyyymmdd.isdigit()):
            return False, "Data inválida na chave.", ""
        expira_iso = f"{exp_yyyymmdd[0:4]}-{exp_yyyymmdd[4:6]}-{exp_yyyymmdd[6:8]}"
        if mid8 != machine_id[:8]:
            return False, "Esta chave não corresponde a este computador.", ""
        payload = f"{exp_yyyymmdd}-{mid8}-{rnd4}"
        expected = _hmac8(payload)
        if not hmac.compare_digest(expected, sig8):
            return False, "Assinatura inválida (chave adulterada).", ""
        # Válida ATÉ o fim do dia: expira só quando hoje > exp_date
        exp_date = datetime.datetime.strptime(expira_iso, "%Y-%m-%d").date()
        if _today_date() > exp_date:
            return False, "Chave vencida. Solicite uma nova.", expira_iso
        return True, "OK", expira_iso
    except Exception as ex:
        return False, f"Erro ao validar chave: {ex}", ""

def obter_licenca_db():
    try:
        cursor.execute("SELECT machine_id, chave, expira_em FROM app_licenca WHERE id=1")
        r = cursor.fetchone()
        if not r:
            return None
        return {"machine_id": r[0] or "", "chave": r[1] or "", "expira_em": r[2] or ""}
    except Exception:
        return None

def salvar_licenca_db(machine_id: str, chave: str, expira_em_iso: str):
    now = _now_iso()
    with conn:
        cursor.execute(
            """INSERT INTO app_licenca (id, machine_id, chave, expira_em, ativada_em, atualizado_em)
VALUES (1, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    machine_id=excluded.machine_id,
    chave=excluded.chave,
    expira_em=excluded.expira_em,
    atualizado_em=excluded.atualizado_em
""",
            (machine_id, chave, expira_em_iso, now, now),
        )

def licenca_valida_local():
    lic = obter_licenca_db()
    if not lic:
        return False, "Licença não ativada."
    ok, msg, _exp = validar_chave_licenca(lic.get("chave", ""), lic.get("machine_id", ""))
    return ok, msg


def get_tempo_restante_licenca_str():
    """Retorna string amigável para exibir na status bar com o tempo restante da licença."""
    try:
        lic = obter_licenca_db()
        if not lic or not (lic.get("expira_em") or "").strip():
            return "Licença: não ativada"
        expira_iso = (lic.get("expira_em") or "").strip()  # YYYY-MM-DD
        exp_date = datetime.datetime.strptime(expira_iso, "%Y-%m-%d").date()
        hoje = datetime.date.today()
        # Regra do app: válida ATÉ o fim do dia do vencimento
        if hoje == exp_date:
            return "Licença expira hoje"
        if hoje < exp_date:
            dias = (exp_date - hoje).days
            return f"Licença: {dias} dia(s) restante(s)"
        dias = (hoje - exp_date).days
        return f"Licença vencida há {dias} dia(s)"
    except Exception:
        return "Licença: indisponível"


def bind_licenca_statusbar_auto_update(root_widget, label_widget, interval_ms=60000):
    """Atualiza periodicamente a label da status bar com o tempo restante da licença."""
    def _tick():
        try:
            label_widget.config(text=get_tempo_restante_licenca_str())
        except Exception:
            pass
        try:
            root_widget.after(int(interval_ms), _tick)
        except Exception:
            pass
    _tick()

def mostrar_dialogo_licenca(master=None):
    """Exige uma chave válida para liberar o app. Retorna True se ativar."""
    try:
        ok, _msg = licenca_valida_local()
        if ok:
            return True
    except Exception:
        pass

    # Evita conflito de múltiplos Tk(): cria root temporário e destrói no fim.
    tmp_root = None
    try:
        if master is None:
            tmp_root = tk.Tk()
            tmp_root.withdraw()
            master = tmp_root
    except Exception:
        master = None

    machine_id = get_machine_id()
    win = tk.Toplevel(master) if master else tk.Tk()
    win.title("Ativação do Sistema - Licença")
    win.resizable(False, False)
    win.geometry("560x320")

    frm = ttk.Frame(win, padding=14)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Licença necessária para liberar o sistema.", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    ttk.Label(frm, text="Cole a chave de acesso recebida.\nA licença é válida por 30 dias e expira ao fim do dia do vencimento.", font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 10))

    ttk.Label(frm, text=f"ID deste computador: {machine_id[:8]}…", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

    ttk.Label(frm, text="Chave:", font=("Segoe UI", 10)).pack(anchor="w")
    ent = ttk.Entry(frm, width=46)
    ent.pack(anchor="w", pady=6)

    lbl_status = ttk.Label(frm, text="", foreground="red")
    lbl_status.pack(anchor="w", pady=(6, 0))

    result = {"ok": False}

    def _ativar():
        key = ent.get().strip()
        ok, msg, exp = validar_chave_licenca(key, machine_id)
        if not ok:
            lbl_status.config(text=msg)
            return
        salvar_licenca_db(machine_id, key, exp)
        result["ok"] = True
        try:
            win.destroy()
        except Exception:
            pass

    def _sair():
        result["ok"] = False
        try:
            win.destroy()
        except Exception:
            pass

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=14)
    ttk.Button(btns, text="Sair", style="Secondary.TButton", command=_sair).pack(side="right", padx=6)
    ttk.Button(btns, text="Ativar", style="Success.TButton", command=_ativar).pack(side="right", padx=6)

    win.bind("<Return>", lambda e: _ativar())
    win.protocol("WM_DELETE_WINDOW", _sair)

    try:
        win.grab_set()
        win.focus_force()
        win.wait_window()
    except Exception:
        pass

    try:
        if tmp_root is not None:
            tmp_root.destroy()
    except Exception:
        pass

    return result["ok"]




def enviar_chave_licenca_email(destinatario_email: str, chave: str, expira_iso: str):
    """Envia a chave de licença por e-mail.

    - Envia multipart: texto simples (fallback) + HTML.
    - Inclui logo centralizada inline (CID) usando o arquivo "Logo_email" (preferência) na pasta do app.
    """
    try:
        cfg = _load_email_config()
        EMAIL_REMETENTE = cfg.get("EMAIL_GMAIL") or os.getenv("EMAIL_GMAIL")
        SENHA_APP = cfg.get("EMAIL_GMAIL_APP") or os.getenv("EMAIL_GMAIL_APP")
        if not EMAIL_REMETENTE or not SENHA_APP:
            return False, "Credenciais de e-mail não configuradas."
        if not destinatario_email or "@" not in destinatario_email:
            return False, "E-mail inválido."

        msg = EmailMessage()
        msg["Subject"] = f"Chave de acesso - Licença ({LICENCA_DIAS} dias)"
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = destinatario_email

        # Fallback em texto simples
        text = (
            "Olá!\n\n"
            f"Segue sua chave de acesso (válida por {LICENCA_DIAS} dias):\n\n"
            f"CHAVE: {chave}\n"
            f"Válida até: {expira_iso} (fim do dia)\n\n"
            "Cole esta chave na tela de ativação do sistema.\n\n"
            "Atenciosamente,\n"
            "AM CORPY\n"
        )
        msg.set_content(text)

        # Logo (inline CID) — preferência: Logo_email.(png/jpg/jpeg) na pasta do app
        logo_path = None
        base = os.path.join(os.getcwd(), "Logo_email")
        for cand in (base + ".png", base + ".jpg", base + ".jpeg", base):
            if os.path.isfile(cand):
                logo_path = cand
                break
        if not logo_path:
            cand = str(P('logo.png'))
            if os.path.isfile(cand):
                logo_path = cand

        logo_cid = make_msgid(domain="besim.local")
        logo_cid_str = logo_cid[1:-1]

        logo_html = ""
        if logo_path:
            logo_html = (
                "<tr>"
                "<td align='center' style='padding:24px 22px 8px 22px;'>"
                f"<img src='cid:{logo_cid_str}' alt='BESIM COMPANY' "
                "style='display:block;max-width:260px;width:260px;height:auto;' />"
                "</td>"
                "</tr>"
            )

        html = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7fb;font-family:Segoe UI, Arial, sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7fb;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="620" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 6px 18px rgba(0,0,0,.06);">
            {logo_html}
            <tr>
              <td style="padding:0 22px 18px 22px;text-align:center;">
                <div style="font-size:16px;font-weight:800;color:#111827;">Chave de acesso</div>
                <div style="font-size:13px;color:#6b7280;">Licença ({LICENCA_DIAS} dias) — válida até {expira_iso} (fim do dia)</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 22px 22px 22px;color:#111827;">
                <p style="margin:0 0 12px 0;font-size:14px;">Olá! 👋</p>
                <p style="margin:0 0 14px 0;font-size:14px;">Segue sua chave de acesso válida por <b>{LICENCA_DIAS} dias</b>.</p>
                <div style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:10px;padding:14px;text-align:left;">
                  <div style="font-size:12px;color:#6b7280;margin-bottom:6px;">CHAVE</div>
                  <div style="font-size:16px;font-weight:800;letter-spacing:.5px;font-family:Consolas, monospace;word-break:break-word;">{chave}</div>
                  <div style="margin-top:10px;font-size:13px;"><b>Válida até:</b> {expira_iso} <span style="color:#6b7280;">(fim do dia)</span></div>
                </div>
                <p style="margin:14px 0 0 0;font-size:14px;">👉 Cole esta chave na tela de ativação do sistema.</p>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;">
                <p style="margin:0;font-size:13px;color:#374151;">Atenciosamente,<br><b>BESIM COMPANY</b></p>
              </td>
            </tr>
          </table>
          <div style="width:620px;text-align:center;color:#9ca3af;font-size:12px;margin-top:10px;">Este e-mail foi enviado automaticamente.</div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
        msg.add_alternative(html, subtype="html")

        if logo_path:
            ctype, _enc = mimetypes.guess_type(logo_path)
            if not ctype:
                ctype = "image/png"
            maintype, subtype = ctype.split("/", 1)
            with open(logo_path, "rb") as fimg:
                img_bytes = fimg.read()
            html_part = msg.get_payload()[-1]
            html_part.add_related(img_bytes, maintype=maintype, subtype=subtype, cid=logo_cid)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(EMAIL_REMETENTE, SENHA_APP)
            smtp.send_message(msg)
        return True, "OK"
    except Exception as e:
        return False, f"Falha ao enviar e-mail: {e}"

def admin_gerar_enviar_licenca_dialog(master):
    """Ferramenta simples (admin) para gerar e enviar chave para um cliente."""
    try:
        win = tk.Toplevel(master)
        win.title("Licença (Admin) - Gerar/Enviar Chave")
        win.resizable(False, False)
        win.geometry("560x320")

        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Gerar e enviar chave de licença (30 dias)", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frm, text="E-mail do cliente:").grid(row=1, column=0, sticky="w")
        ent_email = ttk.Entry(frm, width=40)
        ent_email.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="ID do PC do cliente (8 primeiros):").grid(row=2, column=0, sticky="w")
        ent_mid8 = ttk.Entry(frm, width=16)
        ent_mid8.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="Obs.: o cliente vê esse ID na tela de ativação.").grid(row=3, column=1, sticky="w", pady=(0, 8))

        lbl_out = ttk.Label(frm, text="", foreground="#6b7280")
        lbl_out.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def _gerar_e_enviar():
            email = (ent_email.get() or "").strip()
            mid8 = (ent_mid8.get() or "").strip().upper()
            if len(mid8) != 8:
                messagebox.showwarning("Atenção", "Informe os 8 primeiros caracteres do ID do PC do cliente.")
                return
            exp = _add_days_iso(LICENCA_DIAS)
            fake_mid = mid8 + "0" * 56
            chave = gerar_chave_licenca(exp, fake_mid)
            ok, msg = enviar_chave_licenca_email(email, chave, exp)
            if ok:
                try:
                    win.clipboard_clear(); win.clipboard_append(chave)
                except Exception:
                    pass
                lbl_out.config(text=f"Chave enviada! Válida até {exp} (fim do dia). (Chave copiada)")
                messagebox.showinfo("Licença", f"""Chave enviada para {email}.
Válida até {exp} (fim do dia).

Chave: {chave}""")
            else:
                messagebox.showerror("Licença", msg)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=14)
        ttk.Button(btns, text="Fechar", style="Secondary.TButton", command=win.destroy).pack(side="right", padx=6)
        ttk.Button(btns, text="Gerar e Enviar", style="Success.TButton", command=_gerar_e_enviar).pack(side="right", padx=6)

        frm.grid_columnconfigure(1, weight=1)
        try:
            win.transient(master)
            win.grab_set()
        except Exception:
            pass
    except Exception as ex:
        logging.error(f"Erro ao abrir diálogo de licença admin: {ex}")
# ===================== EXCEPTIONS TK (assinatura corrigida) =====================
def setup_global_exception_handlers(tk_root: tk.Misc):
    def excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            msg = f"Ocorreu um erro inesperado:\n{exc_value}\n\nDetalhes foram gravados em: {LOG_FILE}"
            messagebox.showerror("Erro inesperado", msg)
        except Exception:
            pass
    sys.excepthook = excepthook
    # Assinatura correta para Tkinter: (exc, val, tb)
    def tk_callback_exception(exc, val, tb):
        logging.error("Tkinter callback exception", exc_info=(exc, val, tb))
        try:
            msg = f"Ocorreu um erro na interface:\n{val}\n\nDetalhes foram gravados em: {LOG_FILE}"
            messagebox.showerror("Erro na interface", msg)
        except Exception:
            pass
    try:
        tk_root.report_callback_exception = tk_callback_exception
    except Exception:
        pass
# ===================== FOCO PÓS-PDF =====================
def bring_app_to_front():
    """Recoloca a janela do app na frente após abrir viewer externo."""
    try:
        root = tk._default_root
        if root and root.winfo_exists():
            root.lift()
            root.focus_force()
            try:
                root.attributes("-topmost", True)
                root.after(200, lambda: root.attributes("-topmost", False))
            except Exception:
                pass
    except Exception:
        pass



# ===================== FERRAMENTA: ABRIR 3uTools (Windows) =====================
def abrir_3utools(parent=None):
    """Abre o 3uTools diretamente pelo executável no Windows."""
    caminho = r"C:\\Program Files (x86)\\3uToolsV3\\3uTools.exe"
    try:
        if not os.path.exists(caminho):
            try:
                messagebox.showerror("Erro", f"O 3uTools não foi encontrado neste caminho:\n{caminho}", parent=parent)
            except Exception:
                messagebox.showerror("Erro", f"O 3uTools não foi encontrado neste caminho:\n{caminho}")
            return
        os.startfile(caminho)
    except Exception as ex:
        try:
            messagebox.showerror("Erro", f"Falha ao abrir 3uTools:\n{ex}", parent=parent)
        except Exception:
            messagebox.showerror("Erro", f"Falha ao abrir 3uTools:\n{ex}")


# ===================== FERRAMENTAS (atalhos com ícones) =====================
def _criar_icone_placeholder(texto: str, bg: str = '#2563eb', size: int = 64):
    """Cria um ícone simples em memória (placeholder) com iniciais.
    Não depende de arquivos .png/.ico no PC do cliente.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk
        img = Image.new('RGBA', (size, size), bg)
        draw = ImageDraw.Draw(img)
        t = (texto or '').strip()[:4].upper()
        try:
            font = ImageFont.truetype('arial.ttf', int(size * 0.36))
        except Exception:
            font = ImageFont.load_default()
        try:
            bbox = draw.textbbox((0, 0), t, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = draw.textsize(t, font=font)
        x = (size - tw) // 2
        y = (size - th) // 2
        draw.text((x+1, y+1), t, font=font, fill=(0,0,0,110))
        draw.text((x, y), t, font=font, fill='white')
        return ImageTk.PhotoImage(img)
    except Exception:
        return None

def _abrir_programa_por_caminhos(nome: str, caminhos: list, parent=None):
    """Tenta abrir um programa pelo primeiro caminho existente (Windows)."""
    try:
        for p in (caminhos or []):
            p = (p or '').strip()
            if p and os.path.exists(p):
                os.startfile(p)
                return True
        msg = 'Não foi possível localizar o ' + str(nome) + ' nos caminhos configurados.\n' + '\n'.join(caminhos or [])
        try:
            messagebox.showerror('Erro', msg, parent=parent)
        except Exception:
            messagebox.showerror('Erro', msg)
        return False
    except Exception as ex:
        try:
            messagebox.showerror('Erro', 'Falha ao abrir ' + str(nome) + ':\n' + str(ex), parent=parent)
        except Exception:
            messagebox.showerror('Erro', 'Falha ao abrir ' + str(nome) + ':\n' + str(ex))
        return False

def montar_aba_ferramentas(abas: ttk.Notebook, root_win):
    """Cria a aba Ferramentas com botões em formato de ícone."""
    aba_ferramentas = ttk.Frame(abas, padding=10)
    # insere perto do início para ficar visível mesmo com muitas abas
    try:
        abas.insert(1, aba_ferramentas, text='Ferramentas')
    except Exception:
        abas.add(aba_ferramentas, text='Ferramentas')

    try:
        ttk.Label(aba_ferramentas, text='Atalhos rápidos', font=('Segoe UI', 12, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 12))
    except Exception:
        pass

    programas = [
        {'nome': '3uTools', 'iniciais': '3U', 'cor': '#2563eb', 'caminhos': [
            r'C:\\Program Files (x86)\\3uToolsV3\\x86\\3uToolsV3.exe',
            r'C:\\Program Files (x86)\\3uToolsV3\\3uTools.exe',
        ]},
        {'nome': 'Software Fix', 'iniciais': 'SF', 'cor': '#16a34a', 'caminhos': [
            r'C:\\Program Files\\Software Fix\\Software Fix.exe',
            r'C:\\Program Files\\Software Fix Software Fix.exe',
        ]},
        {'nome': 'SamFwTool', 'iniciais': 'SAM', 'cor': '#f59e0b', 'caminhos': [
            r'C:\\SamFwTool\\SamFwTool.exe',
        ]},
    ]

    cols = 4
    for c in range(cols):
        try:
            aba_ferramentas.columnconfigure(c, weight=1)
        except Exception:
            pass

    aba_ferramentas._tool_icons = []
    for idx, p in enumerate(programas):
        r = 1 + (idx // cols)
        c = idx % cols
        icon = _criar_icone_placeholder(p.get('iniciais', p.get('nome','')[:2]), p.get('cor', '#2563eb'), size=64)
        if icon is not None:
            aba_ferramentas._tool_icons.append(icon)
        btn = ttk.Button(
            aba_ferramentas,
            text=p.get('nome','Programa'),
            image=icon if icon else '',
            compound='top',
            style='Accent.TButton',
            command=lambda pp=p: _abrir_programa_por_caminhos(pp.get('nome','Programa'), pp.get('caminhos', []), parent=root_win)
        )
        btn.grid(row=r, column=c, padx=12, pady=12, sticky='nsew')
        try:
            add_tooltip(btn, 'Abrir ' + str(p.get('nome','Programa')))
        except Exception:
            pass
    return aba_ferramentas

# ===================== FIM FERRAMENTAS =====================

# ===================== TOAST (não-bloqueante) — Premium + Empilhado =====================
_ACTIVE_TOAST_ROOT = None

def _resolve_toast_base(parent=None):
    """Escolhe a melhor janela base para posicionar o toast."""
    try:
        if parent is not None and hasattr(parent, 'winfo_exists') and parent.winfo_exists():
            return parent
    except Exception:
        pass
    try:
        base = _ACTIVE_TOAST_ROOT
        if base is not None and hasattr(base, 'winfo_exists') and base.winfo_exists():
            return base
    except Exception:
        pass
    try:
        base = getattr(tk, '_default_root', None)
        if base is None or not hasattr(base, 'winfo_exists') or not base.winfo_exists():
            return None
        # Se a root estiver escondida, tenta achar algum Toplevel visível
        try:
            if str(base.state()) == 'withdrawn':
                for w in reversed(base.winfo_children()):
                    try:
                        if isinstance(w, tk.Toplevel) and w.winfo_exists() and str(w.state()) != 'withdrawn':
                            return w
                    except Exception:
                        pass
        except Exception:
            pass
        return base
    except Exception:
        return None


def _toast_level_from_title(title) -> str:
    """Heurística simples para escolher level do toast a partir do título."""
    try:
        t = str(title or '').strip().lower()
        if any(k in t for k in ('erro', 'falha')):
            return 'error'
        if any(k in t for k in ('atenção', 'atencao', 'aviso', 'warn')):
            return 'warn'
        if any(k in t for k in ('sucesso', 'ok', 'aprovado', 'upgrade', 'os', 'devolução', 'saida', 'saída', 'venda', 'cliente', 'produto', 'fechar', 'caixa')):
            return 'ok'
        return 'info'
    except Exception:
        return 'info'


def _toast_icon(level: str) -> str:
    return {'ok': '✅', 'warn': '⚠️', 'error': '❌', 'info': 'ℹ️'}.get(level or 'info', 'ℹ️')


def _get_toast_colors(level: str):
    # Paleta moderna escura por padrão
    base_bg = "#1f1f1f"
    colors = {
        'info': (base_bg, '#9cdcfe', '#2563eb'),
        'ok': (base_bg, '#c7f9cc', '#22c55e'),
        'warn': (base_bg, '#ffe8b5', '#f6c453'),
        'error': (base_bg, '#ffd1d1', '#ef4444'),
    }
    return colors.get(level, colors['info'])


def _reposition_toasts(base, anchor='top-right', margin=16, gap=10):
    """Recalcula posição de todos os toasts empilhados."""
    try:
        stack = getattr(base, '_toast_stack', []) or []
        stack = [w for w in stack if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
        base._toast_stack = stack
        if not stack:
            return
        base.update_idletasks()
        rx = base.winfo_rootx()
        ry = base.winfo_rooty()
        rw = base.winfo_width()
        if rw <= 1:
            rw = max(base.winfo_screenwidth(), 800)
        y = ry + margin
        for win in stack:
            try:
                win.update_idletasks()
                w = win.winfo_width()
                h = win.winfo_height()
                if anchor == 'top':
                    x = rx + (rw // 2) - (w // 2)
                else:
                    x = rx + rw - w - margin
                win.geometry(f'+{x}+{y}')
                y += h + gap
            except Exception:
                pass
    except Exception:
        pass


def show_toast(root: tk.Misc = None, text: str = '', level: str = 'info', duration_ms: int = 3500,
               anchor: str = 'top-right', max_stack: int = 4):
    """Mostra uma notificação tipo toast (não bloqueia a UI) — empilhado (2–4)."""
    global _ACTIVE_TOAST_ROOT
    try:
        base = _resolve_toast_base(root)
        if base is None:
            return
        _ACTIVE_TOAST_ROOT = base

        stack = getattr(base, '_toast_stack', []) or []
        stack = [w for w in stack if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
        base._toast_stack = stack

        while len(stack) >= int(max_stack):
            try:
                old = stack.pop(0)
                if old and old.winfo_exists():
                    old.destroy()
            except Exception:
                pass

        bg, fg, bar = _get_toast_colors(level)
        icon = _toast_icon(level)

        win = tk.Toplevel(base)
        win.overrideredirect(True)
        try:
            win.attributes('-topmost', True)
        except Exception:
            pass
        try:
            win.attributes('-alpha', 0.0)
        except Exception:
            pass

        shadow = tk.Frame(win, bg="#000000", bd=0, highlightthickness=0)
        shadow.pack(fill='both', expand=True)
        outer = tk.Frame(shadow, bg=bg, bd=0, highlightthickness=1, highlightbackground="#3a3a3a")
        outer.pack(padx=2, pady=2)

        tk.Frame(outer, bg=bar, width=6).pack(side='left', fill='y')
        body = tk.Frame(outer, bg=bg)
        body.pack(side='left', fill='both', expand=True)

        msg = f"{icon}  {text}".strip()
        tk.Label(body, text=msg, bg=bg, fg=fg, font=("Segoe UI", 10, "bold"), justify='left', anchor='w').pack(
            padx=12, pady=10
        )

        win.update_idletasks()
        stack.append(win)
        base._toast_stack = stack
        _reposition_toasts(base, anchor=anchor)

        # animação (fade + slide leve)
        try:
            cur_geo = win.geometry()
            mm = re.match(r"\d+x\d+\+(\-?\d+)\+(\-?\d+)", cur_geo)
            if mm:
                tx, ty = int(mm.group(1)), int(mm.group(2))
            else:
                tx, ty = win.winfo_x(), win.winfo_y()
            start_y = ty - 12
        except Exception:
            tx, ty, start_y = win.winfo_x(), win.winfo_y(), win.winfo_y() - 12

        def _anim_in(step=0):
            try:
                a = min(1.0, (step + 1) / 10)
                try:
                    win.attributes('-alpha', a)
                except Exception:
                    pass
                yy = int(start_y + (ty - start_y) * a)
                win.geometry(f'+{tx}+{yy}')
                if step < 9:
                    win.after(18, lambda: _anim_in(step + 1))
            except Exception:
                pass

        _anim_in(0)

        def _close():
            def _anim_out(step=0):
                try:
                    a = max(0.0, 1.0 - (step + 1) / 10)
                    try:
                        win.attributes('-alpha', a)
                    except Exception:
                        pass
                    if step < 9:
                        win.after(18, lambda: _anim_out(step + 1))
                    else:
                        try:
                            if win.winfo_exists():
                                win.destroy()
                        except Exception:
                            pass
                        try:
                            stack2 = getattr(base, '_toast_stack', []) or []
                            stack2 = [w for w in stack2 if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
                            base._toast_stack = stack2
                            _reposition_toasts(base, anchor=anchor)
                        except Exception:
                            pass
                except Exception:
                    pass

            _anim_out(0)

        win.after(max(900, int(duration_ms)), _close)

    except Exception:
        pass


# Monkey patch: transforma todos os messagebox.showinfo em toast (sem mudar chamadas)
_ORIG_SHOWINFO = messagebox.showinfo

def _showinfo_toast(title, message, *args, **kwargs):
    try:
        parent = kwargs.get('parent')
        level = _toast_level_from_title(title)
        show_toast(parent, message, level=level, duration_ms=3500, anchor='top-right', max_stack=4)
    except Exception:
        pass
    return 'ok'

if USE_TOAST_FOR_INFO:
    messagebox.showinfo = _showinfo_toast

# ===================== TOOLTIP (Micro UX) =====================
class ToolTip:
    """Tooltip simples para Tkinter/ttk."""
    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self.tip = None
        widget.bind('<Enter>', self._on_enter, add=True)
        widget.bind('<Leave>', self._on_leave, add=True)
        widget.bind('<ButtonPress>', self._on_leave, add=True)

    def _on_enter(self, _evt=None):
        self._schedule()

    def _on_leave(self, _evt=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _unschedule(self):
        try:
            if self._after_id:
                self.widget.after_cancel(self._after_id)
        except Exception:
            pass
        self._after_id = None

    def _show(self):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.tip = tk.Toplevel(self.widget)
            self.tip.overrideredirect(True)
            try:
                self.tip.attributes('-topmost', True)
            except Exception:
                pass
            frm = tk.Frame(self.tip, bg='#111827', highlightbackground='#374151', highlightthickness=1)
            frm.pack()
            lbl = tk.Label(frm, text=self.text, bg='#111827', fg='#f9fafb', font=('Segoe UI', 9), justify='left')
            lbl.pack(padx=10, pady=6)
            self.tip.geometry(f'+{x}+{y}')
        except Exception:
            self.tip = None

    def _hide(self):
        try:
            if self.tip and self.tip.winfo_exists():
                self.tip.destroy()
        except Exception:
            pass
        self.tip = None

def add_tooltip(widget, text: str):
    try:
        return ToolTip(widget, text)
    except Exception:
        return None


# ===================== TREEVIEW: Zebra (linhas alternadas) =====================
def configure_zebra_tags(tree: ttk.Treeview, theme_name: str = 'dark'):
    try:
        pal = THEME_DARK if theme_name == 'dark' else THEME_LIGHT
        even = pal['bg']
        odd = pal['panel'] if theme_name == 'dark' else pal['panel2']
        tree.tag_configure('even', background=even)
        tree.tag_configure('odd', background=odd)
    except Exception:
        pass

def apply_zebra(tree: ttk.Treeview):
    """Aplica zebra aos itens já inseridos (mantém outras tags)."""
    try:
        for i, iid in enumerate(tree.get_children('')):
            tags = list(tree.item(iid, 'tags') or [])
            tags = [t for t in tags if t not in ('even', 'odd')]
            tags.append('even' if i % 2 == 0 else 'odd')
            tree.item(iid, tags=tuple(tags))
    except Exception:
        pass

# ===================== SPLASH SCREEN (corrigida: primeiro plano garantido) =====================
class SplashScreen(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.geometry("520x300")
        self.configure(bg="#1e1e1e")
        # Centralização manual (Windows-safe)
        try:
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (520 // 2)
            y = (self.winfo_screenheight() // 2) - (300 // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        # Garantir visibilidade (reforços)
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(10, self.lift)
            self.after(20, lambda: self.attributes("-topmost", True))
            self.after(30, self.focus_force)
        except Exception:
            pass
        frame = tk.Frame(self, bg="#1e1e1e")
        frame.pack(expand=True, fill="both")
        logo_path = str(P('logo.png'))
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((240, 80))
                self.logo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=self.logo, bg="#1e1e1e").pack(pady=(40, 20))
            except Exception:
                tk.Label(
                    frame,
                    text="BESIM COMPANY",
                    fg="white",
                    bg="#1e1e1e",
                    font=("Segoe UI", 20, "bold"),
                ).pack(pady=(55, 20))
        else:
            tk.Label(
                frame,
                text="BESIM COMPANY",
                fg="white",
                bg="#1e1e1e",
                font=("Segoe UI", 20, "bold"),
            ).pack(pady=(55, 20))
        tk.Label(
            frame,
            text="Atualizando sistema...",
            fg="#cccccc",
            bg="#1e1e1e",
            font=("Segoe UI", 12),
        ).pack()
        self.progress = ttk.Progressbar(
            frame, orient="horizontal", length=360, mode="determinate"
        )
        self.progress.pack(pady=25)
        self.status = tk.Label(
            frame,
            text="Preparando atualização",
            fg="#9cdcfe",
            bg="#1e1e1e",
            font=("Segoe UI", 10),
        )
        self.status.pack()
    def set_progress(self, value):
        self.progress["value"] = value
        try:
            self.update_idletasks()
        except Exception:
            pass
    def set_status(self, text):
        self.status.config(text=text)
        try:
            self.update_idletasks()
        except Exception:
            pass


def show_goodbye_screen(master, message="Até Logo,\nBom descanso", duration_ms=1500):
    """Mostra uma tela rápida de despedida com logo (se existir) e mensagem."""
    try:
        win = tk.Toplevel(master)
        win.overrideredirect(True)
        win.configure(bg="#1e1e1e")

        w, h = 520, 260
        try:
            win.update_idletasks()
            x = (win.winfo_screenwidth() // 2) - (w // 2)
            y = (win.winfo_screenheight() // 2) - (h // 2)
            win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            win.geometry(f"{w}x{h}")

        try:
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
        except Exception:
            pass

        frame = tk.Frame(win, bg="#1e1e1e")
        frame.pack(expand=True, fill="both")

        logo_path = str(P('logo.png'))
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((240, 80))
                win._goodbye_logo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=win._goodbye_logo, bg="#1e1e1e").pack(pady=(35, 18))
            except Exception:
                tk.Label(
                    frame,
                    text="BESIM COMPANY",
                    fg="white",
                    bg="#1e1e1e",
                    font=("Segoe UI", 20, "bold"),
                ).pack(pady=(55, 18))
        else:
            tk.Label(
                frame,
                text="BESIM COMPANY",
                fg="white",
                bg="#1e1e1e",
                font=("Segoe UI", 20, "bold"),
            ).pack(pady=(55, 18))

        tk.Label(
            frame,
            text=message,
            fg="#9cdcfe",
            bg="#1e1e1e",
            font=("Segoe UI", 14, "bold"),
            justify="center",
            anchor="center",
        ).pack(pady=(0, 10))

        win.after(duration_ms, win.destroy)
        return win
    except Exception:
        return None

# ===================== RELEASE NOTES (Novidades / Melhorias) =====================
# Mostra uma tela com a logo ao fundo e as melhorias da versão.
# Fonte das melhorias: arquivo RELEASE_NOTES.txt (vem junto no update via GitHub).
RELEASE_NOTES_FILE = "RELEASE_NOTES.txt"

# Controle em memória para não reabrir várias vezes na mesma execução
_RELEASE_NOTES_SESSION_SUPPRESS = set()  # versões suprimidas nesta sessão

def _runtime_app_dir() -> _Path:
    """Diretório real do app (pasta do .py ou do .exe)."""
    try:
        if getattr(sys, 'frozen', False):
            return _Path(sys.executable).resolve().parent
    except Exception:
        pass
    try:
        return _Path(__file__).resolve().parent
    except Exception:
        return _Path(os.getcwd()).resolve()


def _load_release_notes_text(max_chars: int = 14000) -> str:
    """Carrega o texto de RELEASE_NOTES.txt, tentando caminhos comuns."""
    candidates = []
    try:
        candidates.append(_runtime_app_dir() / RELEASE_NOTES_FILE)
    except Exception:
        pass
    try:
        candidates.append(_Path(os.getcwd()).resolve() / RELEASE_NOTES_FILE)
    except Exception:
        pass
    # fallback: diretório base (PyInstaller _MEIPASS) — pode não conter o arquivo após update
    try:
        candidates.append(P(RELEASE_NOTES_FILE))
    except Exception:
        pass

    for p in candidates:
        try:
            p = str(p)
            if os.path.exists(p) and os.path.isfile(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return (f.read() or '').strip()[:max_chars]
        except Exception:
            continue

    return "Nenhuma melhoria registrada para esta versão."


def _extract_notes_for_version(notes_text: str, version: str) -> str:
    """Se o arquivo tiver várias versões, tenta extrair só o bloco da versão atual."""
    try:
        v = str(version or '').strip()
        if not v:
            return notes_text
        # Cabeçalhos aceitos: "VERSÃO 4.8" / "VERSAO 4.8" / "VERSION 4.8"
        header_re = re.compile(r'^(VERS[AÃ]O|VERSION)\s+' + re.escape(v) + r'\s*$', re.IGNORECASE | re.MULTILINE)
        m = header_re.search(notes_text or '')
        if not m:
            return notes_text
        start = m.end()
        next_re = re.compile(r'^(VERS[AÃ]O|VERSION)\s+\d+(?:\.\d+)*\s*$', re.IGNORECASE | re.MULTILINE)
        m2 = next_re.search((notes_text or '')[start:])
        end = start + (m2.start() if m2 else len((notes_text or '')[start:]))
        block = (notes_text or '')[m.start():end].strip()
        return block if block else notes_text
    except Exception:
        return notes_text
class ReleaseNotesWindow(tk.Toplevel):
    """Janela de novidades com logo ao fundo (marca d'água)."""

    def __init__(self, master, version: str, notes_text: str, title_prefix: str = "Atualização"):
        super().__init__(master)
        self._choice = None  # 'continue' | 'later'
        self.version = str(version or '').strip()

        self.title(f"{title_prefix} • Novidades v{self.version}")
        self.geometry("820x560")
        self.minsize(720, 500)
        self.configure(bg="#0f1115")

        try:
            self.transient(master)
            self.grab_set()
        except Exception:
            pass

        # Centraliza
        try:
            self.update_idletasks()
            w, h = 820, 560
            x = (self.winfo_screenwidth() // 2) - (w // 2)
            y = (self.winfo_screenheight() // 2) - (h // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

        # Canvas para fundo
        self.canvas = tk.Canvas(self, bg="#0f1115", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Prepara logo marca d'água
        self._bg_img = None
        logo_path = str(P('Logo_att.png'))
        if not os.path.exists(logo_path):
            logo_path = str(P('logo.png'))
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).convert("RGBA")
                img = img.resize((560, 190))
                # baixa opacidade
                alpha = img.split()[-1]
                alpha = alpha.point(lambda p: int(p * 0.10))  # 10% opacidade
                img.putalpha(alpha)
                self._bg_img = ImageTk.PhotoImage(img)
            except Exception:
                self._bg_img = None

        # Frame do conteúdo
        self.content = tk.Frame(self.canvas, bg="#0f1115")
        self._content_id = self.canvas.create_window(0, 0, anchor="nw", window=self.content)

        # Header
        # Logo da atualização (preferência: Logo_att.png)
        self._header_logo = None
        try:
            _hdr_path = str(P('Logo_att.png'))
            if not os.path.exists(_hdr_path):
                _hdr_path = str(P('logo.png'))
            if os.path.exists(_hdr_path):
                _img = Image.open(_hdr_path).convert('RGBA')
                _img = _img.resize((240, 80))
                self._header_logo = ImageTk.PhotoImage(_img)
                tk.Label(self.content, image=self._header_logo, bg="#0f1115").pack(anchor="w", padx=18, pady=(18, 0))
        except Exception:
            self._header_logo = None
        tk.Label(
            self.content,
            text=f"✨ Novidades / Melhorias — v{self.version}",
            bg="#0f1115",
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 6))

        tk.Label(
            self.content,
            text="Veja o que mudou nesta atualização.",
            bg="#0f1115",
            fg="#b4b4b4",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=(0, 12))

        # Caixa de texto com scroll
        box = tk.Frame(self.content, bg="#0f1115")
        box.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")

        self.txt = tk.Text(
            box,
            wrap="word",
            yscrollcommand=sb.set,
            bg="#151824",
            fg="#e8e8e8",
            insertbackground="#e8e8e8",
            relief="flat",
            font=("Consolas", 11),
            padx=12,
            pady=10,
        )
        self.txt.pack(side="left", fill="both", expand=True)
        sb.config(command=self.txt.yview)

        self.txt.insert("1.0", notes_text or "")
        self.txt.config(state="disabled")

        # Botões
        btns = tk.Frame(self.content, bg="#0f1115")
        btns.pack(fill="x", padx=18, pady=(0, 18))

        ttk.Button(btns, text="Ler depois", style="Secondary.TButton", command=self._later).pack(side="left")
        ttk.Button(btns, text="Continuar", style="Success.TButton", command=self._continue).pack(side="right")

        # Teclas
        self.bind("<Return>", lambda e: self._continue())
        self.bind("<Escape>", lambda e: self._later())
        # Se o usuário fechar no X, considera como 'Continuar' para não reabrir automaticamente
        self.protocol("WM_DELETE_WINDOW", self._continue)

        # Resize
        self.bind("<Configure>", self._on_resize)
        self.after(50, self._draw_background)

    def _draw_background(self):
        try:
            self.canvas.delete("bg")
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())

            if self._bg_img:
                self.canvas.create_image(cw // 2, ch // 2, image=self._bg_img, tags="bg")

            self.canvas.coords(self._content_id, 0, 0)
            self.canvas.itemconfig(self._content_id, width=cw, height=ch)
        except Exception:
            pass

    def _on_resize(self, _evt=None):
        self._draw_background()

    def _continue(self):
        self._choice = 'continue'
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _later(self):
        self._choice = 'later'
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def show_release_notes(master, force: bool = False):
    """Abre a tela de novidades. Se force=False, respeita controles de exibição automática."""
    try:
        version = get_local_version()
        notes = _load_release_notes_text()
        notes = _extract_notes_for_version(notes, version)

        # Exibição automática: não mostrar se já mostrado ou adiado nesta versão
        if not force:
            if version in _RELEASE_NOTES_SESSION_SUPPRESS:
                return
            try:
                last_shown = _meta_get('release_notes_last_shown', '')
                deferred = _meta_get('release_notes_deferred', '')
                if str(last_shown) == str(version) or str(deferred) == str(version):
                    return
            except Exception:
                pass

        win = ReleaseNotesWindow(master, version, notes)
        try:
            master.wait_window(win)
        except Exception:
            pass
        choice = getattr(win, '_choice', None)
        if choice == 'continue':
            try:
                _meta_set('release_notes_last_shown', str(version))
            except Exception:
                pass
        elif choice == 'later':
            # "Ler depois": não mostra automaticamente nesta versão, mas fica disponível no menu.
            try:
                _meta_set('release_notes_deferred', str(version))
            except Exception:
                pass
            # Mesmo em 'Ler depois', marcamos como exibido para não reaparecer automaticamente
            try:
                _meta_set('release_notes_last_shown', str(version))
            except Exception:
                pass
        else:
            # Fechou sem escolher (ex.: clicou no X) — marque como exibido
            try:
                _meta_set('release_notes_last_shown', str(version))
            except Exception:
                pass

        # Em qualquer caso, suprime nesta sessão para não ficar mostrando toda hora
        _RELEASE_NOTES_SESSION_SUPPRESS.add(str(version))

    except Exception as ex:
        try:
            logging.error(f"Falha ao abrir novidades: {ex}", exc_info=True)
        except Exception:
            pass


def maybe_show_release_notes(master):
    """Mostra automaticamente as novidades após abrir o sistema (uma vez por versão, com opção 'ler depois')."""
    try:
        show_release_notes(master, force=False)
    except Exception:
        pass

# ===================== FIM RELEASE NOTES =====================

# ===================== UPDATE (após login, corrigido: sem loop) =====================

# >>> Diálogo modal de alteração de senha e atalhos de tela cheia
class ChangePasswordDialog(tk.Toplevel):
    def __init__(self, master, username: str, must_change: bool = False):
        super().__init__(master)
        self.title("Alterar Senha")
        self.resizable(False, False)
        self.username = username
        self.must_change = must_change
        self.result = False
        self.grab_set()
        self.transient(master)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        msg = "Sua senha expirou. Defina uma nova senha." if must_change else "Defina a nova senha."
        ttk.Label(frm, text=msg).pack(anchor="w", pady=(0,8))
        ttk.Label(frm, text="Nova senha").pack(anchor="w")
        self.ent_new = ttk.Entry(frm, show="*")
        self.ent_new.pack(fill="x", pady=4)
        ttk.Label(frm, text="Confirmar nova senha").pack(anchor="w")
        self.ent_conf = ttk.Entry(frm, show="*")
        self.ent_conf.pack(fill="x", pady=4)
        ttk.Label(frm, text="Regras: mínimo 8 caracteres, com 1 letra MAIÚSCULA e 1 número.\nNão é permitido reutilizar as últimas 3 senhas.").pack(anchor="w", pady=(6,2))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="right", padx=6)
        ttk.Button(btns, text="Salvar", style="Success.TButton", command=self._save).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self._save())
        if must_change:
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        else:
            self.protocol("WM_DELETE_WINDOW", self._cancel)
    def _save(self):
        new = (self.ent_new.get() or "").strip()
        conf = (self.ent_conf.get() or "").strip()
        ok, msg = validate_password_policy(new)
        if not ok:
            messagebox.showwarning("Atenção", msg)
            return
        if new != conf:
            messagebox.showerror("Erro", "As senhas digitadas não conferem.")
            return
        try:
            set_new_password(self.username, new)
            messagebox.showinfo("OK", "Senha alterada com sucesso!")
            self.result = True
            self.destroy()
        except ValueError as ve:
            messagebox.showerror("Erro", str(ve))
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao alterar a senha\n{ex}")
    def _cancel(self):
        self.result = False
        self.destroy()

# Helper para alternar tela cheia (F11) e sair (Esc)

# ====== Diálogo de Administração de Usuários (apenas admin logado) ======
class UserAdminDialog(tk.Toplevel):
    def __init__(self, master, current_admin: str):
        super().__init__(master)
        self.title("Gerenciar Usuários")
        self.resizable(False, False)
        self.current_admin = current_admin
        try:
            self.transient(master)
            self.grab_set()
        except Exception:
            pass
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Novo usuário").grid(row=0, column=0, sticky="w")
        self.ent_user = ttk.Entry(frm, width=28)
        self.ent_user.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(frm, text="Senha inicial").grid(row=1, column=0, sticky="w")
        self.ent_pass = ttk.Entry(frm, width=28, show="*")
        self.ent_pass.grid(row=1, column=1, padx=6, pady=4)
        self.var_admin = tk.IntVar(value=0)
        ttk.Checkbutton(frm, text="Conceder perfil de administrador", variable=self.var_admin).grid(row=2, column=1, sticky="w", pady=(2,8))
        btns = ttk.Frame(frm); btns.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(btns, text="Criar usuário", style="Success.TButton", command=self._criar).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self._criar())
    def _criar(self):
        novo = (self.ent_user.get() or "").strip()
        pw = (self.ent_pass.get() or "").strip()
        want_admin = 1 if self.var_admin.get() == 1 else 0
        if not novo or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha.")
            return
        ok, msg = validate_password_policy(pw)
        if not ok:
            messagebox.showwarning("Atenção", msg)
            return
        try:
            create_user_admin(self.current_admin, novo, pw, want_admin)
            messagebox.showinfo("OK", "Usuário criado com sucesso!")
            self.destroy()
        except PermissionError as pe:
            messagebox.showerror("Permissão", str(pe))
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Usuário já existe.")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao criar usuário\n{ex}")

def _bind_fullscreen_shortcuts(win: tk.Misc):
    if not hasattr(win, "_is_fullscreen"):
        win._is_fullscreen = False
    def _toggle_fullscreen(evt=None):
        try:
            win._is_fullscreen = not getattr(win, "_is_fullscreen", False)
            win.attributes("-fullscreen", win._is_fullscreen)
        except Exception:
            try:
                win.state("zoomed" if win._is_fullscreen else "normal")
            except Exception:
                pass
    def _exit_fullscreen(evt=None):
        try:
            win._is_fullscreen = False
            win.attributes("-fullscreen", False)
        except Exception:
            try:
                win.state("normal")
            except Exception:
                pass
    win.bind("<F11>", _toggle_fullscreen)
    win.bind("<Escape>", _exit_fullscreen)

def get_local_version() -> str:
    """Lê a versão local a partir do arquivo VERSION, se existir; senão usa APP_VERSION."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return APP_VERSION
def obter_versao_remota() -> str:
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{VERSION_FILE}"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=10) as r:
        return r.read().decode("utf-8").strip()
def baixar_e_extrair(splash: SplashScreen, remote_version: str):
    zip_url = f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip"
    temp_dir = tempfile.mkdtemp(prefix="update_")
    zip_path = os.path.join(temp_dir, "repo.zip")
    try:
        splash.set_status("Baixando atualização...")
        splash.set_progress(5)
        with urllib.request.urlopen(zip_url, context=_SSL_CTX) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as out:
                while True:
                    data = response.read(8192)
                    if not data:
                        break
                    out.write(data)
                    downloaded += len(data)
                    if total:
                        splash.set_progress(5 + int((downloaded / total) * 60))
        splash.set_status("Extraindo arquivos...")
        splash.set_progress(70)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(temp_dir)
        splash.set_status("Copiando nova versão...")
        splash.set_progress(85)
        # Seleciona a pasta extraída (ignora arquivos como repo.zip)
        dirs_extracted = [e for e in os.scandir(temp_dir) if e.is_dir()]
        if not dirs_extracted:
            raise RuntimeError("Nenhum diretório extraído encontrado no update.")
        prefer = None
        for e in dirs_extracted:
            if e.name.startswith(f"{REPO}-"):
                prefer = e.path
                break
        src_dir = prefer or dirs_extracted[0].path
        for root_dir, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            rel = os.path.relpath(root_dir, src_dir)
            dest = os.path.join(os.getcwd(), rel)
            os.makedirs(dest, exist_ok=True)
            for f in files:
                if f not in IGNORE_FILES:
                    shutil.copy2(os.path.join(root_dir, f), os.path.join(dest, f))
        # Garante que a versão local fique igual à remota
        try:
            with open(VERSION_FILE, "w", encoding="utf-8") as vf:
                vf.write(remote_version)
        except Exception:
            pass
        splash.set_status("Finalizando...")
        splash.set_progress(100)
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
def check_and_update_after_login(master: tk.Misc) -> bool:
    """Retorna True se atualizar (e reiniciar), False caso contrário."""
    if DISABLE_AUTO_UPDATE:
        return False
    try:
        remote_version = obter_versao_remota()
        local_version = get_local_version()
        if remote_version == local_version:
            return False # Já está na última versão
    except Exception as e:
        logging.error(f"Falha ao checar versão remota: {e}")
        return False
    try:
        # Esconde a janela principal ANTES da splash
        try:
            master.withdraw()
            master.update_idletasks()
            master.update()
        except Exception:
            pass
        splash = SplashScreen(master)
        try:
            splash.update()
        except Exception:
            pass
        baixar_e_extrair(splash, remote_version)
        splash.set_status("Atualização concluída. Reiniciando...")
        # Reforçar visibilidade antes do reinício
        try:
            splash.lift()
            splash.focus_force()
            splash.update()
        except Exception:
            pass
        master.after(
            1200, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)
        )
        try:
            splash.update()
        except Exception:
            pass
        return True
    except Exception as e:
        logging.error(f"Falha na atualização automática: {e}", exc_info=True)
        try:
            messagebox.showerror("Erro", "Falha na atualização automática")
        except Exception:
            pass
        return False
# ================= FUNÇÕES PDF =================
def gerar_cupom(cliente, produto, qtd, pagamento, total, cpf=None):
    agora = datetime.datetime.now()
    pasta_cupons = os.path.join(os.getcwd(), "cupons")
    os.makedirs(pasta_cupons, exist_ok=True)
    nome_arquivo = os.path.join(
        pasta_cupons, f"cupom_{agora.strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = str(P('logo.png'))
    if os.path.exists(logo_path):
        try:
            c.drawImage(
                ImageReader(logo_path),
                40,
                730,
                width=150,
                height=50,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY",
        "----------------------------------------------"
        "----------------------------------------------",
        f"Cliente: {cliente}",
        f"Produto: {produto}",
        f"Quantidade: {qtd}",
        f"Forma de Pagamento: {pagamento}",
        f"Total: R$ {total:.2f}",
        (f"Pontos acumulados: {get_pontos_cliente(cpf)} pts" if cpf else ""),
        f"Data: {agora.strftime('%d/%m/%Y')}",
        f"Hora: {agora.strftime('%H:%M:%S')}",
        "----------------------------------------------"
        "----------------------------------------------",
        "Obrigado pela preferência!",
    ]
    for l in linhas:
        if l:
            t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        backup_pdf(nome_arquivo, "cupons")
    except Exception:
        pass
    try:
        open_in_default_app(nome_arquivo)
    except Exception:
        pass
    bring_app_to_front()
    return nome_arquivo

def gerar_os_pdf(os_num, nome, cpf, telefone, descricao, valor):
    agora = datetime.datetime.now()
    pasta_os = os.path.join(os.getcwd(), "OS")
    os.makedirs(pasta_os, exist_ok=True)
    nome_arquivo = os.path.join(pasta_os, f"OS_{os_num}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = str(P('logo.png'))
    if os.path.exists(logo_path):
        try:
            c.drawImage(
                ImageReader(logo_path),
                40,
                730,
                width=150,
                height=50,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY - ORDEM DE SERVIÇO",
        "----------------------------------------------"
        "----------------------------------------------",
        f"OS Nº: {os_num}",
        f"Cliente: {nome}",
        f"CPF: {cpf}",
        f"Telefone: {telefone}",
        f"Descrição: {descricao}",
        f"Valor: R$ {valor:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        "----------------------------------------------"
        "----------------------------------------------",
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        backup_pdf(nome_arquivo, "OS")
    except Exception:
        pass
    try:
        open_in_default_app(nome_arquivo)
    except Exception:
        pass
    bring_app_to_front()
    return nome_arquivo
# ================= RELATÓRIO VENDAS (PDF) =================
def gerar_relatorio_vendas_dia_pdf(data_str: str = None, abrir_pdf: bool = True):
    hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    data_alvo = data_str or hoje
    pasta_rel = os.path.join(os.getcwd(), "relatorios")
    os.makedirs(pasta_rel, exist_ok=True)
    nome_arquivo = os.path.join(
        pasta_rel, f"relatorio_vendas_{data_alvo.replace('/', '-')}" + ".pdf"
    )
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path_local = str(P('logo.png'))
    if os.path.exists(logo_path_local):
        try:
            c.drawImage(
                ImageReader(logo_path_local),
                40,
                780,
                width=140,
                height=40,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
    c.setFont("Helvetica", 11)
    c.drawString(40, 742, "-" * 110)
    y = 720
    # Vendas do dia
    cursor.execute(
        "SELECT hora, cliente, produto, quantidade, pagamento, total FROM vendas WHERE data=? ORDER BY hora DESC",
        (data_alvo,),
    )
    linhas = cursor.fetchall()
    totais_pg = {"PIX": 0.0, "Cartão": 0.0, "Dinheiro": 0.0, "OUTROS": 0.0}
    total_dia = 0.0
    c.setFont("Helvetica", 10)
    if not linhas:
        c.drawString(40, y, "Nenhuma venda registrada neste dia.")
        y -= 18
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Hora")
        c.drawString(90, y, "Cliente")
        c.drawString(250, y, "Produto")
        c.drawString(420, y, "Qtd")
        c.drawString(455, y, "Pagto")
        c.drawString(520, y, "Total")
        y -= 16
        c.setFont("Helvetica", 10)
        for hora, cliente, produto, qtd, pagamento, total in linhas:
            total_dia += total or 0.0
            if pagamento in totais_pg:
                totais_pg[pagamento] += total or 0.0
            else:
                totais_pg["OUTROS"] += total or 0.0
            c.drawString(40, y, str(hora))
            c.drawString(90, y, str(cliente)[:24])
            c.drawString(250, y, str(produto)[:24])
            c.drawString(420, y, str(qtd))
            c.drawString(455, y, str(pagamento))
            c.drawRightString(590, y, f"R$ {float(total):.2f}")
            y -= 16
            if y < 60:
                c.showPage()
                if os.path.exists(logo_path_local):
                    try:
                        c.drawImage(
                            ImageReader(logo_path_local),
                            40,
                            780,
                            width=140,
                            height=40,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
                c.setFont("Helvetica", 11)
                c.drawString(40, 742, "-" * 110)
                y = 720
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, "Hora")
                c.drawString(90, y, "Cliente")
                c.drawString(250, y, "Produto")
                c.drawString(420, y, "Qtd")
                c.drawString(455, y, "Pagto")
                c.drawString(520, y, "Total")
                y -= 16
                c.setFont("Helvetica", 10)
    # Totais por forma de pagamento
    y -= 8
    c.setFont("Helvetica", 11)
    c.drawString(40, y, "-" * 110)
    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Totais por Forma de Pagamento:")
    y -= 18
    c.setFont("Helvetica", 11)
    for k in ["PIX", "Cartão", "Dinheiro", "OUTROS"]:
        c.drawString(40, y, f"{k}: R$ {totais_pg[k]:.2f}")
        y -= 18
    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total de vendas do dia: R$ {total_dia:.2f}")
    y -= 24

    # ----------------- FECHAMENTO EXPLICADO: Entradas por origem -----------------
    # Este bloco detalha as entradas do dia por categoria e faz uma conferência rápida.
    try:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Entradas no Caixa (por origem)")
        y -= 18
        c.setFont("Helvetica", 10)

        def _classificar_motivo_rel(vlr, mot):
            mtxt = (mot or '').strip()
            low = mtxt.lower()
            if not mtxt:
                return 'Outros'
            if low.startswith('venda'):
                return 'Venda'
            if low.startswith('upgrade'):
                return 'Upgrade'
            if low.startswith('os') or 'manuten' in low:
                return 'Manutenção'
            if 'devedor' in low:
                return 'Devedor'
            if low.startswith('estorno'):
                return 'Estorno'
            if float(vlr or 0) < 0:
                return 'Saída'
            return 'Outros'

        # Lançamentos do CAIXA do dia
        cursor.execute("SELECT COALESCE(valor,0), COALESCE(motivo,'') FROM caixa WHERE data=?", (data_alvo,))
        rows_cx = cursor.fetchall() or []

        soma_pos = { 'Venda': 0.0, 'Manutenção': 0.0, 'Devedor': 0.0, 'Upgrade': 0.0, 'Outros': 0.0, 'Estorno': 0.0 }
        entradas_cx = 0.0
        saidas_cx_abs = 0.0
        for vv, mot in rows_cx:
            v = float(vv or 0.0)
            if v > 0:
                entradas_cx += v
                cat = _classificar_motivo_rel(v, mot)
                soma_pos[cat] = float(soma_pos.get(cat, 0.0) + v)
            elif v < 0:
                saidas_cx_abs += abs(v)

        # Fontes oficiais (para explicar melhor)
        cursor.execute("SELECT COALESCE(SUM(total),0) FROM vendas WHERE data=?", (data_alvo,))
        vendas_oficial = float((cursor.fetchone() or [0])[0] or 0.0)

        cursor.execute("SELECT COALESCE(SUM(valor),0), COUNT(1) FROM manutencao WHERE COALESCE(aprovado,0)=1 AND data=?", (data_alvo,))
        os_sum, os_cnt = cursor.fetchone() or (0, 0)
        os_sum = float(os_sum or 0.0)
        os_cnt = int(os_cnt or 0)

        cursor.execute("SELECT COALESCE(SUM(valor),0), COUNT(1) FROM devedores WHERE COALESCE(pago,0)=1 AND data_pagamento=?", (data_alvo,))
        dev_sum, dev_cnt = cursor.fetchone() or (0, 0)
        dev_sum = float(dev_sum or 0.0)
        dev_cnt = int(dev_cnt or 0)

        c.drawString(40, y, f"1) Vendas do dia (tabela VENDAS): R$ {vendas_oficial:.2f}")
        y -= 14
        c.drawString(40, y, f"2) OS aprovadas (qtd {os_cnt}): R$ {os_sum:.2f}")
        y -= 14
        c.drawString(40, y, f"3) Devedores pagos (qtd {dev_cnt}): R$ {dev_sum:.2f}")
        y -= 14
        c.drawString(40, y, f"4) Upgrade (tabela CAIXA): R$ {float(soma_pos.get('Upgrade',0.0)):.2f}")
        y -= 14
        c.drawString(40, y, f"5) Outras entradas (tabela CAIXA): R$ {float(soma_pos.get('Outros',0.0)):.2f}")
        y -= 16

        entradas_explicadas = float(vendas_oficial + os_sum + dev_sum + float(soma_pos.get('Upgrade',0.0)) + float(soma_pos.get('Outros',0.0)))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, f"TOTAL DE ENTRADAS (explicado): R$ {entradas_explicadas:.2f}")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(40, y, "Conferência rápida com lançamentos do CAIXA:")
        y -= 14
        c.drawString(60, y, f"• Entradas no CAIXA (valor > 0): R$ {entradas_cx:.2f}")
        y -= 14
        c.drawString(60, y, f"• Saídas no CAIXA (valor < 0): R$ {saidas_cx_abs:.2f}")
        y -= 14
        c.drawString(60, y, f"• Saldo do CAIXA (Entradas - Saídas): R$ {(entradas_cx - saidas_cx_abs):.2f}")
        y -= 18
        c.drawString(40, y, "Obs.: o \"Total líquido do caixa\" ao final do relatório considera os lançamentos do CAIXA do dia.")
        y -= 18

        if y < 120:
            c.showPage()
            if os.path.exists(logo_path_local):
                try:
                    c.drawImage(ImageReader(logo_path_local), 40, 780, width=140, height=40, preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, 760, f"Relatório de Vendas - {data_alvo} (continuação)")
            c.setFont("Helvetica", 11)
            c.drawString(40, 742, "-" * 110)
            y = 720
    except Exception:
        pass

    # -----------------------------------------------------------------------------

    # Saídas do dia
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Saídas do dia")
    y -= 18
    c.setFont("Helvetica", 11)
    # >>> Consulta compatível com colunas hora/motivo criadas na migração
    cursor.execute(
        "SELECT hora, motivo, valor FROM caixa WHERE data=? AND valor<0 ORDER BY hora DESC",
        (data_alvo,),
    )
    saidas = cursor.fetchall()
    total_saidas = 0.0
    if not saidas:
        c.drawString(40, y, "Nenhuma saída registrada neste dia.")
        y -= 18
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Hora")
        c.drawString(100, y, "Motivo")
        c.drawString(520, y, "Valor")
        y -= 16
        c.setFont("Helvetica", 10)
        for hora_s, motivo_s, valor_s in saidas:
            if y < 60:
                c.showPage()
                if os.path.exists(logo_path_local):
                    try:
                        c.drawImage(
                            ImageReader(logo_path_local),
                            40,
                            780,
                            width=140,
                            height=40,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
                c.setFont("Helvetica", 11)
                c.drawString(40, 742, "-" * 110)
                y = 720
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Saídas do dia (continuação)")
                y -= 18
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, "Hora")
                c.drawString(100, y, "Motivo")
                c.drawString(520, y, "Valor")
                y -= 16
                c.setFont("Helvetica", 10)
            hora_txt = str(hora_s or "--:--:--")
            motivo_txt = str(motivo_s or "(sem motivo)")[:48]
            c.drawString(40, y, hora_txt)
            c.drawString(100, y, motivo_txt)
            c.drawRightString(590, y, f"R$ {abs(float(valor_s)):.2f}")
            total_saidas += abs(float(valor_s))
            y -= 16
    # Resumo do caixa
    c.setFont("Helvetica", 11)
    c.drawString(40, y, "-" * 110)
    y -= 18
    cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (data_alvo,))
    total_liquido = cursor.fetchone()[0] or 0.0
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total de saídas: R$ {total_saidas:.2f}")
    y -= 18
    c.drawString(40, y, f"Total líquido do caixa: R$ {total_liquido:.2f}")
    c.save()
    try:
        backup_pdf(nome_arquivo, "relatorios")
    except Exception:
        pass
    try:
        open_in_default_app(nome_arquivo)
    except Exception:
        pass
    bring_app_to_front()
    return nome_arquivo


# ================= RELATÓRIO VENDAS MENSAL (PDF + GRÁFICO + RANKING) =================
def gerar_relatorio_vendas_mes_pdf(ano: int = None, mes: int = None, top_n: int = 10, abrir_pdf: bool = True):
    """Gera um relatório mensal com:

    - Gráfico (barras + linha) do total de vendas por dia no mês
    - Resumo do mês (total e por forma de pagamento)
    - Ranking TOP N de produtos por valor vendido

    Observação:
    - Usa a tabela 'vendas' (histórico), pois o fechamento diário limpa apenas a tabela 'caixa'.
    - Se matplotlib não estiver disponível, o PDF é gerado sem o gráfico.

    Retorna o caminho do PDF.
    """
    hoje_dt = datetime.date.today()
    ano = int(ano or hoje_dt.year)
    mes = int(mes or hoje_dt.month)
    top_n = int(top_n or 10)

    pasta_rel = os.path.join(os.getcwd(), "relatorios")
    os.makedirs(pasta_rel, exist_ok=True)
    nome_arquivo = os.path.join(pasta_rel, f"relatorio_vendas_mensal_{ano:04d}-{mes:02d}.pdf")

    mm = f"{mes:02d}"
    yyyy = f"{ano:04d}"

    # Totais por dia / pagamentos / ranking (robusto para datas com/sem zero à esquerda)
    total_por_data = {}
    totais_pg = {"PIX": 0.0, "Cartão": 0.0, "Dinheiro": 0.0, "OUTROS": 0.0}
    prod_stats = {}  # {produto: {qtd:int, valor:float}}

    # Vendas do ano (filtra por mês/ano em Python para aceitar formatos antigos)
    cursor.execute(
        "SELECT data, COALESCE(total,0), pagamento, produto, COALESCE(quantidade,0) FROM vendas WHERE data LIKE ?",
        (f"%/{yyyy}",),
    )
    for data_raw, tot_raw, pg_raw, prod_raw, qtd_raw in (cursor.fetchall() or []):
        dmY = _parse_br_date_flex(data_raw)
        if not dmY:
            continue
        d, mo, y = dmY
        if y != ano or mo != mes:
            continue
        key = f"{d:02d}/{mo:02d}/{y:04d}"
        v = float(tot_raw or 0.0)
        total_por_data[key] = float(total_por_data.get(key, 0.0) + v)

        # pagamento
        pg = str(pg_raw or "").strip()
        if pg.startswith("Upgrade"):
            totais_pg["OUTROS"] += v
        elif pg in totais_pg:
            totais_pg[pg] += v
        else:
            totais_pg["OUTROS"] += v

        # produto
        prod = str(prod_raw or "(sem produto)").strip() or "(sem produto)"
        st = prod_stats.get(prod) or {"qtd": 0, "valor": 0.0}
        try:
            st["qtd"] += int(qtd_raw or 0)
        except Exception:
            pass
        st["valor"] += v
        prod_stats[prod] = st

    # Série completa do mês (dias sem venda = 0)
    last_day = calendar.monthrange(ano, mes)[1]
    dias = list(range(1, last_day + 1))
    datas = [f"{d:02d}/{mes:02d}/{ano:04d}" for d in dias]
    valores = [float(total_por_data.get(dt, 0.0) or 0.0) for dt in datas]
    total_mes = float(sum(valores))

    # Totais de manutenções (OS) no mês (robusto)
    valor_total_os = 0.0
    valor_total_os_aprov = 0.0
    qtd_os = 0
    qtd_os_aprov = 0
    cursor.execute(
        "SELECT data, COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao WHERE data LIKE ?",
        (f"%/{yyyy}",),
    )
    for data_raw, val_raw, aprov_raw in (cursor.fetchall() or []):
        dmY = _parse_br_date_flex(data_raw)
        if not dmY:
            continue
        d, mo, y = dmY
        if y != ano or mo != mes:
            continue
        try:
            val = float(val_raw or 0.0)
        except Exception:
            val = 0.0
        valor_total_os += val
        qtd_os += 1
        if int(aprov_raw or 0) == 1:
            valor_total_os_aprov += val
            qtd_os_aprov += 1

    # Total geral do mês: vendas + manutenções aprovadas
    total_geral_mes = float(total_mes + valor_total_os_aprov)

    # Ranking TOP N por valor
    ranking = sorted(
        [(p, st.get('qtd', 0), st.get('valor', 0.0)) for p, st in (prod_stats.items())],
        key=lambda x: float(x[2] or 0.0),
        reverse=True,
    )[:top_n]

# Gera gráfico (barras + linha)
    chart_path = os.path.join(pasta_rel, f"_chart_vendas_{ano:04d}{mes:02d}.png")
    chart_ok = False
    try:
        if _HAS_MPL and plt is not None:
            xticks = dias if last_day <= 15 else list(range(1, last_day + 1, 2))
            fig = plt.figure(figsize=(10.2, 3.8), dpi=170)
            ax = fig.add_subplot(111)
            ax.bar(dias, valores, color="#bfdbfe", edgecolor="#93c5fd", label="Barras (R$)")
            ax.plot(dias, valores, marker="o", linewidth=2.2, color="#2563eb", label="Linha (R$)")
            ax.set_title(f"Vendas por dia — {mes:02d}/{ano:04d}")
            ax.set_xlabel("Dia do mês")
            ax.set_ylabel("Total (R$)")
            ax.set_xticks(xticks)
            ax.grid(True, axis='y', alpha=0.25)
            ax.legend(loc="upper left")
            fig.tight_layout()
            fig.savefig(chart_path)
            plt.close(fig)
            chart_ok = os.path.exists(chart_path)
    except Exception:
        chart_ok = False

    # Monta PDF
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path_local = str(P('logo.png'))
    if os.path.exists(logo_path_local):
        try:
            c.drawImage(ImageReader(logo_path_local), 40, 770, width=140, height= 35,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, 745, f"Relatório Mensal de Vendas — {mes:02d}/{ano:04d}")
    c.setFont("Helvetica", 11)
    c.drawString(40, 728, "-" * 110)
    # Resumo
    y = 705
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total do mês (vendas): R$ {total_mes:.2f}")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(
        40, y,
        f"Manutenções (OS): R$ {valor_total_os:.2f}  |  Aprovadas: R$ {valor_total_os_aprov:.2f}  |  OS: {qtd_os} (Aprov.: {qtd_os_aprov})"
    )
    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"TOTAL GERAL (vendas + manutenções aprovadas): R$ {total_geral_mes:.2f}")
    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(
        40, y,
        f"PIX: R$ {totais_pg['PIX']:.2f}   |   Cartão: R$ {totais_pg['Cartão']:.2f}   |   "
        f"Dinheiro: R$ {totais_pg['Dinheiro']:.2f}   |   Outros: R$ {totais_pg['OUTROS']:.2f}"
    )

    # Gráfico
    if chart_ok:
        try:
            c.drawImage(ImageReader(chart_path), 40, 395, width=520, height=220,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            chart_ok = False

    if not chart_ok:
        c.setFont("Helvetica", 10)
        c.drawString(40, 625, "(Gráfico indisponível — matplotlib não encontrado. Relatório gerado sem gráfico.)")

    # Ranking
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 375, f"Ranking TOP {top_n} de produtos (por valor vendido)")
    c.setFont("Helvetica", 10)
    c.drawString(40, 363, "#")
    c.drawString(60, 363, "Produto")
    c.drawString(400, 363, "Qtd")
    c.drawString(520, 363, "Valor")
    c.drawString(40, 357, "-" * 110)

    y = 341
    c.setFont("Helvetica", 10)
    if not ranking:
        c.drawString(40, y, "Nenhuma venda registrada neste mês.")
        y -= 14
    else:
        for idx, (produto, qtd_total, valor_total) in enumerate(ranking, start=1):
            prod_txt = str(produto or "(sem produto)")
            if len(prod_txt) > 48:
                prod_txt = prod_txt[:45] + "..."
            c.drawString(40, y, str(idx))
            c.drawString(60, y, prod_txt)
            c.drawRightString(455, y, str(int(qtd_total or 0)))
            c.drawRightString(590, y, f"R$ {float(valor_total or 0.0):.2f}")
            y -= 14
            if y < 110:
                c.showPage()
                if os.path.exists(logo_path_local):
                    try:
                        c.drawImage(ImageReader(logo_path_local), 40, 770, width=140, height= 35,
                                    preserveAspectRatio=True, mask="auto")
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 13)
                c.drawString(40, 745, f"Relatório Mensal de Vendas — {mes:02d}/{ano:04d} (continuação)")
                c.setFont("Helvetica", 11)
                c.drawString(40, 728, "-" * 110)
                c.setFont("Helvetica-Bold", 11)
                c.drawString(40, 730, f"Ranking TOP {top_n} de produtos (por valor vendido)")
                c.setFont("Helvetica", 10)
                c.drawString(40, 718, "#")
                c.drawString(60, 718, "Produto")
                c.drawString(400, 718, "Qtd")
                c.drawString(520, 718, "Valor")
                c.drawString(40, 712, "-" * 110)
                y = 696

    # Totais por dia (tabela)
    if y < 140:
        c.showPage()
        if os.path.exists(logo_path_local):
            try:
                c.drawImage(ImageReader(logo_path_local), 40, 770, width=140, height= 35,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, 745, f"Relatório Mensal de Vendas — {mes:02d}/{ano:04d} (totais por dia)")
        c.setFont("Helvetica", 11)
        c.drawString(40, 728, "-" * 110)
        y = 730

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Totais por dia")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "Data")
    c.drawString(160, y, "Total")
    y -= 6
    c.drawString(40, y, "-" * 110)
    y -= 14

    for dt, val in zip(datas, valores):
        c.drawString(40, y, dt)
        c.drawRightString(220, y, f"R$ {float(val):.2f}")
        y -= 14
        if y < 60:
            c.showPage()
            y = 780

    c.save()

    # Limpa png temporário
    try:
        if chart_ok and os.path.exists(chart_path):
            os.remove(chart_path)
    except Exception:
        pass

    try:
        backup_pdf(nome_arquivo, "relatorios")
    except Exception:
        pass

    try:
        open_in_default_app(nome_arquivo)
    except Exception:
        pass

    bring_app_to_front()
    return nome_arquivo
# ================= FORMATAÇÃO CPF/TELEFONE/MOEDA =================
def formatar_cpf(event, entry):
    texto = "".join(filter(str.isdigit, entry.get()))[:11]
    novo = ""
    for i, c in enumerate(texto):
        if i == 3 or i == 6:
            novo += "."
        if i == 9:
            novo += "-"
        novo += c
    entry.delete(0, "end")
    entry.insert(0, novo)
def formatar_telefone(event, entry):
    texto = "".join(filter(str.isdigit, entry.get()))[:11]
    novo = ""
    for i, c in enumerate(texto):
        if i == 0:
            novo += "("
        if i == 2:
            novo += ") "
        if i == 7:
            novo += "-"
        novo += c
    entry.delete(0, "end")
    entry.insert(0, novo)
def formatar_moeda(event, entry):
    valor = entry.get().replace("R$", "").replace(",", ".").strip()
    if valor:
        try:
            valor_float = float(valor)
            entry.delete(0, "end")
            entry.insert(0, f"R$ {valor_float:.2f}")
        except Exception:
            entry.delete(0, "end")
            entry.insert(0, "R$ 0.00")
    else:
        entry.delete(0, "end")
        entry.insert(0, "")


# ================= DASHBOARD (Resumo / KPIs) =================
# Aba inicial com indicadores e mini-gráfico (sparkline) opcional via matplotlib.
# Não altera regras do sistema; apenas consome as tabelas existentes.

def _dash_fmt_brl(valor: float) -> str:
    """Formata número para Real (pt-BR) sem depender de locale."""
    try:
        v = float(valor or 0.0)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    # converte 1,234.56 -> 1.234,56
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


# ===================== CAIXA: TOTAIS DO DIA (Bruto / Saídas / Líquido) =====================
# Bruto: soma de vendas do dia (tabela vendas)
# Saídas: soma absoluta das saídas do dia (tabela caixa, valor < 0)
# Líquido: bruto - saídas

def calcular_totais_dia(data_str: str = None):
    """Retorna (vendas_dia, saidas_dia, liquido_dia) para a data informada (dd/mm/aaaa)."""
    data_str = data_str or datetime.datetime.now().strftime("%d/%m/%Y")

    try:
        cursor.execute("SELECT COALESCE(SUM(total),0) FROM vendas WHERE data=?", (data_str,))
        vendas_dia = float((cursor.fetchone() or [0])[0] or 0.0)
    except Exception:
        vendas_dia = 0.0

    try:
        cursor.execute("SELECT COALESCE(SUM(valor),0) FROM caixa WHERE data=? AND valor < 0", (data_str,))
        saidas_neg = float((cursor.fetchone() or [0])[0] or 0.0)
        saidas_dia = abs(saidas_neg)
    except Exception:
        saidas_dia = 0.0

    liquido_dia = float(vendas_dia) - float(saidas_dia)
    return float(vendas_dia), float(saidas_dia), float(liquido_dia)

# ===================== FIM CAIXA: TOTAIS DO DIA =====================


def _dash_datas_ultimos_dias(n: int = 7):
    hoje = datetime.date.today()
    return [(hoje - datetime.timedelta(days=i)).strftime("%d/%m/%Y") for i in range(int(n))][::-1]


def _dash_mes_ano_atual():
    hoje = datetime.date.today()
    return f"{hoje.month:02d}", f"{hoje.year:04d}"


def _dash_criar_card(parent, titulo: str, valor_inicial: str = "—", subtitulo: str = ""):
    """Card simples estilo KPI."""
    card = ttk.Frame(parent, padding=12)
    lbl_t = ttk.Label(card, text=titulo, font=("Segoe UI", 10, "bold"))
    lbl_v = ttk.Label(card, text=valor_inicial, font=("Segoe UI", 18, "bold"))
    lbl_s = ttk.Label(card, text=subtitulo or "", font=("Segoe UI", 9))
    lbl_t.pack(anchor="w")
    lbl_v.pack(anchor="w", pady=(6, 0))
    if subtitulo is not None:
        lbl_s.pack(anchor="w", pady=(4, 0))
    return card, lbl_v, lbl_s


def _dash_gerar_sparkline_img(valores, width: int = 260, height: int = 60):
    """Gera uma sparkline como PhotoImage (ou None)."""
    try:
        if not globals().get('_HAS_MPL') or globals().get('plt') is None:
            return None
        plt_mod = globals().get('plt')
        fig = plt_mod.figure(figsize=(max(1, width) / 100.0, max(1, height) / 100.0), dpi=100)
        ax = fig.add_subplot(111)
        xs = list(range(len(valores)))
        ax.plot(xs, valores, linewidth=2.0, color="#2563eb")
        ax.fill_between(xs, valores, alpha=0.15, color="#2563eb")
        ax.set_axis_off()
        fig.tight_layout(pad=0)
        buf = BytesIO()
        fig.savefig(buf, format="png", transparent=True)
        try:
            plt_mod.close(fig)
        except Exception:
            pass
        buf.seek(0)
        img = Image.open(buf)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def montar_aba_resumo_dashboard(abas: ttk.Notebook, conn: sqlite3.Connection, cursor: sqlite3.Cursor):
    """Cria a aba Resumo/Home com KPIs e atualiza a cada 60s. Retorna o frame da aba."""
    aba_resumo = ttk.Frame(abas, padding=10)
    try:
        abas.insert(0, aba_resumo, text="Resumo")
    except Exception:
        abas.add(aba_resumo, text="Resumo")

    # Layout base
    aba_resumo.columnconfigure(0, weight=1)
    aba_resumo.columnconfigure(1, weight=1)

    # Linha 1: Vendas Hoje / 7 dias / Mês
    row1 = ttk.Frame(aba_resumo)
    row1.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    for i in range(3):
        row1.columnconfigure(i, weight=1)

    card_dia, lbl_dia, _ = _dash_criar_card(row1, "Vendas (Hoje)")
    card_sem, lbl_sem, _ = _dash_criar_card(row1, "Vendas (7 dias)")
    card_mes, lbl_mes, _ = _dash_criar_card(row1, "Vendas (Mês)")

    card_dia.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    card_sem.grid(row=0, column=1, sticky="ew", padx=8)
    card_mes.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    # Sparkline dentro do card do mês
    spark_lbl = ttk.Label(card_mes)
    spark_lbl.pack(anchor="w", pady=(8, 0))

    # Linha 2: Totais por pagamento (mês)
    row2 = ttk.Frame(aba_resumo)
    row2.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    for i in range(4):
        row2.columnconfigure(i, weight=1)

    card_pix, lbl_pix, _ = _dash_criar_card(row2, "PIX (Mês)")
    card_car, lbl_car, _ = _dash_criar_card(row2, "Cartão (Mês)")
    card_din, lbl_din, _ = _dash_criar_card(row2, "Dinheiro (Mês)")
    card_out, lbl_out, _ = _dash_criar_card(row2, "Outros (Mês)")

    card_pix.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    card_car.grid(row=0, column=1, sticky="ew", padx=8)
    card_din.grid(row=0, column=2, sticky="ew", padx=8)
    card_out.grid(row=0, column=3, sticky="ew", padx=(8, 0))

    # Linha 3: Top 5 / Estoque crítico
    box_left = ttk.Frame(aba_resumo)
    box_right = ttk.Frame(aba_resumo)
    box_left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
    box_right.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
    aba_resumo.rowconfigure(2, weight=1)

    ttk.Label(box_left, text="Top 5 Produtos (Mês)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
    top_list = tk.Listbox(box_left, height=8)
    top_list.pack(fill="both", expand=True)

    ttk.Label(box_right, text="Estoque Crítico (≤5)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
    stock_list = tk.Listbox(box_right, height=8)
    stock_list.pack(fill="both", expand=True)

    # Linha 4: OS + Pontos
    row4 = ttk.Frame(aba_resumo)
    row4.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    for i in range(3):
        row4.columnconfigure(i, weight=1)

    card_os_p, lbl_os_p, _ = _dash_criar_card(row4, "OS Pendentes (Mês)")
    card_os_a, lbl_os_a, _ = _dash_criar_card(row4, "OS Aprovadas (Mês)")
    card_pts, lbl_pts, _ = _dash_criar_card(row4, "Pontos Resgatados (Mês)")

    card_os_p.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    card_os_a.grid(row=0, column=1, sticky="ew", padx=8)
    card_pts.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    # manter referência das imagens para evitar GC
    state = {"spark_img": None}

    def _refresh():
        try:
            hoje = datetime.date.today().strftime("%d/%m/%Y")
            mm, yyyy = _dash_mes_ano_atual()

            # Vendas hoje
            cursor.execute("SELECT COALESCE(SUM(total),0) FROM vendas WHERE data=?", (hoje,))
            total_hoje = float((cursor.fetchone() or [0])[0] or 0.0)

            # Vendas 7 dias
            dias7 = _dash_datas_ultimos_dias(7)
            qmarks = ",".join(["?"] * len(dias7))
            cursor.execute(f"SELECT COALESCE(SUM(total),0) FROM vendas WHERE data IN ({qmarks})", tuple(dias7))
            total_7d = float((cursor.fetchone() or [0])[0] or 0.0)

            # Vendas mês
            cursor.execute(
                "SELECT COALESCE(SUM(total),0) FROM vendas WHERE substr(data,4,2)=? AND substr(data,7,4)=?",
                (mm, yyyy),
            )
            total_mes = float((cursor.fetchone() or [0])[0] or 0.0)

            lbl_dia.config(text=_dash_fmt_brl(total_hoje))
            lbl_sem.config(text=_dash_fmt_brl(total_7d))
            lbl_mes.config(text=_dash_fmt_brl(total_mes))

            # Pagamentos mês
            cursor.execute(
                """
                SELECT pagamento, COALESCE(SUM(total),0)
                FROM vendas
                WHERE substr(data,4,2)=? AND substr(data,7,4)=?
                GROUP BY pagamento
                """,
                (mm, yyyy),
            )
            totals = {"PIX": 0.0, "Cartão": 0.0, "Dinheiro": 0.0, "OUTROS": 0.0}
            for pg, val in (cursor.fetchall() or []):
                pg = (pg or "").strip()
                v = float(val or 0.0)
                if pg.startswith("Upgrade"):
                    totals["OUTROS"] += v
                elif pg in totals:
                    totals[pg] += v
                else:
                    totals["OUTROS"] += v

            lbl_pix.config(text=_dash_fmt_brl(totals["PIX"]))
            lbl_car.config(text=_dash_fmt_brl(totals["Cartão"]))
            lbl_din.config(text=_dash_fmt_brl(totals["Dinheiro"]))
            lbl_out.config(text=_dash_fmt_brl(totals["OUTROS"]))

            # Top 5 produtos
            top_list.delete(0, "end")
            cursor.execute(
                """
                SELECT produto, COALESCE(SUM(total),0) AS valor_total
                FROM vendas
                WHERE substr(data,4,2)=? AND substr(data,7,4)=?
                GROUP BY produto
                ORDER BY valor_total DESC
                LIMIT 5
                """,
                (mm, yyyy),
            )
            for prod, val in (cursor.fetchall() or []):
                prod = (prod or "(sem produto)")
                top_list.insert("end", f"{prod[:45]} — {_dash_fmt_brl(float(val or 0.0))}")

            # Estoque crítico
            stock_list.delete(0, "end")
            cursor.execute(
                """
                SELECT nome, COALESCE(estoque,0)
                FROM produtos
                WHERE COALESCE(estoque,0) <= 5
                ORDER BY COALESCE(estoque,0) ASC, nome ASC
                LIMIT 10
                """
            )
            for nome, est in (cursor.fetchall() or []):
                stock_list.insert("end", f"{(nome or '')[:48]} — {int(est or 0)} un")

            # OS pendentes/aprovadas
            cursor.execute(
                """
                SELECT
                  SUM(CASE WHEN COALESCE(aprovado,0)=0 THEN 1 ELSE 0 END) AS pendentes,
                  SUM(CASE WHEN COALESCE(aprovado,0)=1 THEN 1 ELSE 0 END) AS aprovadas
                FROM manutencao
                WHERE substr(data,4,2)=? AND substr(data,7,4)=?
                """,
                (mm, yyyy),
            )
            pend, aprov = cursor.fetchone() or (0, 0)
            lbl_os_p.config(text=str(int(pend or 0)))
            lbl_os_a.config(text=str(int(aprov or 0)))

            # Pontos resgatados no mês
            cursor.execute(
                """
                SELECT COALESCE(SUM(pontos_usados),0)
                FROM resgates_pontos
                WHERE substr(data,4,2)=? AND substr(data,7,4)=?
                """,
                (mm, yyyy),
            )
            pts = int((cursor.fetchone() or [0])[0] or 0)
            lbl_pts.config(text=f"{pts} pts")

            # Sparkline (últimos 14 dias)
            dias14 = _dash_datas_ultimos_dias(14)
            qmarks14 = ",".join(["?"] * len(dias14))
            cursor.execute(
                f"""
                SELECT data, COALESCE(SUM(total),0)
                FROM vendas
                WHERE data IN ({qmarks14})
                GROUP BY data
                """,
                tuple(dias14),
            )
            mp = {str(d): float(v or 0.0) for d, v in (cursor.fetchall() or [])}
            serie = [mp.get(d, 0.0) for d in dias14]
            img = _dash_gerar_sparkline_img(serie)
            if img is not None:
                state["spark_img"] = img
                spark_lbl.config(image=img, text="")
            else:
                spark_lbl.config(image="", text="(sparkline indisponível)")

        except Exception as ex:
            try:
                logging.error(f"Falha ao atualizar dashboard: {ex}", exc_info=True)
            except Exception:
                pass
        finally:
            try:
                aba_resumo.after(60000, _refresh)
            except Exception:
                pass

    # atualiza ao abrir e também periodicamente
    _refresh()

    # Atualiza ao selecionar a aba
    def _on_tab_changed(event=None):
        try:
            if abas.select() == aba_resumo._w:
                _refresh()
        except Exception:
            pass

    try:
        abas.bind("<<NotebookTabChanged>>", _on_tab_changed, add=True)
    except Exception:
        pass

    return aba_resumo

# ================= FIM DASHBOARD =================


# ===================== NOTEBOOK: ORDENAR ABAS (UI) =====================
def reorder_notebook_tabs_alphabetical(abas: 'ttk.Notebook'):
    """Reordena as abas do ttk.Notebook em ordem alfabética (conforme labels).

    Mantém frames e widgets; apenas remove e adiciona novamente as abas na ordem desejada.
    Se alguma aba não existir, ela é ignorada.
    Abas não listadas explicitamente serão mantidas ao final, preservando a ordem atual.
    """
    try:
        desired = [
            'Agendamento',
            'Caixa',
            'Clientes',
            'Devolução',
            'Estoque',
            'Ferramentas',
            'Manutenção',
            'Pontuação',
            'Resumo',
            'Upgrade',
            'Vendas',
        ]
        current_tabs = list(abas.tabs())
        if not current_tabs:
            return

        selected = abas.select()

        tab_info = {}
        for tid in current_tabs:
            try:
                w = abas.nametowidget(tid)
            except Exception:
                w = None

            cfg = {}
            for opt in ('text', 'image', 'compound', 'underline', 'sticky', 'state'):
                try:
                    cfg[opt] = abas.tab(tid, opt)
                except Exception:
                    pass

            tab_info[tid] = {
                'widget': w,
                'cfg': cfg,
                'text': cfg.get('text', ''),
            }

        # Remove todas as abas
        for tid in current_tabs:
            try:
                abas.forget(tid)
            except Exception:
                pass

        used = set()

        def _add_tab(widget, cfg, fallback_text=''):
            try:
                cfg2 = {k: v for k, v in (cfg or {}).items()
                        if k in ('text','image','compound','underline','sticky','state') and v not in (None, '')}
                if 'text' not in cfg2 and fallback_text:
                    cfg2['text'] = fallback_text
                abas.add(widget, **cfg2)
                return
            except Exception:
                try:
                    abas.add(widget, text=fallback_text or '')
                except Exception:
                    pass

        # Re-adiciona na ordem desejada
        for label in desired:
            tid = next((t for t, info in tab_info.items() if str(info.get('text','')) == label), None)
            if not tid:
                continue
            info = tab_info.get(tid) or {}
            w = info.get('widget')
            if w is None:
                continue
            _add_tab(w, info.get('cfg') or {}, fallback_text=label)
            used.add(tid)

        # Abas restantes no final
        for tid in current_tabs:
            if tid in used:
                continue
            info = tab_info.get(tid) or {}
            w = info.get('widget')
            if w is None:
                continue
            _add_tab(w, info.get('cfg') or {}, fallback_text=info.get('text') or '')

        # Restaura seleção
        try:
            if selected:
                abas.select(selected)
        except Exception:
            pass

    except Exception:
        return
# =================== FIM NOTEBOOK: ORDENAR ABAS ===================

# ================= SISTEMA PRINCIPAL =================
def abrir_sistema_com_logo(username, login_win):
    root = tk.Toplevel()
    root.title(f"BESIM COMPANY - Usuário: {username} ")
    root.geometry("1280x720")
    root.minsize(1100, 600)
    root.lift()
    root.focus_force()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    _bind_fullscreen_shortcuts(root)
    setup_global_exception_handlers(root)
    # Executa atualização após login (se houver)
    try:
        updated = check_and_update_after_login(root)
        if updated:
            return  # app será reiniciado
    except Exception:
        pass

    # Mostra novidades da versão (uma vez por versão, com 'Ler depois')
    try:
        maybe_show_release_notes(root)
    except Exception:
        pass

    # 🔊 Som de boas-vindas ~200ms após a janela subir (não bloqueia a UI)
    try:
        root.after(200, lambda: tocar_som_agradavel(os.path.join("media", "welcome.wav")))
    except Exception:
        pass

    closing_state = {"mode": None}

    def on_close():
        # 1) Logout: volta para o login sem mensagem de despedida
        if closing_state.get("mode") == "logout":
            try:
                root.destroy()
            except Exception:
                pass
            try:
                if login_win and login_win.winfo_exists():
                    login_win.deiconify()
                    login_win.lift()
                    login_win.focus_force()
                    if hasattr(login_win, "ent_user"):
                        login_win.ent_user.delete(0, "end")
                    if hasattr(login_win, "ent_pass"):
                        login_win.ent_pass.delete(0, "end")
            except Exception:
                pass
            closing_state["mode"] = None
            return

        # 2) Encerrar o programa: mostra despedida (duas linhas)
        if messagebox.askyesno("Sair", "Tem certeza que deseja encerrar o sistema?"):
            try:
                show_goodbye_screen(root, "Até Logo,\nBom descanso", duration_ms=1500)
            except Exception:
                pass

            def _finalizar_saida():
                try:
                    if login_win and login_win.winfo_exists():
                        login_win.destroy()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            root.after(1600, _finalizar_saida)
            return
        return

    root.protocol("WM_DELETE_WINDOW", on_close)

    menu_bar = tk.Menu(root)
    menu_sessao = tk.Menu(menu_bar, tearoff=0)
    # Tema (runtime)
    menu_tema = tk.Menu(menu_sessao, tearoff=0)
    tema_var = tk.StringVar(value="dark")
    def _on_theme_change():
        try:
            apply_theme(tema_var.get())
            _refresh_theme_widgets()
            _refresh_statusbar_theme()
            try:
                for t in (tree_cli, tree_upgrades, ag_tree, tree_cx, tree_m, tree_dev, tree_pontos):
                # Estoque: sem zebra (somente cores por quantidade)
                    configure_zebra_tags(t, current_theme["name"])
                    apply_zebra(t)
            except Exception:
                pass
        except Exception:
            pass
    menu_tema.add_radiobutton(label="Escuro (Modern Dark)", variable=tema_var, value="dark", command=_on_theme_change)
    menu_tema.add_radiobutton(label="Claro (Windows 11)", variable=tema_var, value="light", command=_on_theme_change)
    menu_sessao.add_cascade(label="Tema", menu=menu_tema)

    # Atualizações / Melhorias (Release Notes)
    def abrir_atualizacoes():
        try:
            show_release_notes(root, force=True)
        except Exception as ex:
            try:
                messagebox.showerror('Atualização', f'Falha ao abrir atualizações:\n{ex}')
            except Exception:
                pass

    menu_sessao.add_separator()
    menu_sessao.add_command(label='Atualizações / Melhorias…', command=abrir_atualizacoes)
    def do_logout():
        if messagebox.askyesno(
            "Logout", "Deseja finalizar a sessão e voltar ao login?"
        ):
            closing_state["mode"] = "logout"
            on_close()
    def do_quit():
        closing_state["mode"] = None
        on_close()

    def alterar_senha():
        dlg = ChangePasswordDialog(root, username, must_change=False)
        root.wait_window(dlg)

    menu_sessao.add_command(label="Alterar senha…", command=alterar_senha)

    # >>> Gestão de Usuários (somente admin)

    def abrir_gerenciar_usuarios():

        if not is_admin(username):

            messagebox.showerror("Permissão negada", "Apenas administradores podem gerenciar usuários.")

            return

        UserAdminDialog(root, current_admin=username)


    if is_admin(username):

        try:

            menu_sessao.add_separator()

            menu_sessao.add_command(label="Usuários (Admin)…", command=abrir_gerenciar_usuarios)
            try:
                # [REMOVIDO] menu_sessao.add_command(label="Licença (Admin)…", command=lambda: admin_gerar_enviar_licenca_dialog(root))
                pass
            except Exception:
                pass

        except Exception:

            pass
    menu_sessao.add_command(label="Logout", accelerator="Ctrl+L", command=do_logout)
    menu_sessao.add_separator()
    menu_sessao.add_command(label="Sair", accelerator="Ctrl+Q", command=do_quit)
    menu_bar.add_cascade(label="Sessão", menu=menu_sessao)

    # Menu separado: Atualização
    menu_atualizacao = tk.Menu(menu_bar, tearoff=0)
    menu_atualizacao.add_command(label='Ver novidades / melhorias…', command=abrir_atualizacoes)
    try:
        menu_atualizacao.add_command(label='Abrir RELEASE_NOTES.txt', command=lambda: open_in_default_app(str(_runtime_app_dir() / RELEASE_NOTES_FILE)))
    except Exception:
        pass
    menu_bar.add_cascade(label='Atualização', menu=menu_atualizacao)
    root.config(menu=menu_bar)
    root.bind_all("<Control-l>", lambda e: do_logout())
    root.bind_all("<Control-q>", lambda e: do_quit())
    root.bind_all("<Control-f>", lambda e: fechar_caixa())
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    default_font = ("Segoe UI", 10)
    heading_font = ("Segoe UI", 11, "bold")
    style.configure(".", font=default_font)
    style.configure("TLabel", font=default_font, padding=6)
    style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    style.configure("Treeview.Heading", font=heading_font)
    style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))

    # ====== MELHORIAS DE LAYOUT / TEMA (Modern Dark + toggle runtime) ======
    # Tema padrão: ESCURO (grafite) com destaques azul/verde
    current_theme = {"name": "dark"}
    palette = THEME_DARK

    def _apply_custom_styles(theme_name: str):
        nonlocal palette
        palette = THEME_DARK if theme_name == 'dark' else THEME_LIGHT

        # Fontes globais
        style.configure('.', font=BASE_FONT)
        style.configure('TLabel', font=BASE_FONT, padding=6)
        style.configure('TButton', font=BUTTON_FONT, padding=6)
        style.configure('TEntry', padding=4)
        style.configure('TCombobox', padding=4)

        # Notebook (abas) mais bonito
        style.configure('TNotebook.Tab', padding=[16, 10], font=("Segoe UI", 10, 'bold'))
        style.map('TNotebook.Tab',
                  foreground=[('selected', '#ffffff'), ('!selected', palette['muted'])],
                  background=[('selected', palette['accent']), ('!selected', palette['panel2'])])

        # Treeview (tabela) — header + seleção
        style.configure('Treeview.Heading', font=HEADING_FONT)
        try:
            style.configure('Treeview.Heading', background=palette['panel2'], foreground=palette['text'])
        except Exception:
            pass
        style.configure('Treeview', rowheight=28, font=BASE_FONT)
        style.configure('Treeview',
                        background=palette['bg'],
                        fieldbackground=palette['bg'],
                        foreground=palette['text'])
        style.map('Treeview',
                  foreground=[('selected', '#ffffff')],
                  background=[('selected', palette['accent'])])

    def apply_theme(theme_name: str):
        # sv-ttk (se disponível)
        if _HAS_SV_TTK and sv_ttk is not None:
            try:
                sv_ttk.set_theme(theme_name)
            except Exception:
                pass
        else:
            try:
                style.theme_use('clam')
            except Exception:
                pass
        current_theme['name'] = theme_name
        _apply_custom_styles(theme_name)

    # Aplica tema inicial
    apply_theme('dark')

    # Adicionando espaçamento padrão

    PADX = 8
    PADY = 6
    # ====== ESTILOS DE BOTÕES (cores e hover) ======
    # Paleta inspirada nas cores Tailwind para consistência visual
    style.configure("Success.TButton", foreground="white", background="#22c55e", padding=6)
    style.map("Success.TButton", background=[("active", "#16a34a"), ("pressed", "#15803d")])
    style.configure("Danger.TButton", foreground="white", background="#ef4444", padding=6)
    style.map("Danger.TButton", background=[("active", "#dc2626"), ("pressed", "#b91c1c")])
    style.configure("Secondary.TButton", foreground="white", background="#64748b", padding=6)
    style.map("Secondary.TButton", background=[("active", "#475569"), ("pressed", "#334155")])
    style.configure("Accent.TButton", foreground="white", background="#2563eb", padding=6)
    style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])
    # Botão já usado para fechar caixa
    style.configure("FecharCaixa.TButton", foreground="white", background="#2563eb", padding=6)
    style.map("FecharCaixa.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])
    style.configure("TNotebook.Tab", padding=[12, 8], font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", tabposition="n")
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    # ====== HEADER premium (logo + nome + versão + usuário + sair) ======
    header = tk.Frame(root, bg=palette['panel'], highlightbackground=palette['border'], highlightthickness=1)
    header.pack(fill='x', padx=12, pady=(10, 6))

    h_left = tk.Frame(header, bg=palette['panel'])
    h_left.pack(side='left', fill='x', expand=True)

    logo_path = str(P('logo.png'))
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((170, 52))
            log_img = ImageTk.PhotoImage(img)
            lbl_logo = tk.Label(h_left, image=log_img, bg=palette['panel'])
            lbl_logo.image = log_img
            lbl_logo.pack(side='left', padx=(10, 10), pady=8)
        except Exception:
            pass

    title_box = tk.Frame(h_left, bg=palette['panel'])
    title_box.pack(side='left', pady=8)
    tk.Label(title_box, text="BESIM COMPANY", bg=palette['panel'], fg=palette['text'],
             font=("Segoe UI", 14, "bold")).pack(anchor='w')
    tk.Label(title_box, text=f"Sistema Loja • v{get_local_version()}", bg=palette['panel'], fg=palette['muted'],
             font=("Segoe UI", 10)).pack(anchor='w')

    h_right = tk.Frame(header, bg=palette['panel'])
    h_right.pack(side='right', pady=8, padx=10)

    role = "admin" if is_admin(username) else "user"
    chip = tk.Frame(h_right, bg=palette['panel2'], highlightbackground=palette['border'], highlightthickness=1)
    chip.pack(side='right', padx=(8, 0))
    lbl_chip = tk.Label(chip, text=f"👤 {username} ({role})", bg=palette['panel2'], fg=palette['text'],
                        font=("Segoe UI", 10, "bold"))
    lbl_chip.pack(side='left', padx=10, pady=6)

    btn_sair = ttk.Button(h_right, text="Sair", style="Danger.TButton", command=do_logout)
    btn_sair.pack(side='right')

    _theme_widgets = {
        'header': header, 'h_left': h_left, 'h_right': h_right, 'title_box': title_box,
        'chip': chip, 'lbl_chip': lbl_chip
    }

    def _refresh_theme_widgets():
        try:
            pal = THEME_DARK if current_theme['name'] == 'dark' else THEME_LIGHT
            for key in ('header', 'h_left', 'h_right', 'title_box'):
                _theme_widgets[key].configure(bg=pal['panel'], highlightbackground=pal['border'])
            _theme_widgets['chip'].configure(bg=pal['panel2'], highlightbackground=pal['border'])
            _theme_widgets['lbl_chip'].configure(bg=pal['panel2'], fg=pal['text'])
        except Exception:
            pass

    # Notebook
    abas = ttk.Notebook(root)

    abas.pack(fill="both", expand=True, padx=12, pady=(8, 0))
    # Fallback: garante que o rodapé (statusbar) apareça
    try:
        root.after(50, lambda: force_attach_statusbar(root))
    except Exception:
        try:
            force_attach_statusbar(root)
        except Exception:
            pass

    # ====== RESUMO (Dashboard KPIs) ======
    try:
        montar_aba_resumo_dashboard(abas, conn, cursor)
    except Exception as _ex_dash:
        try:
            logging.error(f'Falha ao montar aba Resumo: {_ex_dash}', exc_info=True)
        except Exception:
            pass

    aba_estoque = ttk.Frame(abas, padding=10)
    aba_vendas = ttk.Frame(abas, padding=10)
    aba_clientes = ttk.Frame(abas, padding=10)
    aba_devedores = ttk.Frame(abas, padding=10)
    aba_caixa = ttk.Frame(abas, padding=10)
    aba_manutencao = ttk.Frame(abas, padding=10)
    aba_devolucao = ttk.Frame(abas, padding=10)
    abas.add(aba_estoque, text="Estoque")
    abas.add(aba_vendas, text="Vendas")
    abas.add(aba_clientes, text="Clientes")
    abas.add(aba_devedores, text="Devedores")
    abas.add(aba_caixa, text="Caixa")
    abas.add(aba_manutencao, text="Manutenção")
    abas.add(aba_devolucao, text="Devolução")

    aba_agendamento = ttk.Frame(abas, padding=10)
    abas.add(aba_agendamento, text="Agendamento")

    # Atualiza automaticamente a aba Vendas quando ela for selecionada
    def _on_tab_changed(event=None):

        try:
            if abas.select() == aba_vendas._w:
                carregar_vendas_dia()
            if abas.select() == aba_caixa._w:
                atualizar_caixa()
        except Exception:
            pass

    abas.bind("<<NotebookTabChanged>>", _on_tab_changed)

    # ====== UPGRADE ======
    aba_upgrade = ttk.Frame(abas, padding=10)
    abas.add(aba_upgrade, text="Upgrade")
    aba_pontuacao = ttk.Frame(abas, padding=10)
    abas.add(aba_pontuacao, text="Pontuação")
    # Reordena as abas em ordem alfabética (UI)
    try:
        reorder_notebook_tabs_alphabetical(abas)
    except Exception:
        pass


    # Aba Ferramentas (atalhos com ícones)
    try:
        montar_aba_ferramentas(abas, root)
    except Exception as _ex_tools:
        try:
            logging.error(f'Falha ao montar aba Ferramentas: {_ex_tools}', exc_info=True)
        except Exception:
            pass

    f_u = ttk.Frame(aba_upgrade, padding=8)
    f_u.pack(fill="x", pady=6)
    ttk.Label(f_u, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_u = ttk.Entry(f_u)
    ent_cpf_u.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_u.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_u))
    ttk.Label(f_u, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_u = ttk.Entry(f_u)
    ent_nome_u.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_u, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_u = ttk.Entry(f_u)
    ent_tel_u.grid(row=0, column=5, padx=6, pady=4)
    ent_tel_u.bind("<KeyRelease>", lambda e: formatar_telefone(e, ent_tel_u))
    ttk.Label(f_u, text="Descrição").grid(row=1, column=0, sticky="w", padx=6, pady=6)
    ent_desc_u = ttk.Entry(f_u, width=70)
    ent_desc_u.grid(row=1, column=1, columnspan=4, pady=4, padx=6, sticky="we")
    ttk.Label(f_u, text="Valor").grid(row=1, column=5, sticky="w", padx=6, pady=6)
    ent_valor_u = ttk.Entry(f_u, width=18)
    ent_valor_u.grid(row=1, column=6, padx=6, pady=6)
    ent_valor_u.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_valor_u))
    ttk.Label(f_u, text="Pagamento").grid(row=2, column=5, sticky="w", padx=6, pady=6)
    ent_pg_u = ttk.Combobox(f_u, values=["PIX", "Cartão", "Dinheiro"], width=16)
    ent_pg_u.grid(row=2, column=6, padx=6, pady=6)
    def buscar_cliente_u():
        cpf = ent_cpf_u.get().strip()
        cursor.execute("SELECT nome, telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_u.delete(0, "end")
            ent_nome_u.insert(0, r[0])
            ent_tel_u.delete(0, "end")
            ent_tel_u.insert(0, r[1])
    ttk.Button(f_u, text="🔍 Buscar Cliente", style="Secondary.TButton", command=buscar_cliente_u).grid(row=0, column=6, padx=6)
    def finalizar_upgrade():
        try:
            cpf = ent_cpf_u.get().strip()
            cliente = ent_nome_u.get().strip() or "Sem Nome"
            telefone = ent_tel_u.get().strip()
            descricao = ent_desc_u.get().strip()
            valor_text = ent_valor_u.get().replace("R$", "").replace(",", ".").strip()
            if not descricao or not valor_text:
                messagebox.showwarning("Atenção", "Informe descrição e valor válido")
                return
            valor = float(valor_text)
            data = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            with conn:
                cursor.execute("INSERT INTO vendas(cliente,cpf,produto,quantidade,total,pagamento,data,hora) VALUES (?,?,?,?,?,?,?,?)", (cliente, cpf, descricao, 1, valor, (f"Upgrade - {ent_pg_u.get().strip()}" if ent_pg_u.get().strip() else "Upgrade"), data, hora))

                # >>> NOVO: soma pontos do cliente (Upgrade também soma pontos)
                cursor.execute(
                    "INSERT OR IGNORE INTO pontuacao(cpf,pontos,atualizado_em) VALUES(?,?,?)",
                    (cpf, 0, datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
                )
                adicionar_pontos_cliente(cpf, valor)
                # <<< FIM NOVO: pontos
                cursor.execute("INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)", (valor, data, hora, (f"Upgrade - {ent_pg_u.get().strip()}" if ent_pg_u.get().strip() else "Upgrade")))
                cursor.execute("INSERT OR IGNORE INTO clientes(cpf,nome,telefone) VALUES (?,?,?)", (cpf, cliente, telefone))
            try:
                caminho_pdf = gerar_cupom(cliente, descricao, 1, (ent_pg_u.get().strip() or "Upgrade"), valor, cpf=cpf)

                try:
                    telegram_notify(f"""🆙 <b>UPGRADE REGISTRADO</b>
                👤 Cliente: {cliente}
                📞 Tel: {telefone}
                📝 Desc: {descricao}
                💳 {ent_pg_u.get().strip() or 'Upgrade'}
                💰 Total: R$ {valor:.2f}
                🕒 {data} {hora}""", dedupe_key=f"upgrade_{data}_{hora}_{cpf}", dedupe_window_sec=30)
                except Exception:
                    pass
                try:
                    telegram_send_pdf("🧾 Cupom do upgrade", caminho_pdf, dedupe_key=f"cupom_upgrade_{data}_{hora}_{cpf}", dedupe_window_sec=60)
                except Exception:
                    pass
            except Exception:
                pass
            messagebox.showinfo("Upgrade", f"Upgrade registrado! Total: R$ {valor:.2f}")
            # Atualiza também a lista de vendas do dia (upgrades geram venda)
            try:
                aba_vendas.after(30, carregar_vendas_dia)
            except Exception:
                pass
            carregar_upgrades()
            ent_cpf_u.delete(0, "end")
            ent_nome_u.delete(0, "end")
            ent_tel_u.delete(0, "end")
            ent_desc_u.delete(0, "end")
            ent_valor_u.delete(0, "end")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao registrar upgrade\n{ex}")
    ttk.Button(f_u, text="✓ Finalizar Upgrade", style="Success.TButton", command=finalizar_upgrade).grid(row=2, column=0, columnspan=2, pady=10, sticky="w", padx=6)
    # Histórico de Upgrades
    hist_u_frame = ttk.Frame(aba_upgrade, padding=(8, 0))
    hist_u_frame.pack(fill="both", expand=True)
    top_hist_u = ttk.Frame(hist_u_frame)
    top_hist_u.pack(fill="x", pady=(6, 6))
    ttk.Label(top_hist_u, text="Histórico de Upgrades", font=("Segoe UI", 11, "bold")).pack(side="left", padx=6)
    ttk.Button(top_hist_u, text="⟳ Atualizar", style="Secondary.TButton", command=lambda: carregar_upgrades()).pack(side="left", padx=6)
    tree_up_frame = ttk.Frame(hist_u_frame)
    tree_up_frame.pack(fill="both", expand=True)
    tree_upgrades = ttk.Treeview(tree_up_frame, columns=("Hora", "Cliente", "Descrição", "Pagamento", "Valor"), show="headings", height=10)
    configure_zebra_tags(tree_upgrades, current_theme["name"])
    for col, txt, anchor, width in [("Hora", "Hora", "center", 120), ("Cliente", "Cliente", "w", 200), ("Descrição", "Descrição", "w", 240), ("Pagamento", "Pagamento", "center", 140), ("Valor", "Valor", "e", 120)]:
        tree_upgrades.heading(col, text=txt)
        tree_upgrades.column(col, width=width, anchor=anchor)
    tree_upgrades.pack(side="left", fill="both", expand=True)
    scrollbar_upgrades = ttk.Scrollbar(tree_up_frame, orient="vertical", command=tree_upgrades.yview)
    tree_upgrades.configure(yscroll=scrollbar_upgrades.set)
    scrollbar_upgrades.pack(side="right", fill="y")
    # ====== FUNÇÃO PARA GERAR RELATÓRIO DE UPGRADES EM PDF ======
    def gerar_relatorio_upgrades_dia_pdf(data_str: str = None):
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        data_alvo = data_str or hoje
        pasta_rel = os.path.join(os.getcwd(), "relatorios")
        os.makedirs(pasta_rel, exist_ok=True)
        nome_arquivo = os.path.join(pasta_rel, f"relatorio_upgrades_{data_alvo.replace('/', '-')}.pdf")
        c = canvas.Canvas(nome_arquivo, pagesize=A4)
        logo_path_local = str(P('logo.png'))
        if os.path.exists(logo_path_local):
            try:
                c.drawImage(ImageReader(logo_path_local), 40, 780, width=140, height=40, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, 760, f"Relatório de Upgrades - {data_alvo}")
        c.setFont("Helvetica", 11)
        c.drawString(40, 742, "-" * 110)
        y = 720
        cursor.execute("SELECT hora, cliente, produto, pagamento, total FROM vendas WHERE data=? AND pagamento LIKE 'Upgrade%' ORDER BY hora DESC", (hoje,))
        linhas = cursor.fetchall()
        total_dia = 0.0
        if not linhas:
            c.drawString(40, y, "Nenhum upgrade registrado neste dia.")
            y -= 18
        else:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(40, y, "Hora")
            c.drawString(100, y, "Cliente")
            c.drawString(280, y, "Descrição")
            c.drawString(460, y, "Pagto")
            c.drawString(520, y, "Valor")
            y -= 16
            c.setFont("Helvetica", 10)
            for hora, cliente, produto, pagamento, total in linhas:
                total_dia += total or 0.0
                c.drawString(40, y, str(hora))
                c.drawString(100, y, str(cliente)[:24])
                c.drawString(280, y, str(produto)[:30])
                c.drawString(460, y, str(pagamento or "").replace("Upgrade - ", "")[:12])
                c.drawRightString(590, y, f"R$ {float(total):.2f}")
                y -= 16
                if y < 60:
                    c.showPage()
                    y = 780
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, f"Relatório de Upgrades - {data_alvo}")
                    y -= 20
                    c.setFont("Helvetica-Bold", 10)
                    c.drawString(40, y, "Hora")
                    c.drawString(100, y, "Cliente")
                    c.drawString(280, y, "Descrição")
                    c.drawString(460, y, "Pagto")
                    c.drawString(520, y, "Valor")
                    y -= 16
                    c.setFont("Helvetica", 10)
        y -= 24
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, f"Total de upgrades do dia: R$ {total_dia:.2f}")
        c.save()
        try:
            backup_pdf(nome_arquivo, "relatorios")
        except Exception:
            pass
        try:
            open_in_default_app(nome_arquivo)
        except Exception:
            pass
        bring_app_to_front()
        return nome_arquivo
    # Adiciona botão na aba Upgrade
    ttk.Button(top_hist_u, text="📄 Exportar PDF", style="Accent.TButton", command=lambda: gerar_relatorio_upgrades_dia_pdf()).pack(side="left", padx=6)
    @ui_safe('Upgrade')
    def carregar_upgrades():
        tree_upgrades.delete(*tree_upgrades.get_children())
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        cursor.execute("SELECT hora, cliente, produto, pagamento, total FROM vendas WHERE data=? AND pagamento LIKE 'Upgrade%' ORDER BY hora DESC", (hoje,))
        for hora, cliente, produto, pagamento, total in cursor.fetchall():
            tree_upgrades.insert("", "end", values=(hora, cliente, produto, (pagamento or "").replace("Upgrade - ", ""), f"R$ {total:.2f}"))
        apply_zebra(tree_upgrades)
    
    # ====== AGENDAMENTO (retirada de celulares) ======
    # UI: AGENDAMENTO
    ag_state = {"year": datetime.date.today().year, "month": datetime.date.today().month}

    # Cabeçalho com navegação
    ag_top = ttk.Frame(aba_agendamento, padding=8)
    ag_top.pack(fill="x")

    btn_prev = ttk.Button(ag_top, text="◀", width=4)
    btn_prev.pack(side="left", padx=(0, 6))

    lbl_mes = ttk.Label(ag_top, text="", font=("Segoe UI", 12, "bold"))
    lbl_mes.pack(side="left", padx=6)

    btn_next = ttk.Button(ag_top, text="▶", width=4)
    btn_next.pack(side="left", padx=6)

    def _go_today():
        ag_state["year"] = datetime.date.today().year
        ag_state["month"] = datetime.date.today().month
        refresh_agendamento_calendar()

    ttk.Button(ag_top, text="Hoje", style="Secondary.TButton", command=_go_today).pack(side="right", padx=6)

    # Grade do calendário
    ag_cal_frame = ttk.Frame(aba_agendamento, padding=(8, 4))
    ag_cal_frame.pack(fill="both", expand=True)

    # Linha com nomes dos dias (Seg a Dom)
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for i, d in enumerate(dias_semana):
        ttk.Label(ag_cal_frame, text=d, anchor="center", font=("Segoe UI", 10, "bold")).grid(row=0, column=i, sticky="nsew", padx=2, pady=(0, 4))
        ag_cal_frame.grid_columnconfigure(i, weight=1)

    # Container dos botões de dias
    ag_days_container = ttk.Frame(ag_cal_frame)
    ag_days_container.grid(row=1, column=0, columnspan=7, sticky="nsew")
    for i in range(7):
        ag_days_container.grid_columnconfigure(i, weight=1)

    # Lista (resumo) de agendamentos do mês
    ag_list_frame = ttk.Frame(aba_agendamento, padding=(8, 6))
    ag_list_frame.pack(fill="both", expand=False)

    ttk.Label(ag_list_frame, text="Agendamentos do mês", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=2, pady=(0, 6))

    ag_tree = ttk.Treeview(ag_list_frame, columns=("Data", "Responsável"), show="headings", height=6)
    configure_zebra_tags(ag_tree, current_theme["name"])
    ag_tree.heading("Data", text="Data")
    ag_tree.heading("Responsável", text="Responsável")
    ag_tree.column("Data", width=120, anchor="center", stretch=False)
    ag_tree.column("Responsável", width=900, anchor="w", stretch=True)
    ag_tree.pack(side="left", fill="both", expand=True)
    ag_scroll = ttk.Scrollbar(ag_list_frame, orient="vertical", command=ag_tree.yview)
    ag_tree.configure(yscroll=ag_scroll.set)
    ag_scroll.pack(side="right", fill="y")

    ag_scroll_x = ttk.Scrollbar(ag_list_frame, orient="horizontal", command=ag_tree.xview)
    ag_tree.configure(xscroll=ag_scroll_x.set)
    ag_scroll_x.pack(side="bottom", fill="x")

    def _ver_detalhes_agendamento(event=None):
        sel = ag_tree.selection()
        if not sel:
            return
        iso = sel[0]  # iid = data_iso
        try:
            cursor.execute("SELECT responsavel FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            r = cursor.fetchone()
            detalhes = (r[0] if r and r[0] else "(sem agendamentos)")
        except Exception as ex:
            detalhes = f"(erro ao carregar) {ex}"
        messagebox.showinfo(f"Agendamentos {_br_date_from_iso(iso)}", detalhes)

    ag_tree.bind("<Double-1>", _ver_detalhes_agendamento)
    def _mes_ano_pt(year: int, month: int) -> str:
        # Nomes em pt-BR
        nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        try:
            return f"{nomes[month-1]} {year}"
        except Exception:
            return f"{month:02d}/{year}"

    def _iso_date(year: int, month: int, day: int) -> str:
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _br_date_from_iso(iso: str) -> str:
        try:
            y, m, d = iso.split('-')
            return f"{d}/{m}/{y}"
        except Exception:
            return iso

    def _load_agendamentos_do_mes(year: int, month: int):
        # Retorna dict {dia: responsavel}
        resp = {}
        ym = f"{year:04d}-{month:02d}"
        try:
            cursor.execute("SELECT data_iso, responsavel FROM agendamentos_celulares WHERE substr(data_iso,1,7)=?", (ym,))
            for iso, r in cursor.fetchall():
                try:
                    dia = int(iso.split('-')[2])
                    resp[dia] = r or ""
                except Exception:
                    pass
        except Exception as ex:
            logging.error(f"Falha ao carregar agendamentos: {ex}", exc_info=True)
        return resp

    def _refresh_agendamento_lista(year: int, month: int):
        ag_tree.delete(*ag_tree.get_children())
        ym = f"{year:04d}-{month:02d}"
        try:
            cursor.execute("SELECT data_iso, responsavel FROM agendamentos_celulares WHERE substr(data_iso,1,7)=? ORDER BY data_iso", (ym,))
            for iso, r in cursor.fetchall():
                linhas = [l.strip() for l in (r or "").splitlines() if l.strip()]
                if not linhas:
                    resumo = ""
                elif len(linhas) == 1:
                    resumo = linhas[0]
                else:
                    resumo = f"{linhas[0]} (+{len(linhas)-1})"
                resumo = " ".join(resumo.split())
                MAX = 60
                if len(resumo) > MAX:
                    resumo = resumo[:MAX-3] + "..."
                ag_tree.insert("", "end", iid=str(iso), values=(_br_date_from_iso(iso), resumo))
            apply_zebra(ag_tree)
        except Exception as ex:
            logging.error(f"Falha ao atualizar lista de agendamentos: {ex}", exc_info=True)

    def _open_agendamento_dialog(day: int):
        year = ag_state["year"]
        month = ag_state["month"]
        iso = _iso_date(year, month, day)

        # Valor atual (se existir)
        atual = ""
        try:
            cursor.execute("SELECT responsavel FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            rr = cursor.fetchone()
            if rr and rr[0]:
                atual = rr[0]
        except Exception:
            pass

        # --- Janela multilinha (substitui simpledialog.askstring) ---
        win = tk.Toplevel(root)
        win.title("Agendamento - Retirada de Celulares")
        win.resizable(False, False)
        try:
            win.transient(root)
            win.grab_set()
        except Exception:
            pass

        # Centraliza
        try:
            win.update_idletasks()
            x = root.winfo_rootx() + (root.winfo_width() // 2) - 240
            y = root.winfo_rooty() + (root.winfo_height() // 2) - 170
            win.geometry(f"480x340+{x}+{y}")
        except Exception:
            win.geometry("480x340")

        info = (
            f"Pessoas que vão buscar em {_br_date_from_iso(iso)}:\n\n"
            "• Digite UM NOME por linha\n"
            "• Deixe em branco para remover o agendamento do dia\n"
        )
        ttk.Label(win, text=info, justify="left").pack(anchor="w", padx=12, pady=(12, 6))

        frm_text = ttk.Frame(win)
        frm_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        txt = tk.Text(frm_text, height=10, wrap="word")
        txt.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frm_text, orient="vertical", command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=sb.set)

        if atual:
            txt.insert("1.0", atual)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 12))

        def _salvar():
            texto_in = (txt.get("1.0", "end") or "").strip()
            nomes = [l.strip() for l in texto_in.splitlines() if l.strip()]
            texto = "\n".join(nomes)

            try:
                with conn:
                    if texto:
                        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        cursor.execute(
                            "INSERT INTO agendamentos_celulares(data_iso, responsavel, atualizado_em) VALUES (?,?,?) "
                            "ON CONFLICT(data_iso) DO UPDATE SET responsavel=excluded.responsavel, atualizado_em=excluded.atualizado_em",
                            (iso, texto, agora),
                        )
                    else:
                        cursor.execute("DELETE FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            except Exception as ex:
                logging.error(f"Falha ao salvar agendamento: {ex}", exc_info=True)
                messagebox.showerror("Erro", f"Não foi possível salvar o agendamento.\n{ex}", parent=win)
                return

            try:
                win.destroy()
            except Exception:
                pass

            refresh_agendamento_calendar()

        def _cancelar():
            try:
                win.destroy()
            except Exception:
                pass

        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=_cancelar).pack(side="right", padx=6)
        ttk.Button(btns, text="Salvar", style="Success.TButton", command=_salvar).pack(side="right", padx=6)

        win.bind("<Escape>", lambda e: _cancelar())
        win.bind("<Control-Return>", lambda e: _salvar())

        win.bind("<Return>", lambda e: "break")
        # Enter cria nova linha no Text e não aciona atalhos globais
        txt.bind('<Return>', lambda e: (txt.insert('insert', '\n'), 'break')[1])
        txt.focus_set()
    def refresh_agendamento_calendar():
        year = ag_state["year"]
        month = ag_state["month"]

        lbl_mes.config(text=_mes_ano_pt(year, month))

        # Limpa botões existentes
        for w in ag_days_container.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Carrega agendamentos do mês
        ag_map = _load_agendamentos_do_mes(year, month)

        cal = calendar.Calendar(firstweekday=0)  # 0=Segunda
        weeks = cal.monthdayscalendar(year, month)

        # Grid 6 linhas no máximo
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    # célula vazia
                    ttk.Label(ag_days_container, text="").grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
                    continue

                resp = ag_map.get(day, "")
                # Texto do botão: dia + indicador
                if resp:
                    qtd = len([l for l in str(resp).splitlines() if l.strip()])
                    txt = f"{day}\n✓{qtd}"
                    style_btn = "Accent.TButton"
                else:
                    txt = str(day)
                    style_btn = "TButton"

                b = ttk.Button(ag_days_container, text=txt, command=lambda d=day: _open_agendamento_dialog(d), style=style_btn)
                b.grid(row=r, column=c, sticky="nsew", padx=2, pady=2, ipadx=2, ipady=6)

        _refresh_agendamento_lista(year, month)

    def _change_month(delta: int):
        y = ag_state["year"]
        m = ag_state["month"] + delta
        if m < 1:
            m = 12
            y -= 1
        elif m > 12:
            m = 1
            y += 1
        ag_state["year"] = y
        ag_state["month"] = m
        refresh_agendamento_calendar()

    btn_prev.config(command=lambda: _change_month(-1))
    btn_next.config(command=lambda: _change_month(1))

    # Carrega ao iniciar
    refresh_agendamento_calendar()


    # Notifica no Telegram se houver agendamento para HOJE (ao abrir)
    start_agendamento_notify_on_open(root)
    start_devedores_notify_on_open(root)
# ====== ESTOQUE ======
    est_top = ttk.Frame(aba_estoque)
    est_top.pack(fill="both", expand=True)
    tree_frame = ttk.Frame(est_top)
    tree_frame.pack(fill="both", expand=True, pady=(0, 8))
    tree = ttk.Treeview(
        tree_frame,
        columns=("Código", "Nome", "Tipo", "Preço", "Qtd"),
        show="headings",
        selectmode="browse",
    )
    configure_zebra_tags(tree, current_theme["name"])
    tree.heading("Código", text="Código")
    tree.heading("Nome", text="Nome")
    tree.heading("Tipo", text="Tipo")
    tree.heading("Preço", text="Preço")
    tree.heading("Qtd", text="Qtd")
    tree.column("Código", width=120, anchor="center")
    tree.column("Nome", width=420, anchor="w")
    tree.column("Tipo", width=140, anchor="center")
    tree.column("Preço", width=120, anchor="e")
    tree.column("Qtd", width=80, anchor="center")
    tree.pack(side="left", fill="both", expand=True)
    scrollbar_est = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscroll=scrollbar_est.set)
    scrollbar_est.pack(side="right", fill="y")


    # ===== Legenda de cores do Estoque =====

    leg_frame = ttk.Frame(aba_estoque)

    leg_frame.pack(fill="x", pady=(2, 8))


    ttk.Label(leg_frame, text="Legenda:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(6, 10))


    def _leg_chip(parent, text, bg, fg):

        chip = tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 9, "bold"), padx=10, pady=4)

        chip.pack(side="left", padx=4)

        return chip


    _leg_chip(leg_frame, "ZERADO (0)", "#7f1d1d", "white")

    _leg_chip(leg_frame, "BAIXO (≤ 5)", "tomato", "black")

    _leg_chip(leg_frame, "MÉDIO (6–7)", "orange", "black")

    _leg_chip(leg_frame, "OK (≥ 8)", "lightgreen", "black")


    ttk.Label(leg_frame, text="• Ordenado por menor estoque", font=("Segoe UI", 9)).pack(side="right", padx=8)
    f_est = ttk.Frame(aba_estoque, padding=(6, 8))
    f_est.pack(fill="x", pady=6)
    def make_labeled_entry(parent, label_text, width=15):
        frm = ttk.Frame(parent)
        lbl = ttk.Label(frm, text=label_text)
        ent = ttk.Entry(frm, width=width)
        lbl.pack(side="top", anchor="w")
        ent.pack(side="top", fill="x")
        return frm, ent
    frm_codigo, ent_codigo = make_labeled_entry(f_est, "Código", 15)
    frm_codigo.pack(side="left", padx=6)
    frm_nome, ent_nome = make_labeled_entry(f_est, "Nome", 25)
    frm_nome.pack(side="left", padx=6)
    frm_tipo = ttk.Frame(f_est)
    ttk.Label(frm_tipo, text="Tipo").pack(side="top", anchor="w")
    ent_tipo = ttk.Combobox(frm_tipo, values=["Acessório", "Manutenção"], width=16)
    ent_tipo.pack(side="top", fill="x")
    frm_tipo.pack(side="left", padx=6)
    frm_custo, ent_custo = make_labeled_entry(f_est, "Custo", 10)
    frm_custo.pack(side="left", padx=6)
    frm_preco, ent_preco = make_labeled_entry(f_est, "Preço", 10)
    frm_preco.pack(side="left", padx=6)
    frm_qtd, ent_qtd = make_labeled_entry(f_est, "Qtd", 6)
    frm_qtd.pack(side="left", padx=6)
    ent_custo.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_custo))
    ent_preco.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_preco))
    def listar_estoque():
        tree.delete(*tree.get_children())
        
        # ===== Cores do estoque (SEM zebra) =====
        # 0 = zerado (vermelho escuro)
        tree.tag_configure("zerado", background="#7f1d1d", foreground="white")  # vermelho escuro
        # <= 5 = baixo (vermelho)
        tree.tag_configure("baixo", background="tomato", foreground="black")
        # 6..7 = médio (laranja)
        tree.tag_configure("laranja", background="orange", foreground="black")
        # >= 8 = ok (verde)
        tree.tag_configure("verde", background="lightgreen", foreground="black")
        
        # ===== Ordenação: menor estoque primeiro =====
        # Observação: COALESCE garante que NULL vire 0
        cursor.execute("""
            SELECT codigo, nome, tipo, preco, COALESCE(estoque,0) as estoque
            FROM produtos
            ORDER BY COALESCE(estoque,0) ASC, nome ASC
        """)
        
        for codigo, nome, tipo, preco, qtd in cursor.fetchall():
            if qtd == 0:
                tag = "zerado"
            elif qtd <= 5:
                tag = "baixo"
            elif 6 <= qtd <= 7:
                tag = "laranja"
            else:
                tag = "verde"
        

            try:
                cfg_tg = _load_telegram_config()
                if int(qtd) == 0:
                    telegram_notify(f"""⛔ <b>ESTOQUE ZERADO</b>
            📦 Produto: {nome}
            🔢 Qtd: {qtd}""", dedupe_key=f"stock_zero_{codigo}", dedupe_window_sec=int(cfg_tg.get('dedupe_zero_sec', 43200)))
                elif int(qtd) <= 5:
                    telegram_notify(f"""⚠️ <b>ESTOQUE BAIXO</b>
            📦 Produto: {nome}
            🔢 Qtd: {qtd}""", dedupe_key=f"stock_low_{codigo}", dedupe_window_sec=int(cfg_tg.get('dedupe_low_sec', 21600)))
            except Exception:
                pass
            tree.insert("", "end", values=(codigo, nome, tipo, f"R$ {float(preco):.2f}", int(qtd)), tags=(tag,))
        
        # NÃO aplicar zebra no estoque
        # apply_zebra(tree)
    listar_estoque()
    btn_frame_est = ttk.Frame(aba_estoque)
    btn_frame_est.pack(fill="x", pady=(6, 0))
    @ui_safe('Estoque')
    def cadastrar_produto():
        try:
            codigo = ent_codigo.get().strip()
            nome = ent_nome.get().strip()
            tipo = ent_tipo.get().strip()
            custo = float(ent_custo.get().replace("R$", "").replace(",", "."))
            preco = float(ent_preco.get().replace("R$", "").replace(",", "."))
            qtd = int(ent_qtd.get() or 0)
            if not codigo or not nome or not tipo:
                messagebox.showwarning("Atenção", "Preencha todos os campos")
                return
            with conn:
                cursor.execute(
                    "INSERT INTO produtos (codigo,nome,tipo,custo,preco,estoque) VALUES (?,?,?,?,?,?)",
                    (codigo, nome, tipo, custo, preco, qtd),
                )
            listar_estoque()
            messagebox.showinfo("OK", "Produto cadastrado!")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Código já existe!")
        except ValueError:
            messagebox.showerror("Erro", "Digite números válidos")
    @ui_safe('Estoque')
    def excluir_produto():
        if not is_admin(username):
            messagebox.showerror(
                "Permissão negada", "Somente o administrador pode excluir produtos."
            )
            return
        item = tree.selection()
        if not item:
            messagebox.showwarning("Atenção", "Selecione um produto para excluir")
            return
        codigo = tree.item(item)["values"][0]
        if messagebox.askyesno("Excluir Produto", f"Deseja excluir o código {codigo}?"):
            with conn:
                cursor.execute("DELETE FROM produtos WHERE codigo=?", (codigo,))
            listar_estoque()
    def carregar_produto_selecionado():
        item = tree.selection()
        if not item:
            messagebox.showwarning("Atenção", "Selecione um produto na lista")
            return None
        vals = tree.item(item)["values"]
        ent_codigo.config(state="normal")
        ent_codigo.delete(0, "end")
        ent_nome.delete(0, "end")
        ent_custo.delete(0, "end")
        ent_preco.delete(0, "end")
        ent_qtd.delete(0, "end")
        ent_tipo.set("")
        ent_codigo.insert(0, vals[0])
        ent_nome.insert(0, vals[1])
        ent_tipo.set(vals[2])
        ent_preco.insert(0, str(vals[3]).replace("R$", "").strip())
        ent_qtd.insert(0, vals[4])
        ent_codigo.config(state="readonly")
        cursor.execute("SELECT custo FROM produtos WHERE codigo=?", (vals[0],))
        r = cursor.fetchone()
        if r is not None:
            try:
                ent_custo.insert(0, f"{float(r[0]):.2f}")
            except Exception:
                ent_custo.insert(0, str(r[0]))
        return vals[0]
    @ui_safe('Estoque')
    def salvar_edicao_produto():
        codigo = ent_codigo.get().strip()
        if not codigo:
            messagebox.showwarning(
                "Atenção",
                "Nenhum produto carregado para edição. Clique em 'Editar (carregar)' primeiro.",
            )
            return
        try:
            nome = ent_nome.get().strip()
            tipo = ent_tipo.get().strip()
            custo = float(ent_custo.get().replace("R$", "").replace(",", ".") or 0)
            preco = float(ent_preco.get().replace("R$", "").replace(",", ".") or 0)
            qtd = int(ent_qtd.get() or 0)
            if not nome or not tipo:
                messagebox.showwarning("Atenção", "Preencha nome e tipo")
                return
            if not messagebox.askyesno(
                "Salvar Edição", f"Deseja salvar as alterações do produto {codigo}?"
            ):
                return
            with conn:
                cursor.execute(
                    """
                    UPDATE produtos
                    SET nome=?, tipo=?, custo=?, preco=?, estoque=?
                    WHERE codigo=?
                    """,
                    (nome, tipo, custo, preco, qtd, codigo),
                )
            listar_estoque()
            messagebox.showinfo("Sucesso", "Produto atualizado com sucesso!")
            ent_codigo.config(state="normal")
            ent_codigo.delete(0, "end")
        except ValueError:
            messagebox.showerror("Erro", "Valores inválidos")
    tree.bind("<Double-1>", lambda e: carregar_produto_selecionado())
    btn_cad_prod = ttk.Button(
        btn_frame_est, text="Cadastrar", command=cadastrar_produto
    )
    btn_edit_load_prod = ttk.Button(
        btn_frame_est, text="Editar (carregar)", command=carregar_produto_selecionado
    )
    btn_save_edit_prod = ttk.Button(
        btn_frame_est, text="Salvar Edição", command=salvar_edicao_produto
    )
    btn_del_prod = ttk.Button(btn_frame_est, text="✖ Excluir", style="Danger.TButton", command=excluir_produto)
    btn_cad_prod.pack(side="left", padx=6)
    btn_edit_load_prod.pack(side="left", padx=6)
    btn_save_edit_prod.pack(side="left", padx=6)
    btn_del_prod.pack(side="left", padx=6)
    if not is_admin(username):
        btn_del_prod.state(["disabled"])
    # ====== CLIENTES ======
    # -- TABELA --
    frame_cli = ttk.Frame(aba_clientes)
    frame_cli.pack(fill="both", expand=True, pady=8)
    tree_cli = ttk.Treeview(
        frame_cli, columns=("CPF", "Nome", "Telefone"), show="headings"
    )
    configure_zebra_tags(tree_cli, current_theme["name"])
    tree_cli.heading("CPF", text="CPF")
    tree_cli.heading("Nome", text="Nome")
    tree_cli.heading("Telefone", text="Telefone")
    tree_cli.column("CPF", width=160, anchor="center")
    tree_cli.column("Nome", width=320)
    tree_cli.column("Telefone", width=160, anchor="center")
    tree_cli.pack(side="left", fill="both", expand=True)
    scroll_cli = ttk.Scrollbar(frame_cli, orient="vertical", command=tree_cli.yview)
    tree_cli.configure(yscroll=scroll_cli.set)
    scroll_cli.pack(side="right", fill="y")
    # -- FORMULÁRIO --
    form_cli = ttk.Frame(aba_clientes, padding=8)
    form_cli.pack(fill="x")
    ttk.Label(form_cli, text="CPF").grid(row=0, column=0, padx=6)
    e_cpf = ttk.Entry(form_cli)
    e_cpf.grid(row=0, column=1, padx=6)
    ttk.Label(form_cli, text="Nome").grid(row=0, column=2, padx=6)
    e_nome = ttk.Entry(form_cli, width=30)
    e_nome.grid(row=0, column=3, padx=6)
    ttk.Label(form_cli, text="Telefone").grid(row=0, column=4, padx=6)
    e_tel = ttk.Entry(form_cli)
    e_tel.grid(row=0, column=5, padx=6)
    e_cpf.bind("<KeyRelease>", lambda e: formatar_cpf(e, e_cpf))
    e_tel.bind("<KeyRelease>", lambda e: formatar_telefone(e, e_tel))
    # Controle de edição: guarda o CPF original para permitir alteração do CPF (troca de chave)
    original_cpf = {"value": None}  # dict mutável para uso dentro das funções
    # -- FUNÇÕES --
    @ui_safe('Clientes')
    def carregar_clientes():
        tree_cli.delete(*tree_cli.get_children())
        for cpf, nome, tel in cursor.execute(
            "SELECT cpf, nome, telefone FROM clientes ORDER BY nome"
        ):
            tree_cli.insert("", "end", values=(cpf, nome, tel))
        apply_zebra(tree_cli)
    def salvar_cliente():
        """Salva cliente e permite troca de CPF (migração completa de referências)."""
        cpf = (e_cpf.get() or "").strip()
        nome = (e_nome.get() or "").strip()
        tel = (e_tel.get() or "").strip()
        if not cpf or not nome or not tel:
            messagebox.showwarning("Atenção", "Preencha todos os campos")
            return
        orig = original_cpf.get("value")
        with conn:
            if orig and orig != cpf:
                cursor.execute("SELECT 1 FROM clientes WHERE cpf=?", (cpf,))
                if cursor.fetchone():
                    messagebox.showerror("Erro", "Já existe um cliente cadastrado com este CPF.\nEscolha outro CPF.")
                    return
                # clientes (troca de chave)
                cursor.execute("DELETE FROM clientes WHERE cpf=?", (orig,))
                cursor.execute("INSERT OR REPLACE INTO clientes (cpf, nome, telefone) VALUES (?,?,?)", (cpf, nome, tel))
                # migração CPF nas tabelas relacionadas
                try:
                    cursor.execute("UPDATE vendas SET cpf=? WHERE cpf=?", (cpf, orig))
                except Exception:
                    pass
                try:
                    cursor.execute("UPDATE manutencao SET cpf=? WHERE cpf=?", (cpf, orig))
                except Exception:
                    pass
                try:
                    cursor.execute("UPDATE devedores SET cpf=? WHERE cpf=?", (cpf, orig))
                except Exception:
                    pass
                try:
                    cursor.execute("UPDATE resgates_pontos SET cpf=? WHERE cpf=?", (cpf, orig))
                except Exception:
                    pass
                # pontuacao (PK cpf) com merge
                try:
                    cursor.execute("SELECT COALESCE(pontos,0) FROM pontuacao WHERE cpf=?", (orig,))
                    old_row = cursor.fetchone()
                    old_pts = int((old_row[0] if old_row else 0) or 0)
                    cursor.execute("SELECT COALESCE(pontos,0) FROM pontuacao WHERE cpf=?", (cpf,))
                    new_row = cursor.fetchone()
                    new_pts = int((new_row[0] if new_row else 0) or 0)
                    if new_row is not None:
                        cursor.execute("UPDATE pontuacao SET pontos=? WHERE cpf=?", (old_pts + new_pts, cpf))
                        cursor.execute("DELETE FROM pontuacao WHERE cpf=?", (orig,))
                    else:
                        cursor.execute("UPDATE pontuacao SET cpf=? WHERE cpf=?", (cpf, orig))
                except Exception:
                    pass
            else:
                cursor.execute("INSERT OR REPLACE INTO clientes (cpf, nome, telefone) VALUES (?,?,?)", (cpf, nome, tel))
        carregar_clientes()
        # Limpa formulário após salvar
        try:
            e_cpf.config(state="normal")
        except Exception:
            pass
        e_cpf.delete(0, "end")
        e_nome.delete(0, "end")
        e_tel.delete(0, "end")
        original_cpf["value"] = None
        try:
            e_cpf.focus_set()
        except Exception:
            pass
    # -- BUSCA POR NOME (filtro incremental) --
    filtro_frame = ttk.Frame(aba_clientes, padding=8)
    filtro_frame.pack(fill="x")
    ttk.Label(filtro_frame, text="Buscar por nome").pack(side="left", padx=6)
    e_busca_nome = ttk.Entry(filtro_frame, width=30)
    e_busca_nome.pack(side="left")
    def carregar_clientes_filtrado(query: str = ""):
        tree_cli.delete(*tree_cli.get_children())
        q = (query or "").strip()
        if q:
            cursor.execute(
                "SELECT cpf, nome, telefone FROM clientes WHERE nome LIKE ? ORDER BY nome",
                (f"%{q}%",),
            )
        else:
            cursor.execute("SELECT cpf, nome, telefone FROM clientes ORDER BY nome")
        for cpf, nome, tel in cursor.fetchall():
            tree_cli.insert("", "end", values=(cpf, nome, tel))
        apply_zebra(tree_cli)
    def _on_busca_nome(_evt=None):
        carregar_clientes_filtrado(e_busca_nome.get())
    e_busca_nome.bind("<KeyRelease>", _on_busca_nome)
    e_busca_nome.bind("<Return>", _on_busca_nome)
    def carregar_para_edicao(event=None):
        item = tree_cli.selection()
        if not item:
            return
        cpf, nome, tel = tree_cli.item(item)["values"]
        e_cpf.delete(0, "end")
        e_nome.delete(0, "end")
        e_tel.delete(0, "end")
        e_cpf.insert(0, cpf)
        e_nome.insert(0, nome)
        e_tel.insert(0, tel)
        # CPF permanece editável; guardamos o CPF original para permitir alteração
        original_cpf["value"] = cpf
        try:
            e_cpf.config(state="normal")
        except Exception:
            pass
    tree_cli.bind("<Double-1>", carregar_para_edicao)
    ttk.Button(form_cli, text="Salvar Cliente", command=salvar_cliente).grid(
        row=1, column=1, pady=8
    )
    carregar_clientes()
    

    
# ====== DEVEDORES ======
    dev_top = ttk.Frame(aba_devedores)
    dev_top.pack(fill="both", expand=True)

    frm_dev = ttk.Frame(dev_top, padding=8)
    frm_dev.pack(fill="x", pady=6)

    ttk.Label(frm_dev, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_dev = ttk.Entry(frm_dev, width=18)
    ent_cpf_dev.grid(row=0, column=1, padx=6, pady=4, sticky="w")
    ent_cpf_dev.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_dev))

    ttk.Label(frm_dev, text="Nome (auto)").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_dev = ttk.Entry(frm_dev, width=34, state="readonly")
    ent_nome_dev.grid(row=0, column=3, padx=6, pady=4, sticky="w")

    ttk.Label(frm_dev, text="Data p/ pagar (dd/mm/aaaa)").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_data_dev = ttk.Entry(frm_dev, width=16)
    ent_data_dev.grid(row=0, column=5, padx=6, pady=4, sticky="w")

    def _calendar_popup_for(entry: ttk.Entry):
        """Popup simples de calendário (sem dependências externas)."""
        try:
            # Data inicial = valor do campo ou hoje
            raw = (entry.get() or "").strip()
            dmY = _parse_br_date_flex(raw)
            if dmY:
                d0, m0, y0 = dmY
                cur_year, cur_month = int(y0), int(m0)
            else:
                today = datetime.date.today()
                cur_year, cur_month = today.year, today.month

            win = tk.Toplevel(root)
            win.title("Escolher data")
            win.resizable(False, False)
            try:
                win.transient(root)
                win.grab_set()
            except Exception:
                pass

            header = ttk.Frame(win, padding=8)
            header.pack(fill="x")
            body = ttk.Frame(win, padding=(8, 0, 8, 8))
            body.pack(fill="both", expand=True)

            lbl = ttk.Label(header, text="", font=("Segoe UI", 10, "bold"))
            lbl.pack(side="left")

            state = {"y": cur_year, "m": cur_month}

            def _render():
                for w in body.winfo_children():
                    w.destroy()
                y = state["y"]; m = state["m"]
                meses_pt = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
                lbl.config(text=f"{meses_pt[m]} / {y}")
                # Cabeçalho dias
                days_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
                for c, name in enumerate(days_pt):
                    ttk.Label(body, text=name, width=4, anchor="center").grid(row=0, column=c, padx=2, pady=2)
                weeks = calendar.monthcalendar(y, m)
                for r, week in enumerate(weeks, start=1):
                    for c, day in enumerate(week):
                        if day == 0:
                            ttk.Label(body, text="", width=4).grid(row=r, column=c, padx=2, pady=2)
                        else:
                            def _pick(dd=day, mm=m, yy=y):
                                try:
                                    entry.delete(0, "end")
                                    entry.insert(0, f"{dd:02d}/{mm:02d}/{yy:04d}")
                                except Exception:
                                    pass
                                try:
                                    win.destroy()
                                except Exception:
                                    pass
                            ttk.Button(body, text=str(day), width=4, command=_pick).grid(row=r, column=c, padx=2, pady=2)

            def _prev():
                m = state["m"] - 1
                y = state["y"]
                if m < 1:
                    m = 12; y -= 1
                state["m"], state["y"] = m, y
                _render()

            def _next():
                m = state["m"] + 1
                y = state["y"]
                if m > 12:
                    m = 1; y += 1
                state["m"], state["y"] = m, y
                _render()

            ttk.Button(header, text="<", width=3, command=_prev).pack(side="right", padx=(0, 6))
            ttk.Button(header, text=">", width=3, command=_next).pack(side="right")

            _render()
        except Exception:
            pass

    def _on_click_data_dev(evt=None):
        _calendar_popup_for(ent_data_dev)
        return "break"

    ent_data_dev.bind("<Button-1>", _on_click_data_dev)

    ttk.Label(frm_dev, text="Valor (R$)").grid(row=0, column=6, sticky="w", padx=6, pady=4)
    var_valor_dev = tk.StringVar(value="R$ ")
    ent_valor_dev = ttk.Entry(frm_dev, width=12, textvariable=var_valor_dev)
    ent_valor_dev.grid(row=0, column=7, padx=6, pady=4, sticky="w")

    def _format_brl(v: float) -> str:
        try:
            v = float(v or 0.0)
        except Exception:
            v = 0.0
        s = f"{v:,.2f}"  # 1,234.56
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # 1.234,56
        return "R$ " + s

    def _ensure_prefix_valor_dev(evt=None):
        try:
            cur = var_valor_dev.get() or ""
            # Mantém prefixo R$
            if not cur.startswith("R$"):
                digits = re.sub(r"[^0-9,\.]", "", cur)
                var_valor_dev.set("R$ " + digits)
            elif cur == "R$":
                var_valor_dev.set("R$ ")
            ent_valor_dev.icursor("end")
        except Exception:
            pass

    def _format_valor_dev(evt=None):
        try:
            val = _parse_valor_br(var_valor_dev.get())
            if val > 0:
                var_valor_dev.set(_format_brl(val))
            else:
                _ensure_prefix_valor_dev()
        except Exception:
            pass

    ent_valor_dev.bind("<FocusIn>", _ensure_prefix_valor_dev)
    ent_valor_dev.bind("<KeyRelease>", _ensure_prefix_valor_dev)
    ent_valor_dev.bind("<FocusOut>", _format_valor_dev)

    def _cpf_digits(s: str) -> str:
        return re.sub(r"\D", "", str(s or ""))

    def _cpf_format(d: str) -> str:
        d = _cpf_digits(d)
        if len(d) != 11:
            return str(d)
        return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"

    def _get_cliente_nome_by_cpf(cpf_in: str) -> str:
        try:
            cpf_raw = (cpf_in or "").strip()
            d = _cpf_digits(cpf_raw)
            if len(d) != 11:
                return ""
            candidates = [cpf_raw, d, _cpf_format(d)]
            for c in candidates:
                if not c:
                    continue
                cursor.execute("SELECT nome FROM clientes WHERE cpf=?", (c,))
                r = cursor.fetchone()
                if r and (r[0] or "").strip():
                    return (r[0] or "").strip()
            # Fallback: compara só dígitos
            cursor.execute("SELECT cpf, nome FROM clientes")
            for c, n in (cursor.fetchall() or []):
                if _cpf_digits(c) == d and (n or "").strip():
                    return (n or "").strip()
        except Exception:
            return ""
        return ""

    def _buscar_nome_por_cpf_dev(evt=None):
        try:
            cpf_raw = (ent_cpf_dev.get() or "").strip()
            d = _cpf_digits(cpf_raw)
            # Só busca quando CPF estiver completo (11 dígitos)
            if len(d) != 11:
                nome = ""
            else:
                nome = _get_cliente_nome_by_cpf(cpf_raw)
            ent_nome_dev.config(state="normal")
            ent_nome_dev.delete(0, "end")
            ent_nome_dev.insert(0, nome)
            ent_nome_dev.config(state="readonly")
        except Exception:
            try:
                ent_nome_dev.config(state="readonly")
            except Exception:
                pass



    # Debounce para buscar nome automaticamente após digitar CPF
    _dev_after = {"id": None}

    def _on_cpf_dev_key(evt=None):
        # garante CPF formatado
        try:
            formatar_cpf(evt, ent_cpf_dev)
        except Exception:
            pass
        # cancela busca anterior enquanto o usuário digita
        try:
            if _dev_after.get("id"):
                ent_cpf_dev.after_cancel(_dev_after["id"])
        except Exception:
            pass
        # agenda nova busca
        _dev_after["id"] = ent_cpf_dev.after(180, _buscar_nome_por_cpf_dev)

    # substitui o bind de KeyRelease para buscar automaticamente
    ent_cpf_dev.bind("<KeyRelease>", _on_cpf_dev_key)
    ent_cpf_dev.bind("<FocusOut>", _buscar_nome_por_cpf_dev)
    ent_cpf_dev.bind("<Return>", _buscar_nome_por_cpf_dev)

    tree_dev_frame = ttk.Frame(dev_top)
    tree_dev_frame.pack(fill="both", expand=True, pady=(6, 8))

    tree_devedores = ttk.Treeview(
        tree_dev_frame,
        columns=("id", "cpf", "nome", "data", "valor", "status"),
        show="headings",
        height=14,
    )
    headers = {
        "id": ("ID", 60),
        "cpf": ("CPF", 120),
        "nome": ("NOME", 220),
        "data": ("DATA", 120),
        "valor": ("VALOR", 110),
        "status": ("STATUS", 110),
    }
    for col in ("id", "cpf", "nome", "data", "valor", "status"):
        tree_devedores.heading(col, text=headers[col][0])
        tree_devedores.column(col, width=headers[col][1], anchor="w")

    vsb_dev = ttk.Scrollbar(tree_dev_frame, orient="vertical", command=tree_devedores.yview)
    tree_devedores.configure(yscrollcommand=vsb_dev.set)
    tree_devedores.pack(side="left", fill="both", expand=True)
    vsb_dev.pack(side="right", fill="y")

    try:
        configure_zebra_tags(tree_devedores, 'dark')
    except Exception:
        pass

    def _parse_valor_br(s: str) -> float:
        s = (s or "").strip().replace("R$", "").replace(" ", "")
        if s.count(",") == 1 and s.count(".") >= 1:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def carregar_devedores():
        try:
            for iid in tree_devedores.get_children(""):
                tree_devedores.delete(iid)
            cursor.execute(
                """SELECT id, cpf, nome, data_pagamento, COALESCE(valor,0), COALESCE(pago,0)
                   FROM devedores
                   ORDER BY COALESCE(pago,0) ASC, date(data_iso) ASC, nome ASC"""
            )
            rows = cursor.fetchall() or []
            for (id_, cpf, nome, data_pag, valor, pago) in rows:
                status = "Pago" if int(pago or 0) == 1 else "Pendente"
                tree_devedores.insert(
                    "", "end",
                    values=(id_, cpf or "", nome or "", data_pag or "", f"R$ {float(valor or 0.0):.2f}", status)
                )
            try:
                apply_zebra(tree_devedores)
            except Exception:
                pass
        except Exception as ex:
            try:
                logging.error(f"Falha ao carregar devedores: {ex}", exc_info=True)
            except Exception:
                pass

    def _limpar_form_dev():
        ent_cpf_dev.delete(0, "end")
        ent_data_dev.delete(0, "end")
        ent_valor_dev.delete(0, "end")
        ent_nome_dev.config(state="normal")
        ent_nome_dev.delete(0, "end")
        ent_nome_dev.config(state="readonly")

    def salvar_devedor():
        cpf = (ent_cpf_dev.get() or "").strip()
        data_br = (ent_data_dev.get() or "").strip()
        valor = _parse_valor_br(ent_valor_dev.get())
        if not cpf:
            messagebox.showwarning("Atenção", "Informe o CPF.")
            return
        # Normaliza CPF e busca nome do cliente
        d = _cpf_digits(cpf)
        if len(d) == 11:
            cpf = _cpf_format(d)
        nome = _get_cliente_nome_by_cpf(cpf)
        if not nome:
            messagebox.showwarning("Atenção", "CPF não encontrado em Clientes. Cadastre o cliente primeiro.")
            return

        dmY = _parse_br_date_flex(data_br)
        if not dmY:
            messagebox.showwarning("Atenção", "Data inválida. Use dd/mm/aaaa.")
            return
        d, m, y = dmY
        try:
            data_iso = datetime.date(int(y), int(m), int(d)).strftime("%Y-%m-%d")
        except Exception:
            messagebox.showwarning("Atenção", "Data inválida.")
            return
        if valor <= 0:
            messagebox.showwarning("Atenção", "Informe um valor maior que zero.")
            return

        criado_em = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with conn:
            cursor.execute(
                """INSERT INTO devedores(cpf,nome,data_pagamento,data_iso,valor,pago,criado_em)
                   VALUES(?,?,?,?,?,0,?)""",
                (cpf, nome, f"{d:02d}/{m:02d}/{y:04d}", data_iso, float(valor), criado_em),
            )
        carregar_devedores()
        _limpar_form_dev()
        messagebox.showinfo("OK", "Devedor registrado com sucesso!")

    def marcar_pago():
        sel = tree_devedores.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um devedor na lista.")
            return
        vals = tree_devedores.item(sel[0], "values")
        if not vals:
            return
        id_ = vals[0]
        pago_em = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with conn:

            # Marca como pago e lança no Caixa (entrada)
            agora_dt = datetime.datetime.now()
            data_caixa = agora_dt.strftime("%d/%m/%Y")
            hora_caixa = agora_dt.strftime("%H:%M:%S")
            motivo_caixa = "Recebimento Devedor"

            # valor total do devedor (sempre)
            try:
                cursor.execute("SELECT COALESCE(valor,0) FROM devedores WHERE id=?", (id_,))
                valor_pago = float((cursor.fetchone() or [0])[0] or 0.0)
            except Exception:
                valor_pago = 0.0

            cursor.execute("UPDATE devedores SET pago=1, pago_em=? WHERE id=?", (pago_em, id_))
            cursor.execute(
                "INSERT INTO caixa(valor, data, hora, motivo) VALUES(?,?,?,?)",
                (float(valor_pago), data_caixa, hora_caixa, motivo_caixa),
            )
        carregar_devedores()
        messagebox.showinfo("OK", "Marcado como PAGO.")

    def excluir_devedor():
        sel = tree_devedores.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um devedor na lista.")
            return
        vals = tree_devedores.item(sel[0], "values")
        if not vals:
            return
        id_ = vals[0]
        if not messagebox.askyesno("Confirmar", "Excluir este registro de devedor?"):
            return
        with conn:
            cursor.execute("DELETE FROM devedores WHERE id=?", (id_,))
        carregar_devedores()

    def _on_tree_double_click(evt=None):
        sel = tree_devedores.selection()
        if not sel:
            return
        vals = tree_devedores.item(sel[0], "values")
        if not vals:
            return
        _limpar_form_dev()
        ent_cpf_dev.insert(0, vals[1])
        _buscar_nome_por_cpf_dev()
        ent_data_dev.insert(0, vals[3])
        ent_valor_dev.insert(0, str(vals[4]).replace('R$', '').strip())

    tree_devedores.bind("<Double-1>", _on_tree_double_click)

    btns_dev = ttk.Frame(dev_top)
    btns_dev.pack(fill="x", pady=(0, 8))
    ttk.Button(btns_dev, text="➕ Salvar", style="Success.TButton", command=salvar_devedor).pack(side="left", padx=6)
    ttk.Button(btns_dev, text="✅ Marcar Pago", style="Secondary.TButton", command=marcar_pago).pack(side="left", padx=6)
    ttk.Button(btns_dev, text="🗑 Excluir", style="Secondary.TButton", command=excluir_devedor).pack(side="left", padx=6)
    ttk.Button(btns_dev, text="🔄 Atualizar", style="Secondary.TButton", command=carregar_devedores).pack(side="right", padx=6)

    carregar_devedores()

# ====== PONTUAÇÃO ======
    pt_top = ttk.Frame(aba_pontuacao, padding=8)
    pt_top.pack(fill="x", pady=(0, 6))

    pt_info = ttk.Label(
        pt_top,
        text=f"Regras: 1 R$ = 1 ponto • Capa = {CUSTO_CAPA_PONTOS} pts • Película = {CUSTO_PELICULA_PONTOS} pts",
        font=("Segoe UI", 10, "bold"),
    )
    pt_info.pack(side="left", padx=6)

    btn_refresh_pts = ttk.Button(pt_top, text="⟳ Atualizar", style="Secondary.TButton")
    btn_refresh_pts.pack(side="right", padx=6)

    pt_filter = ttk.Frame(aba_pontuacao, padding=(8, 0))
    pt_filter.pack(fill="x", pady=(0, 6))

    ttk.Label(pt_filter, text="Buscar (CPF ou Nome)").pack(side="left", padx=6)
    ent_busca_pts = ttk.Entry(pt_filter, width=30)
    ent_busca_pts.pack(side="left", padx=6)

    pt_table_frame = ttk.Frame(aba_pontuacao, padding=(8, 0))
    pt_table_frame.pack(fill="both", expand=True)

    tree_pontos = ttk.Treeview(
        pt_table_frame,
        columns=("CPF", "Nome", "Pontos", "Último Resgate"),
        show="headings",
        height=12,
    )
    configure_zebra_tags(tree_pontos, current_theme["name"])
    for col, txt, anchor, width in [
        ("CPF", "CPF", "center", 160),
        ("Nome", "Nome", "w", 320),
        ("Pontos", "Pontos", "center", 100),
        ("Último Resgate", "Último Resgate", "w", 260),
    ]:
        tree_pontos.heading(col, text=txt)
        tree_pontos.column(col, width=width, anchor=anchor, stretch=(col in ("Nome", "Último Resgate")))

    tree_pontos.pack(side="left", fill="both", expand=True)
    pt_scroll = ttk.Scrollbar(pt_table_frame, orient="vertical", command=tree_pontos.yview)
    tree_pontos.configure(yscroll=pt_scroll.set)
    pt_scroll.pack(side="right", fill="y")

    pt_actions = ttk.Frame(aba_pontuacao, padding=8)
    pt_actions.pack(fill="x", pady=(6, 0))

    ttk.Label(pt_actions, text="Resgatar:").pack(side="left", padx=(6, 4))
    combo_resgate = ttk.Combobox(pt_actions, values=["Capa", "Película"], width=14, state="readonly")
    combo_resgate.set("Capa")
    combo_resgate.pack(side="left", padx=6)

    lbl_sel = ttk.Label(pt_actions, text="Cliente selecionado: (nenhum)")
    lbl_sel.pack(side="left", padx=10)

    lbl_saldo = ttk.Label(pt_actions, text="Saldo: 0 pts", font=("Segoe UI", 10, "bold"))
    lbl_saldo.pack(side="left", padx=10)

    btn_resgatar = ttk.Button(pt_actions, text="✓ Registrar Resgate", style="Success.TButton")
    btn_resgatar.pack(side="right", padx=6)


    def _ultimo_resgate_str(cpf: str) -> str:
        try:
            cursor.execute(
                "SELECT item, data, hora FROM resgates_pontos WHERE cpf=? ORDER BY id DESC LIMIT 1",
                (cpf,),
            )
            r = cursor.fetchone()
            if not r:
                return ""
            item, data, hora = r
            return f"{item} ({data} {hora})"
        except Exception:
            return ""


    @ui_safe('Pontuação')
    def carregar_pontuacao(query: str = ""):
        # Limpa a Treeview (robusto)
        for _iid in tree_pontos.get_children():
            tree_pontos.delete(_iid)
        q = (query or "").strip()
        if q:
            cursor.execute(
                """
                SELECT c.cpf, COALESCE(c.nome,''), COALESCE(p.pontos,0)
                FROM clientes c
                LEFT JOIN pontuacao p ON p.cpf=c.cpf
                WHERE c.cpf LIKE ? OR c.nome LIKE ?
                ORDER BY COALESCE(p.pontos,0) DESC, c.nome ASC
                """,
                (f"%{q}%", f"%{q}%"),
            )
        else:
            cursor.execute(
                """
                SELECT c.cpf, COALESCE(c.nome,''), COALESCE(p.pontos,0)
                FROM clientes c
                LEFT JOIN pontuacao p ON p.cpf=c.cpf
                ORDER BY COALESCE(p.pontos,0) DESC, c.nome ASC
                """
            )


        for cpf, nome, pontos in cursor.fetchall() or []:
            cpf_iid = str((cpf or "")).strip()
            last = _ultimo_resgate_str(cpf_iid)
            vals = (cpf_iid, nome, int(pontos or 0), last)
            # Proteção anti-colisão de iid: se já existir, apenas atualiza os valores
            if tree_pontos.exists(cpf_iid):
                tree_pontos.item(cpf_iid, values=vals)
            else:
                tree_pontos.insert("", "end", iid=cpf_iid, values=vals)
        apply_zebra(tree_pontos)


    def _on_busca_pts(_evt=None):
        carregar_pontuacao(ent_busca_pts.get())

    ent_busca_pts.bind("<KeyRelease>", _on_busca_pts)
    ent_busca_pts.bind("<Return>", _on_busca_pts)


    def _on_select_pts(_evt=None):
        sel = tree_pontos.selection()
        if not sel:
            lbl_sel.config(text="Cliente selecionado: (nenhum)")
            lbl_saldo.config(text="Saldo: 0 pts")
            return

        cpf = str(sel[0])
        try:
            cursor.execute("SELECT nome FROM clientes WHERE cpf=?", (cpf,))
            r = cursor.fetchone()
            nome = r[0] if r and r[0] else ""
        except Exception:
            nome = ""

        saldo = get_pontos_cliente(cpf)
        lbl_sel.config(text=f"Cliente selecionado: {nome} ({cpf})")
        lbl_saldo.config(text=f"Saldo: {saldo} pts")

    tree_pontos.bind("<<TreeviewSelect>>", _on_select_pts)


    def _do_resgatar():
        sel = tree_pontos.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um cliente na tabela de Pontuação.")
            return

        cpf = str(sel[0])
        item = combo_resgate.get().strip()
        ok, msg, _novo = registrar_resgate_pontos(cpf, item)

        if ok:
            messagebox.showinfo("Resgate", msg)
        else:
            messagebox.showwarning("Resgate", msg)

        carregar_pontuacao(ent_busca_pts.get())
        _on_select_pts()

    btn_resgatar.config(command=_do_resgatar)
    btn_refresh_pts.config(command=lambda: carregar_pontuacao(ent_busca_pts.get()))

    try:
        carregar_pontuacao()
    except Exception:
        pass
# ====== VENDAS ======
    f_v = ttk.Frame(aba_vendas, padding=8)
    f_v.pack(fill="x", pady=6)
    ttk.Label(f_v, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_v = ttk.Entry(f_v)
    ent_cpf_v.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_v.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_v))
    ent_cpf_v.bind("<FocusOut>", lambda e: formatar_cpf(e, ent_cpf_v))
    ttk.Label(f_v, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_v = ttk.Entry(f_v)
    ent_nome_v.grid(row=0, column=3, padx=6, pady=4)

    ttk.Label(f_v, text="E-mail").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_email_v = ttk.Entry(f_v, width=28)
    ent_email_v.grid(row=0, column=5, padx=6, pady=4)
    ttk.Label(f_v, text="Código Produto").grid(
        row=1, column=0, sticky="w", padx=6, pady=4
    )
    ent_cod_v = ttk.Entry(f_v)
    ent_cod_v.grid(row=1, column=1, padx=6, pady=4)
    ttk.Label(f_v, text="Produto").grid(row=1, column=2, sticky="w", padx=6, pady=4)
    ent_prod_v = ttk.Entry(f_v, state="readonly")
    ent_prod_v.grid(row=1, column=3, padx=6, pady=4)
    ttk.Label(f_v, text="Qtd").grid(row=2, column=0, sticky="w", padx=6, pady=4)
    ent_qtd_v = ttk.Entry(f_v)
    ent_qtd_v.grid(row=2, column=1, padx=6, pady=4)
    ttk.Label(f_v, text="Pagamento").grid(row=2, column=2, sticky="w", padx=6, pady=4)
    ent_pg_v = ttk.Combobox(f_v, values=["PIX", "Cartão", "Dinheiro"], width=14)
    ent_pg_v.grid(row=2, column=3, padx=6, pady=4)
    lbl_total_v = ttk.Label(f_v, text="Total: R$ 0.00", font=("Segoe UI", 12, "bold"))
    lbl_total_v.grid(row=3, column=0, columnspan=2, pady=10, sticky="w", padx=6)
    var_desc_5 = tk.IntVar()
    var_desc_10 = tk.IntVar()
    def atualizar_total(event=None):
        try:
            codigo = ent_cod_v.get().strip()
            qtd = int(ent_qtd_v.get() or 0)
            cursor.execute(
                "SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,)
            )
            r = cursor.fetchone()
            if r:
                nome_prod, preco, estoque = r
                total = preco * qtd
                if var_desc_5.get():
                    total *= 0.95
                elif var_desc_10.get():
                    total *= 0.90
                lbl_total_v.config(text=f"Total: R$ {total:.2f}")
            else:
                lbl_total_v.config(text="Total: R$ 0.00")
        except Exception:
            lbl_total_v.config(text="Total: R$ 0.00")
    ttk.Checkbutton(
        f_v,
        text="5%",
        variable=var_desc_5,
        command=lambda: [var_desc_10.set(0), atualizar_total()],
    ).grid(row=4, column=0, sticky="w", padx=6)
    ttk.Checkbutton(
        f_v,
        text="10%",
        variable=var_desc_10,
        command=lambda: [var_desc_5.set(0), atualizar_total()],
    ).grid(row=4, column=1, sticky="w", padx=6)

    var_enviar_email = tk.IntVar(value=1)
    chk_email = ttk.Checkbutton(
        f_v,
        text="Enviar cupom por e-mail",
        variable=var_enviar_email
    )
    chk_email.grid(row=4, column=2, columnspan=2, sticky="w", padx=6)
    add_tooltip(chk_email, "Se marcado, o sistema envia o cupom em PDF para o e-mail informado.")
    def buscar_cliente_v():
        cpf = ent_cpf_v.get().strip()
        cursor.execute("SELECT nome,telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_v.delete(0, "end")
            ent_nome_v.insert(0, r[0])
    ttk.Button(f_v, text="Buscar Cliente", command=buscar_cliente_v).grid(
        row=0, column=4, padx=6
    )
    def buscar_produto_v(event=None):
        codigo = ent_cod_v.get().strip()
        ent_prod_v.config(state="normal")
        ent_prod_v.delete(0, "end")
        cursor.execute("SELECT nome FROM produtos WHERE codigo=?", (codigo,))
        r = cursor.fetchone()
        if r:
            ent_prod_v.insert(0, r[0])
        else:
            ent_prod_v.insert(0, "Produto não encontrado")
        ent_prod_v.config(state="readonly")
        atualizar_total()
    ent_cod_v.bind("<KeyRelease>", buscar_produto_v)
    ent_cod_v.bind("<FocusOut>", buscar_produto_v)
    ent_qtd_v.bind("<KeyRelease>", atualizar_total)
    ent_qtd_v.bind("<FocusOut>", atualizar_total)
    @ui_safe('Vendas')
    def finalizar_venda():
        try:
            cpf = ent_cpf_v.get().strip()
            cliente = ent_nome_v.get().strip()
            codigo = ent_cod_v.get().strip()
            qtd = int(ent_qtd_v.get() or 0)
            pagamento = ent_pg_v.get().strip()
            if qtd <= 0:
                messagebox.showerror("Erro", "Quantidade inválida")
                return
            cursor.execute(
                "SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,)
            )
            r = cursor.fetchone()
            if not r:
                messagebox.showerror("Erro", "Produto não encontrado")
                return
            nome_prod, preco, estoque = r
            if qtd > estoque:
                messagebox.showerror("Erro", f"Apenas {estoque} unidades disponíveis")
                return
            total = preco * qtd
            if var_desc_5.get():
                total *= 0.95
            elif var_desc_10.get():
                total *= 0.90
            data = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            with conn:
                cursor.execute(
                    "INSERT INTO vendas(cliente,cpf,produto,quantidade,total,pagamento,data,hora) VALUES (?,?,?,?,?,?,?,?)",
                    (cliente, cpf, nome_prod, qtd, total, pagamento, data, hora),
                )

                # >>> NOVO: soma pontos do cliente (1 R$ = 1 ponto)
                cursor.execute(
                    "INSERT OR IGNORE INTO pontuacao(cpf,pontos,atualizado_em) VALUES(?,?,?)",
                    (cpf, 0, datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
                )
                adicionar_pontos_cliente(cpf, total)
                # <<< FIM NOVO: pontos
                cursor.execute(
                    "UPDATE produtos SET estoque=? WHERE codigo=?",
                    (estoque - qtd, codigo),
                )
                # >>> ATUALIZADO: grava hora na entrada do caixa (motivo NULL)
                # Motivo da entrada (Venda) — robusto para diferentes nomes de variáveis
                _prod = str(locals().get('produto') or locals().get('descricao') or locals().get('prod') or locals().get('produto_nome') or locals().get('nome_produto') or '').strip()
                _qtd = None
                for _k in ('qtd','quantidade','qtd_v','qtd_prod'):
                    if _k in locals() and locals().get(_k) not in (None,''):
                        _qtd = locals().get(_k)
                        break
                try:
                    _qtd = int(_qtd) if _qtd is not None else None
                except Exception:
                    _qtd = None
                _pg = ''
                for _k in ('pagamento','forma_pagamento','pg'):
                    if _k in locals() and str(locals().get(_k) or '').strip():
                        _pg = str(locals().get(_k) or '').strip()
                        break
                if not _pg:
                    try:
                        _pg = str(ent_pg_v.get() or '').strip()
                    except Exception:
                        _pg = ''
                _cli = str(locals().get('cliente') or locals().get('nome') or locals().get('nome_cliente') or '').strip()
                motivo_caixa = 'Venda'
                if _prod:
                    motivo_caixa += f" - {_prod}"
                if _qtd is not None:
                    motivo_caixa += f" x{_qtd}"
                if _pg:
                    motivo_caixa += f" ({_pg})"
                if _cli:
                    motivo_caixa += f" - {_cli}"
                motivo_caixa = (motivo_caixa or '').strip()[:90]
                try:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                        (total, data, hora, motivo_caixa),
                    )
                except Exception:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora) VALUES (?,?,?)",
                        (total, data, hora),
                    )
                cursor.execute(
                    "INSERT OR IGNORE INTO clientes(cpf,nome) VALUES (?,?)",
                    (cpf, cliente),
                )
            listar_estoque()
            # Atualiza a lista de vendas do dia automaticamente
            try:
                aba_vendas.after(30, carregar_vendas_dia)
            except Exception:
                pass

            # Gerar cupom e enviar por e-mail, se marcado
            try:
                caminho_pdf = gerar_cupom(cliente or "", nome_prod, qtd, pagamento or "", total, cpf=cpf)

                try:
                    telegram_notify(f"""✅ <b>VENDA REALIZADA</b>
                👤 Cliente: {cliente}
                📦 Produto: {nome_prod}
                🔢 Qtd: {qtd}
                💳 Forma de Pagamento: {pagamento}
                💰 Total: R$ {total:.2f}
                🕒 {data} {hora}""", dedupe_key=f"venda_{data}_{hora}_{codigo}", dedupe_window_sec=15)
                except Exception:
                    pass
                try:
                    telegram_send_pdf("🧾 Cupom da venda", caminho_pdf, dedupe_key=f"cupom_venda_{data}_{hora}_{codigo}", dedupe_window_sec=30)
                except Exception:
                    pass
                # valida o caminho do PDF antes de enviar
                if not caminho_pdf or not os.path.isfile(caminho_pdf):
                    try:
                        messagebox.showwarning("E-mail", "Cupom não foi gerado corretamente. O envio por e-mail foi pulado.")
                    except Exception:
                        pass
                    email_cliente = ""  # força pular envio
                # Captura e-mail e tenta enviar
                try:
                    email_cliente = ent_email_v.get().strip()
                except Exception:
                    email_cliente = ""
                if var_enviar_email.get() == 1 and email_cliente:
                    ok, detail = enviar_cupom_email(email_cliente, caminho_pdf)
                    if not ok:
                        try:
                            messagebox.showwarning("E-mail", f"Falha ao enviar e-mail:\n{detail}")
                        except Exception:
                            pass
            except Exception as e:
                logging.error(f"Falha ao gerar/enviar cupom: {e}", exc_info=True)
                try:
                    messagebox.showerror("Cupom/E-mail", "Erro: " + str(e))
                except Exception:
                    pass
        except Exception as ex:
            logging.error("Falha ao finalizar venda", exc_info=True)
            try:
                messagebox.showerror("Erro", f"Falha ao finalizar venda\n{ex}")
            except Exception:
                pass

    # --- Botões de ação da venda (recriados) ---
    acoes_venda = ttk.Frame(f_v)
    acoes_venda.grid(row=3, column=2, columnspan=4, padx=6, pady=8, sticky="e")

    btn_finalizar_venda = ttk.Button(
        acoes_venda,
        text="✓ Finalizar Venda",
        style="Success.TButton",
        command=finalizar_venda
    )
    btn_finalizar_venda.pack(side="left", padx=6)

    # (Opcional) Botão para limpar campos
    def limpar_venda():
        for w in (ent_cpf_v, ent_nome_v, ent_email_v, ent_cod_v, ent_prod_v, ent_qtd_v):
            try:
                w.config(state="normal")
                w.delete(0, "end")
            except Exception:
                pass
        ent_pg_v.set("")
        var_desc_5.set(0)
        var_desc_10.set(0)
        lbl_total_v.config(text="Total: R$ 0.00")
        try:
            ent_prod_v.config(state="readonly")
        except Exception:
            pass

    btn_limpar_venda = ttk.Button(
        acoes_venda,
        text="Limpar",
        style="Secondary.TButton",
        command=limpar_venda
    )
    btn_limpar_venda.pack(side="left", padx=6)

    # (Opcional) Atalho: Enter finaliza a venda
    # Atalho Enter (bind_all) removido para não interferir em campos multilinha (Agendamento)
    # Use Ctrl+Enter ou clique em '✓ Finalizar Venda'.
    hist_v_frame = ttk.Frame(aba_vendas, padding=(8, 0))
    hist_v_frame.pack(fill="both", expand=True)

    top_hist = ttk.Frame(hist_v_frame)
    top_hist.pack(fill="x", pady=(6, 6))

    lbl_hist = ttk.Label(top_hist, text="Vendas de Hoje", font=("Segoe UI", 11, "bold"))
    lbl_hist.pack(side="left", padx=6)

    ttk.Button(top_hist, text="Atualizar", command=lambda: carregar_vendas_dia()).pack(side="left", padx=6)
    ttk.Button(top_hist, text="📄 Exportar PDF", style="Accent.TButton", command=lambda: gerar_relatorio_vendas_dia_pdf()).pack(side="left", padx=6)

    # Botão: Excluir Venda (estorna do caixa)
    ttk.Button(top_hist, text="✖ Excluir Venda", style="Danger.TButton", command=lambda: excluir_venda()).pack(side="left", padx=6)

    combo_filtro_pg = ttk.Combobox(top_hist, values=["", "PIX", "Cartão", "Dinheiro"], width=16)
    combo_filtro_pg.pack(side="right", padx=6)
    combo_filtro_pg.set("")
    ttk.Label(top_hist, text="Filtrar por pagamento:").pack(side="right")

    tree_vendas_frame = ttk.Frame(hist_v_frame)
    tree_vendas_frame.pack(fill="both", expand=True)

    tree_vendas = ttk.Treeview(
        tree_vendas_frame,
        columns=("Hora", "Cliente", "Produto", "Qtd", "Pagamento", "Total"),
        show="headings",
        height=10,
    )

    for col, txt, anchor, width in [
        ("Hora", "Hora", "center", 120),
        ("Cliente", "Cliente", "w", 200),
        ("Produto", "Produto", "w", 240),
        ("Qtd", "Qtd", "center", 80),
        ("Pagamento", "Pagamento", "center", 120),
        ("Total", "Total", "e", 120),
    ]:
        tree_vendas.heading(col, text=txt)
        tree_vendas.column(col, width=width, anchor=anchor)

    tree_vendas.pack(side="left", fill="both", expand=True)
    scrollbar_vendas = ttk.Scrollbar(tree_vendas_frame, orient="vertical", command=tree_vendas.yview)
    tree_vendas.configure(yscroll=scrollbar_vendas.set)
    scrollbar_vendas.pack(side="right", fill="y")

    # >>> Ajuste de contraste nas tags de vendas
    tree_vendas.tag_configure("PIX", background="#e6ffed", foreground="black")
    tree_vendas.tag_configure("Cartão", background="#e6f0ff", foreground="black")
    tree_vendas.tag_configure("Dinheiro", background="#fff5e6", foreground="black")
    tree_vendas.tag_configure("default", background="white", foreground="black")

    @ui_safe('Vendas')
    def excluir_venda():
        """Exclui a venda selecionada na lista do dia e estorna o valor no caixa."""
        sel = tree_vendas.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma venda na lista para excluir.")
            return

        vid = sel[0]
        try:
            cursor.execute(
                "SELECT id, produto, quantidade, total, data, pagamento, cliente, hora FROM vendas WHERE id=?",
                (vid,),
            )
            r = cursor.fetchone()
            if not r:
                messagebox.showerror("Erro", "Venda não encontrada no banco de dados.")
                return

            _id, produto, qtd, total, data_v, pagamento, cliente_v, hora_v = r

            # Se o caixa do dia já foi fechado, bloquear para evitar inconsistência
            cursor.execute("SELECT total FROM fechamento_caixa WHERE data=?", (data_v,))
            if cursor.fetchone():
                messagebox.showwarning(
                    "Caixa já fechado",
                    f"O caixa do dia {data_v} já foi fechado.\n\nPara manter consistência, não é permitido excluir vendas após o fechamento.",
                )
                return

            msg = (
                "Deseja excluir esta venda?\n\n"
                f"ID: {_id}\n"
                f"Cliente: {cliente_v}\n"
                f"Produto: {produto}\n"
                f"Qtd: {qtd}\n"
                f"Pagamento: {pagamento}\n"
                f"Total: R$ {float(total):.2f}\n"
                f"Hora: {hora_v}"
            )

            if not messagebox.askyesno("Excluir Venda", msg):
                return

            hora_now = datetime.datetime.now().strftime("%H:%M:%S")

            with conn:
                # Remove a venda
                cursor.execute("DELETE FROM vendas WHERE id=?", (_id,))

                # Devolve estoque se for um produto cadastrado (por nome)
                try:
                    cursor.execute(
                        "UPDATE produtos SET estoque = COALESCE(estoque,0) + ? WHERE nome=?",
                        (int(qtd), str(produto)),
                    )
                except Exception:
                    pass

                # Estorna no caixa (lançamento negativo com motivo)
                try:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                        (-float(total), data_v, hora_now, f"Estorno - exclusão venda ID {_id}"),
                    )
                except Exception:
                    # Compatibilidade caso algum banco antigo não tenha motivo/hora
                    cursor.execute("INSERT INTO caixa(valor,data) VALUES (?,?)", (-float(total), data_v))

            # Atualiza telas
            try:
                listar_estoque()
            except Exception:
                pass
            try:
                carregar_vendas_dia()
            except Exception:
                pass
            try:
                atualizar_caixa()
            except Exception:
                pass

            messagebox.showinfo("OK", "Venda excluída e valor estornado do caixa.")

            try:
                telegram_notify(f"""❌ <b>VENDA EXCLUÍDA (ESTORNO)</b>
            🧾 ID: {_id}
            👤 Cliente: {cliente_v}
            📦 Produto: {produto}
            🔢 Qtd: {qtd}
            💰 Estorno: R$ {float(total):.2f}
            📅 Data: {data_v}
            🕒 Hora original: {hora_v}""", dedupe_key=f"estorno_{_id}", dedupe_window_sec=300)
            except Exception:
                pass

        except Exception as ex:
            logging.error("Falha ao excluir venda", exc_info=True)
            messagebox.showerror("Erro", f"Falha ao excluir venda\n{ex}")

    @ui_safe('Vendas')
    def carregar_vendas_dia():
        tree_vendas.delete(*tree_vendas.get_children())
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        filtro = (combo_filtro_pg.get() or "").strip()

        if filtro:
            cursor.execute(
                """
                SELECT id, hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=? AND pagamento=?
                ORDER BY hora DESC
                """,
                (hoje, filtro),
            )
        else:
            cursor.execute(
                """
                SELECT id, hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=?
                ORDER BY hora DESC
                """,
                (hoje,),
            )

        for vid, hora, cliente, produto, qtd, pagamento, total in cursor.fetchall():
            tag = pagamento if pagamento in ("PIX", "Cartão", "Dinheiro") else "default"
            tree_vendas.insert(
                "",
                "end",
                iid=str(vid),
                values=(hora, cliente, produto, qtd, pagamento, f"R$ {float(total):.2f}"),
                tags=(tag,),
            )

    combo_filtro_pg.bind("<<ComboboxSelected>>", lambda e: carregar_vendas_dia())

    # Carrega vendas ao abrir a aba
    try:
        carregar_vendas_dia()
    except Exception:
        pass

# ====== CAIXA ======
    f_cx = ttk.Frame(aba_caixa, padding=8)
    f_cx.pack(fill="both", expand=True)
    top_cx = ttk.Frame(f_cx)
    top_cx.pack(fill="x", pady=(0, 8))
    lbl_total_cx = ttk.Label(top_cx, text="", font=("Segoe UI", 12, "bold"))
    lbl_total_cx.pack(side="left", padx=6)


    # --- Totais do dia (Bruto / Saídas / Líquido) ---
    totais_dia_box = ttk.Frame(top_cx)
    totais_dia_box.pack(side="left", padx=(16, 0))

    # Placeholder para evitar alerta/erro de variável não definida (Pylance)
    lbl_os_aprov_dia_cx = None

    lbl_vendas_dia_cx = ttk.Label(totais_dia_box, text="Vendas: R$ 0,00", font=("Segoe UI", 10, "bold"))
    lbl_vendas_dia_cx.grid(row=0, column=0, sticky="w", padx=(0, 12))

    lbl_saidas_dia_cx = ttk.Label(totais_dia_box, text="Saídas: R$ 0,00", font=("Segoe UI", 10, "bold"))
    lbl_saidas_dia_cx.grid(row=0, column=1, sticky="w", padx=(0, 12))

    lbl_liquido_dia_cx = ttk.Label(totais_dia_box, text="Líquido: R$ 0,00", font=("Segoe UI", 10, "bold"))
    lbl_liquido_dia_cx.grid(row=0, column=2, sticky="w")

    # OS aprovadas (dia)
    lbl_os_aprov_dia_cx = ttk.Label(totais_dia_box, text="OS aprovadas: R$ 0,00", font=("Segoe UI", 10, "bold"))
    lbl_os_aprov_dia_cx.grid(row=0, column=3, sticky="w", padx=(12, 0))

    @ui_safe('Caixa')
    def atualizar_totais_ganho_dia_caixa():
        """Atualiza os 3 totais no topo da aba Caixa."""
        try:
            vendas_dia, saidas_dia, liquido_dia = calcular_totais_dia()
            fmt = _dash_fmt_brl if '_dash_fmt_brl' in globals() else (lambda v: f"R$ {float(v or 0):.2f}")
            lbl_vendas_dia_cx.config(text=f"Vendas: {fmt(vendas_dia)}")
            lbl_saidas_dia_cx.config(text=f"Saídas: {fmt(saidas_dia)}")
            lbl_liquido_dia_cx.config(text=f"Líquido: {fmt(liquido_dia)}")
            # OS aprovadas do dia (somente aprovadas)
            try:
                hoje = datetime.datetime.now().strftime("%d/%m/%Y")
                cursor.execute("SELECT COALESCE(SUM(valor),0), COUNT(1) FROM manutencao WHERE COALESCE(aprovado,0)=1 AND data=?", (hoje,))
                _sum_os, _cnt_os = cursor.fetchone() or (0, 0)
                _sum_os = float(_sum_os or 0.0)
                _cnt_os = int(_cnt_os or 0)
                try:
                    if lbl_os_aprov_dia_cx is not None:
                        lbl_os_aprov_dia_cx.config(text=f"OS aprovadas: {fmt(_sum_os)} ({_cnt_os})")
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    # Atualiza ao abrir a aba (primeira renderização)
    try:
        atualizar_totais_ganho_dia_caixa()
    except Exception:
        pass
    lbl_data_hora = ttk.Label(top_cx, text="", font=("Segoe UI", 10))
    lbl_data_hora.pack(side="right", padx=6)
    caixa_ops = ttk.Frame(f_cx)
    caixa_ops.pack(fill="x", pady=6)
    frm_saida = ttk.Frame(caixa_ops)
    frm_saida.pack(side="left", padx=6)
    ttk.Label(frm_saida, text="Saída de Caixa").pack(anchor="w")
    # Valor
    ent_saida_cx = ttk.Entry(frm_saida, width=20)
    ent_saida_cx.pack(anchor="w", pady=4)
    ent_saida_cx.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_saida_cx))
    # >>> NOVO: Motivo da saída
    ttk.Label(frm_saida, text="Motivo").pack(anchor="w")
    ent_motivo_cx = ttk.Entry(frm_saida, width=30)
    ent_motivo_cx.pack(anchor="w", pady=4)
    add_tooltip(ent_motivo_cx, "Explique rapidamente o motivo desta saída (ex.: motoboy, compra de insumos, troco, etc.)")

    # ------------ EMOJIS PARA SAÍDAS DE CAIXA ------------
    def _emoji_saida(motivo: str) -> str:
        """Retorna um emoji adequado para o motivo da saída."""
        if not motivo:
            return "💸"

        m = motivo.lower()

        if "uber" in m or "corrida" in m or "transporte" in m:
            return "🚗"
        if "lanche" in m or "comida" in m or "almoço" in m or "almoco" in m:
            return "🍔"
        if "motoboy" in m or "entrega" in m or "delivery" in m:
            return "🏍️"
        if "insumo" in m or "material" in m or "compra" in m:
            return "📦"
        if "troco" in m:
            return "💵"
        if "pagamento" in m or "pagar" in m or "boleto" in m:
            return "💲"
        if "manutenção" in m or "manutencao" in m or "conserto" in m or "reparo" in m:
            return "🛠️"

        return "💸"
    @ui_safe('Caixa')
    def registrar_saida_caixa():
        valor_text = ent_saida_cx.get().replace("R$", "").replace(",", ".").strip()
        motivo = ent_motivo_cx.get().strip()

        if not valor_text:
            messagebox.showwarning("Atenção", "Informe o valor da saída")
            return

        if not motivo:
            messagebox.showwarning("Atenção", "Informe o motivo da saída")
            return

        try:
            valor = float(valor_text)
            if valor <= 0:
                messagebox.showwarning(
                    "Atenção", "Informe um valor positivo para a saída"
                )
                return

            hoje = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")

            with conn:
                cursor.execute(
                    "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                    (-valor, hoje, hora, motivo),
                )

            ent_saida_cx.delete(0, "end")
            ent_motivo_cx.delete(0, "end")

            atualizar_caixa()

            messagebox.showinfo(
                "Saída", f"Saída de R$ {valor:.2f} registrada com sucesso"
            )

            # ----------- ENVIO TELEGRAM -----------
            try:
                emoji = _emoji_saida(motivo)
                telegram_notify(
                    f"""{emoji} <b>SAÍDA DE CAIXA REGISTRADA</b>
💸 Valor: R$ {valor:.2f}
📝 Motivo: {motivo}
🗓️ Data: {hoje}
⏰ Hora: {hora}""",
                    dedupe_key=f"saida_{hoje}_{hora}_{valor}",
                    dedupe_window_sec=30
                )
            except Exception:
                # Não quebra a UX se o Telegram falhar
                pass

        except ValueError:
            messagebox.showerror("Erro", "Valor inválido")
    # ====== RELATÓRIO MENSAL (último mês) — Caixa ======
    def _prev_month_year(_today=None):
        """Retorna (ano, mes) do mês anterior ao informado (ou ao dia de hoje)."""
        dt = _today or datetime.date.today()
        y, m = int(dt.year), int(dt.month) - 1
        if m <= 0:
            m = 12
            y -= 1
        return y, m

    @ui_safe('Caixa')
    def ver_relatorio_mensal_ultimo_mes(send_telegram: bool = True):
        """Gera e abre o relatório mensal do último mês e envia o PDF pelo Telegram (chat já configurado)."""
        try:
            y, m = _prev_month_year()

            # Gera o PDF (a função já abre o arquivo no visualizador do sistema)
            pdf_path = gerar_relatorio_vendas_mes_pdf(y, m)

            # Envio Telegram (opcional)
            if send_telegram:
                try:
                    agora_txt = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                    telegram_notify(
                        f"""\U0001F4CA <b>RELATÓRIO MENSAL</b>
\U0001F4C5 Mês: {m:02d}/{y:04d}
\U0001F552 Gerado em: {agora_txt}""",
                        dedupe_key=f"rel_mensal_msg_{y:04d}{m:02d}",
                        dedupe_window_sec=30,
                    )
                except Exception:
                    pass

                try:
                    telegram_send_pdf(
                        f"\U0001F4CA Relatório mensal {m:02d}/{y:04d}",
                        pdf_path,
                        dedupe_key=f"rel_mensal_pdf_{y:04d}{m:02d}",
                        dedupe_window_sec=120,
                    )
                except Exception:
                    pass

            messagebox.showinfo(
                'Relatório Mensal',
                f'Relatório mensal {m:02d}/{y:04d} gerado com sucesso!\n\nArquivo: {pdf_path}',
            )
            return pdf_path

        except Exception as ex:
            messagebox.showerror(
                'Erro',
                f'Falha ao gerar/enviar relatório mensal do último mês.\n\nDetalhes: {ex}',
            )
            return None

    ttk.Button(caixa_ops, text="Registrar Saída", command=registrar_saida_caixa).pack(
        side="left", padx=6, pady=10
    )
    ttk.Button(caixa_ops, text="🔒 Fechar Caixa", style="FecharCaixa.TButton", command=lambda: fechar_caixa()).pack(side="left", padx=6, pady=10)
    btn_rel_mensal = ttk.Button(
        caixa_ops,
        text="\U0001F4CA Relatório Mensal (último mês)",
        style="Accent.TButton",
        command=ver_relatorio_mensal_ultimo_mes,
    )
    btn_rel_mensal.pack(side="left", padx=6, pady=10)
    add_tooltip(btn_rel_mensal, "Gera o relatório do mês anterior e envia o PDF no Telegram (chat configurado).")

    ttk.Separator(f_cx, orient="horizontal").pack(fill="x", pady=6)
    tree_cx_frame = ttk.Frame(f_cx)
    tree_cx_frame.pack(fill="both", expand=True)
    tree_cx = ttk.Treeview(
        tree_cx_frame, columns=("Data", "Total"), show="headings", height=8
    )
    configure_zebra_tags(tree_cx, current_theme["name"])
    tree_cx.heading("Data", text="Data")
    tree_cx.heading("Total", text="Total Fechado")
    tree_cx.column("Data", width=200, anchor="center")
    tree_cx.column("Total", width=200, anchor="e")
    tree_cx.pack(side="left", fill="both", expand=True, padx=(0, 6))
    scrollbar_cx = ttk.Scrollbar(
        tree_cx_frame, orient="vertical", command=tree_cx.yview
    )
    tree_cx.configure(yscroll=scrollbar_cx.set)
    scrollbar_cx.pack(side="right", fill="y")
    @ui_safe('Caixa')
    def carregar_historico_cx():
        try:
            if not tree_cx.winfo_exists():
                return
            tree_cx.delete(*tree_cx.get_children())
            for row in cursor.execute(
                "SELECT data,total FROM fechamento_caixa ORDER BY data DESC"
            ):
                tree_cx.insert("", "end", values=(row[0], f"R$ {row[1]:.2f}"))
        except tk.TclError:
            return
        except Exception as ex:
            logging.error(f"Erro ao carregar histórico de caixa: {ex}", exc_info=True)
    def atualizar_caixa():
        agora = datetime.datetime.now()
        hoje = agora.strftime("%d/%m/%Y")

        # Atualiza os indicadores de ganho do dia (Vendas / Saídas / Líquido)
        try:
            atualizar_totais_ganho_dia_caixa()
        except Exception:
            pass
        # (Patch) Evita NameError/UnboundLocal para variáveis de PDF usadas no fechamento
        pdf_dia = None
        pdf_mes = None
        pdf_path = None
        cursor.execute("SELECT MAX(data) FROM caixa")
        ultima_data = cursor.fetchone()[0]
        if ultima_data and ultima_data != hoje:
            # Fecha automaticamente o dia anterior (gera relatório antes de limpar a tabela 'caixa')
            cursor.execute("SELECT COUNT(1) FROM caixa WHERE data=?", (ultima_data,))
            qtd_lanc = int((cursor.fetchone() or [0])[0] or 0)
            cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (ultima_data,))
            total_ultimo = cursor.fetchone()[0] or 0
            if qtd_lanc > 0:
                # 1) Registra fechamento
                with conn:
                    cursor.execute("INSERT OR REPLACE INTO fechamento_caixa (data,total) VALUES (?,?)", (ultima_data, total_ultimo))
                # 2) Gera relatório diário (silencioso) antes de apagar lançamentos
                pdf_dia = None
                try:
                    pdf_dia = gerar_relatorio_vendas_dia_pdf(data_str=ultima_data, abrir_pdf=False)
                except Exception as ex:
                    logging.error(f"Falha ao gerar relatório diário automático ({ultima_data}): {ex}", exc_info=True)
                # 2.1) Se for último dia do mês fechado, gera relatório mensal (silencioso)
                pdf_mes = None
                try:
                    dmY = _parse_br_date_flex(ultima_data)
                    if dmY:
                        d, mo, y = dmY
                        if d == calendar.monthrange(y, mo)[1]:
                            pdf_mes = gerar_relatorio_vendas_mes_pdf(y, mo, abrir_pdf=False)
                except Exception as ex:
                    logging.error(f"Falha ao gerar relatório mensal automático: {ex}", exc_info=True)
                # 3) Telegram (mensagem + PDFs)
                try:
                    telegram_notify(f"""🔒 <b>CAIXA FECHADO (AUTO)</b>
📅 Data: {ultima_data}
💰 Total do dia: R$ {float(total_ultimo)}:.2f
📄 Relatórios gerados ✅""", dedupe_key=f"auto_fech_{ultima_data}", dedupe_window_sec=120)
                except Exception:
                    pass
                try:
                    if pdf_dia:
                        telegram_send_pdf(f"📄 Relatório do dia {ultima_data}", pdf_dia, dedupe_key=f"auto_rel_dia_{ultima_data}", dedupe_window_sec=600)
                except Exception:
                    pass

            # 2.1) Se for o ÚLTIMO DIA do mês, gera também o relatório MENSAL (gráfico + ranking)
            pdf_mes = None
            try:
                now = datetime.datetime.now()
                last_day = calendar.monthrange(now.year, now.month)[1]
                if now.day == last_day:
                    pdf_mes = gerar_relatorio_vendas_mes_pdf(now.year, now.month)
            except Exception as ex:
                logging.error(f"Falha ao gerar relatório mensal: {ex}", exc_info=True)

            # Envia o relatório mensal (se gerado)
            try:
                if pdf_mes:
                    telegram_send_pdf(f"📊 Relatório mensal {hoje[-7:]}", pdf_mes, dedupe_key=f"rel_mes_{hoje[-7:]}", dedupe_window_sec=600)
            except Exception:
                pass

            # 3) Backups automáticos (banco, cupons, OS, relatórios)
            try:
                backup_banco()
                backup_bulk_dir(os.path.join(os.getcwd(), "cupons"), "cupons")
                backup_bulk_dir(os.path.join(os.getcwd(), "OS"), "OS")
                backup_bulk_dir(os.path.join(os.getcwd(), "relatorios"), "relatorios")
            except Exception:
                pass
            # 4) Somente agora apagamos os lançamentos do dia do caixa
            with conn:
                cursor.execute("DELETE FROM caixa WHERE data=?", (ultima_data,))
            pdf_path = pdf_path or pdf_dia or pdf_mes or "(sem relatório)"
            messagebox.showinfo(
                "Fechar Caixa",
                f"Caixa do dia {ultima_data} fechado com sucesso!\nRelatório gerado:\n{pdf_path}",
            )
            carregar_historico_cx()
            return

    @ui_safe('Caixa')
    def fechar_caixa():
        """Fecha o caixa do dia (manual) e gera relatório diário.
        Retorna o caminho do PDF (ou None)."""
        try:
            agora = datetime.datetime.now()
            hoje = agora.strftime("%d/%m/%Y")
            cursor.execute("SELECT COUNT(1) FROM caixa WHERE data=?", (hoje,))
            qtd = int((cursor.fetchone() or [0])[0] or 0)
            cursor.execute("SELECT COALESCE(SUM(valor),0) FROM caixa WHERE data=?", (hoje,))
            total_dia = float((cursor.fetchone() or [0])[0] or 0.0)
            if qtd <= 0:
                messagebox.showwarning("Fechar Caixa", f"Não há lançamentos para fechar no dia {hoje}.")
                return None
            if not messagebox.askyesno("Fechar Caixa", f"Deseja fechar o caixa do dia {hoje}?\n\nTotal do dia: R$ {total_dia:.2f}"):
                return None
            # 1) Registra fechamento
            with conn:
                cursor.execute("INSERT OR REPLACE INTO fechamento_caixa (data,total) VALUES (?,?)", (hoje, total_dia))
            # 2) Gera relatório diário
            pdf_path = None
            try:
                pdf_path = gerar_relatorio_vendas_dia_pdf(data_str=hoje, abrir_pdf=True)
            except Exception as ex:
                logging.error(f"Falha ao gerar relatório diário ({hoje}): {ex}", exc_info=True)
            # 2.1) Se for último dia do mês, tenta gerar também o mensal (best-effort)
            try:
                dmY = _parse_br_date_flex(hoje)
                if dmY:
                    d, mo, y = dmY
                    if d == calendar.monthrange(y, mo)[1]:
                        _ = gerar_relatorio_vendas_mes_pdf(y, mo, abrir_pdf=True)
            except Exception:
                pass
            # 3) Telegram / Backups (best-effort)
            try:
                telegram_notify(f"🔒 CAIXA FECHADO\nData: {hoje}\nTotal: R$ {total_dia:.2f}", dedupe_key=f"fech_{hoje}", dedupe_window_sec=120)
            except Exception:
                pass
            try:
                if pdf_path:
                    telegram_send_pdf(f"📄 Relatório do dia {hoje}", pdf_path, dedupe_key=f"rel_dia_{hoje}", dedupe_window_sec=600)
            except Exception:
                pass
            try:
                backup_banco()
                backup_bulk_dir(os.path.join(os.getcwd(), "cupons"), "cupons")
                backup_bulk_dir(os.path.join(os.getcwd(), "OS"), "OS")
                backup_bulk_dir(os.path.join(os.getcwd(), "relatorios"), "relatorios")
            except Exception:
                pass
            # 4) Limpa lançamentos do dia
            with conn:
                cursor.execute("DELETE FROM caixa WHERE data=?", (hoje,))
            messagebox.showinfo("Fechar Caixa", f"Caixa do dia {hoje} fechado com sucesso!\nRelatório gerado:\n{pdf_path or "(sem relatório)"}")
            try:
                carregar_historico_cx()
            except Exception:
                pass
            return pdf_path
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao fechar caixa.\n\nDetalhes: {ex}")
            return None

    # --- Rodapé da aba Caixa: mensagem no canto inferior direito (vermelho e negrito) ---
    try:
        footer_cx = ttk.Frame(aba_caixa)
        footer_cx.pack(side="bottom", fill="x")
        ttk.Label(
            footer_cx,
            text="Obrigado meu Deus 🙏🏼",
            style="Footer.TLabel",
            anchor="e",
            justify="right"
        ).pack(side="right", padx=8, pady=4)
    except Exception:
        pass
    # --- Fim do rodapé da aba Caixa ---

    # ====== MANUTENÇÃO ======
    f_m = ttk.Frame(aba_manutencao, padding=8)
    f_m.pack(fill="x", pady=6)
    ttk.Label(f_m, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_m = ttk.Entry(f_m)
    ent_cpf_m.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_m.bind("<KeyRelease>", partial(formatar_cpf, entry=ent_cpf_m))
    ttk.Label(f_m, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_m = ttk.Entry(f_m)
    ent_nome_m.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_m, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_m = ttk.Entry(f_m)
    ent_tel_m.grid(row=0, column=5, padx=6, pady=4)
    ttk.Label(f_m, text="Descrição").grid(row=1, column=0, sticky="w", padx=6, pady=6)
    ent_desc_m = ttk.Entry(f_m, width=70)
    ent_desc_m.grid(row=1, column=1, columnspan=5, pady=4, padx=6, sticky="we")
    ttk.Label(f_m, text="Valor").grid(row=1, column=6, sticky="w", padx=6, pady=6)
    ent_valor_m = ttk.Entry(f_m, width=18)
    ent_valor_m.grid(row=1, column=7, padx=6, pady=6)
    ent_valor_m.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_valor_m))
    tree_m_frame = ttk.Frame(aba_manutencao)
    tree_m_frame.pack(fill="both", expand=True, pady=8)
    tree_m = ttk.Treeview(
        tree_m_frame,
        columns=(
            "OS",
            "Nome",
            "CPF",
            "Telefone",
            "Descrição",
            "Data",
            "Valor",
            "Aprovado",
        ),
        show="headings",
    )
    configure_zebra_tags(tree_m, current_theme["name"])
    for c in tree_m["columns"]:
        tree_m.heading(c, text=c)
    tree_m.column("OS", width=80, anchor="center")
    tree_m.column("Nome", width=220, anchor="w")
    tree_m.column("CPF", width=140, anchor="center")
    tree_m.column("Telefone", width=140, anchor="center")
    tree_m.column("Descrição", width=360, anchor="w")
    tree_m.column("Data", width=120, anchor="center")
    tree_m.column("Valor", width=120, anchor="e")
    tree_m.column("Aprovado", width=100, anchor="center")
    tree_m.pack(side="left", fill="both", expand=True)
    scrollbar_m = ttk.Scrollbar(tree_m_frame, orient="vertical", command=tree_m.yview)
    tree_m.configure(yscroll=scrollbar_m.set)
    scrollbar_m.pack(side="right", fill="y")
    @ui_safe('Manutenção')
    def carregar_manutencao():
        tree_m.delete(*tree_m.get_children())
        for row in cursor.execute(
            "SELECT os, nome, cpf, telefone, descricao, data, COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao ORDER BY os DESC"
        ):
            aprovado_text = "Sim" if row[7] == 1 else "Não"
            tree_m.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    f"R$ {row[6]:.2f}",
                    aprovado_text,
                ),
            )
    carregar_manutencao()
    def buscar_cliente_m(event=None):
        try:
            cpf = ent_cpf_m.get().strip()
            cursor.execute("SELECT nome, telefone FROM clientes WHERE cpf=?", (cpf,))
            r = cursor.fetchone()
            if r:
                ent_nome_m.delete(0, "end")
                ent_nome_m.insert(0, str(r[0] or ""))
                ent_tel_m.delete(0, "end")
                ent_tel_m.insert(0, str(r[1] or ""))
        except Exception as ex:
            logging.error(f"Falha ao buscar cliente (OS): {ex}", exc_info=True)
    ttk.Button(f_m, text="Buscar Cliente", command=buscar_cliente_m).grid(
        row=0, column=6, padx=6
    )
    @ui_safe('Manutenção')
    def cadastrar_manutencao():
        cpf = ent_cpf_m.get().strip()
        nome = ent_nome_m.get().strip()
        if not nome:
            nome = "Sem Nome"
        telefone = ent_tel_m.get().strip()
        desc = ent_desc_m.get().strip()
        valor_text = ent_valor_m.get().replace("R$", "").replace(",", ".").strip()
        if not desc or not valor_text:
            messagebox.showwarning("Atenção", "Informe descrição e um valor válido")
            return
        try:
            valor = float(valor_text)
        except ValueError:
            messagebox.showerror("Erro", "Valor inválido")
            return
        data = datetime.datetime.now().strftime("%d/%m/%Y")
        with conn:
            cursor.execute(
                "INSERT INTO manutencao(cpf,nome,telefone,descricao,data,valor) VALUES (?,?,?,?,?,?)",
                (cpf, nome, telefone, desc, data, valor),
            )
        os_num = cursor.lastrowid
        gerar_os_pdf(os_num, nome, cpf, telefone, desc, valor)

        try:
            caminho_os_pdf = os.path.join(os.getcwd(), 'OS', f"OS_{os_num}.pdf")
            telegram_notify(f"""🧾 <b>NOVA OS REGISTRADA</b>
        🧾 OS Nº: {os_num}
        👤 Cliente: {nome}
        📞 Tel: {telefone}
        📝 Desc: {desc}
        💰 Valor: R$ {valor:.2f}
        📅 🕒 {data} {datetime.datetime.now().strftime("%H:%M:%S")}""", dedupe_key=f"os_nova_{os_num}", dedupe_window_sec=120)
            telegram_send_pdf(f"🧾 OS Nº {os_num}", caminho_os_pdf, dedupe_key=f"os_pdf_{os_num}", dedupe_window_sec=300)
        except Exception:
            pass
        carregar_manutencao()
        ent_cpf_m.delete(0, "end")
        ent_nome_m.config(state="normal")
        ent_nome_m.delete(0, "end")
        ent_nome_m.config(state="normal")
        ent_tel_m.config(state="normal")
        ent_tel_m.delete(0, "end")
        ent_tel_m.config(state="normal")
        ent_desc_m.delete(0, "end")
        ent_valor_m.delete(0, "end")
        messagebox.showinfo("OS", "Ordem de serviço registrada!")
    btn_reg_manut = ttk.Button(
        f_m, text="Registrar Manutenção", command=cadastrar_manutencao
    )
    btn_reg_manut.grid(row=2, column=0, columnspan=2, pady=8)
    @ui_safe('Manutenção')
    def excluir_manutencao():
        if not is_admin(username):
            messagebox.showerror(
                "Permissão negada", "Somente o administrador pode excluir manutenções."
            )
            return
        selected = tree_m.selection()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma OS para excluir.")
            return
        item_id = selected[0]
        os_num = tree_m.item(item_id)["values"][0]
        if messagebox.askyesno("Excluir OS", f"Deseja excluir a OS {os_num}?"):
            with conn:
                cursor.execute("DELETE FROM manutencao WHERE os=?", (os_num,))
            carregar_manutencao()
    btn_excluir_manut = ttk.Button(
        f_m, text="Excluir Manutenção", command=excluir_manutencao
    )
    btn_excluir_manut.grid(row=2, column=2, columnspan=2, pady=8)
    if not is_admin(username):
        btn_excluir_manut.state(["disabled"])
    @ui_safe('Manutenção')
    def aprovar_manutencao():
        selected = tree_m.selection()
        if not selected:
            messagebox.showwarning(
                "Atenção", "Selecione a OS que será aprovada na lista."
            )
            return
        item_id = selected[0]
        os_num = tree_m.item(item_id)["values"][0]
        cursor.execute(
            "SELECT COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao WHERE os=?",
            (os_num,), # sempre tupla
        )
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "OS não encontrada.")
            return
        valor, aprovado = r
        if aprovado == 1:
            messagebox.showinfo("Info", f"A OS {os_num} já foi aprovada.")

            try:
                telegram_notify(f"""🛠️ <b>OS APROVADA</b>
            🧾 OS Nº: {os_num}
            💰 Valor: R$ {valor:.2f}
            🕒 {hoje} {hora}""", dedupe_key=f"os_aprovada_{os_num}", dedupe_window_sec=300)
            except Exception:
                pass
            return
        if valor <= 0:
            messagebox.showwarning("Atenção", "Valor inválido para aprovar.")
            return
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with conn:
                # >>> ATUALIZADO: grava hora na entrada do caixa (motivo NULL)
                # Motivo da entrada (OS aprovada) — robusto
                _nome_os = str(locals().get('nome') or locals().get('cliente') or locals().get('nome_cliente') or '').strip()
                if not _nome_os:
                    try:
                        _nome_os = str(ent_nome_m.get() or '').strip()
                    except Exception:
                        _nome_os = ''
                motivo_caixa = f"OS {os_num} aprovada" + (f" - {_nome_os}" if _nome_os else "")
                motivo_caixa = (motivo_caixa or '').strip()[:90]
                try:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                        (valor, hoje, hora, motivo_caixa),
                    )
                except Exception:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora) VALUES (?,?,?)",
                        (valor, hoje, hora),
                    )
                cursor.execute(
                    "UPDATE manutencao SET aprovado=1 WHERE os=?", (os_num,)
                ) # vírgula aqui
            carregar_manutencao()
            atualizar_caixa()
            messagebox.showinfo(
                "Aprovado",
                f"OS {os_num} aprovada. R$ {valor:.2f} adicionados ao caixa.",
            )
        except Exception as ex:
            logging.error("Falha ao aprovar manutenção", exc_info=True)
            messagebox.showerror("Erro", f"Falha ao aprovar manutenção:\n{ex}")
    # Cria o botão APÓS definir a função
    btn_aprovar_manut = ttk.Button(
        f_m, text="Manutenção Aprovada", command=aprovar_manutencao
    )
    btn_aprovar_manut.grid(row=2, column=4, columnspan=2, pady=8)
    # ====== DEVOLUÇÃO ======
    f_d = ttk.Frame(aba_devolucao, padding=8)
    f_d.pack(fill="x", pady=6)
    ttk.Label(f_d, text="Quem devolve").grid(
        row=0, column=0, sticky="w", padx=6, pady=4
    )
    ent_nome_dev = ttk.Entry(f_d, width=30)
    ent_nome_dev.grid(row=0, column=1, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Qual a devolução").grid(
        row=0, column=2, sticky="w", padx=6, pady=4
    )
    ent_devolucao = ttk.Entry(f_d, width=40)
    ent_devolucao.grid(row=0, column=3, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Motivo da devolução").grid(
        row=1, column=0, sticky="w", padx=6, pady=4
    )
    ent_motivo_dev = ttk.Entry(f_d, width=80)
    ent_motivo_dev.grid(row=1, column=1, columnspan=3, padx=6, pady=4, sticky="we")
    hist_d_frame = ttk.Frame(aba_devolucao, padding=(8, 0))
    hist_d_frame.pack(fill="both", expand=True)
    top_hist_d = ttk.Frame(hist_d_frame)
    top_hist_d.pack(fill="x", pady=(6, 6))
    ttk.Label(
        top_hist_d, text="Histórico de Devoluções", font=("Segoe UI", 11, "bold")
    ).pack(side="left", padx=6)
    ttk.Button(
        top_hist_d, text="Atualizar", command=lambda: carregar_devolucoes()
    ).pack(side="left", padx=6)
    tree_dev_frame = ttk.Frame(hist_d_frame)
    tree_dev_frame.pack(fill="both", expand=True)
    tree_dev = ttk.Treeview(
        tree_dev_frame,
        columns=("Data", "Hora", "Nome", "Item", "Motivo"),
        show="headings",
        height=10,
    )
    configure_zebra_tags(tree_dev, current_theme["name"])
    for col, txt, anchor, width in [
        ("Data", "Data", "center", 120),
        ("Hora", "Hora", "center", 100),
        ("Nome", "Nome", "w", 180),
        ("Item", "Item", "w", 240),
        ("Motivo", "Motivo", "w", 320),
    ]:
        tree_dev.heading(col, text=txt)
        tree_dev.column(col, width=width, anchor=anchor)
    tree_dev.pack(side="left", fill="both", expand=True)
    scrollbar_dev = ttk.Scrollbar(
        tree_dev_frame, orient="vertical", command=tree_dev.yview
    )
    tree_dev.configure(yscroll=scrollbar_dev.set)
    scrollbar_dev.pack(side="right", fill="y")
    @ui_safe('Devolução')
    def carregar_devolucoes():
        tree_dev.delete(*tree_dev.get_children())
        cursor.execute(
            """
            SELECT data, hora, nome, item, motivo
            FROM devolucoes
            ORDER BY date(substr(data,7,4)
                         || '-'
                         || substr(data,4,2)
                         || '-'
                         || substr(data,1,2)) DESC, hora DESC
            """
        )
        for data, hora, nome, item, motivo in cursor.fetchall():
            tree_dev.insert("", "end", values=(data, hora, nome, item, motivo))
        apply_zebra(tree_dev)
    @ui_safe('Devolução')
    def registrar_devolucao():
        nome = ent_nome_dev.get().strip()
        item = ent_devolucao.get().strip()
        motivo = ent_motivo_dev.get().strip()
        if not nome or not item or not motivo:
            messagebox.showwarning(
                "Atenção", "Preencha nome, item e motivo da devolução"
            )
            return
        data = datetime.datetime.now().strftime("%d/%m/%Y")
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with conn:
                cursor.execute(
                    "INSERT INTO devolucoes(item,motivo,nome,data,hora) VALUES (?,?,?,?,?)",
                    (item, motivo, nome, data, hora),
                )
            messagebox.showinfo("Devolução", "Devolução registrada com sucesso!")

            try:
                telegram_notify(f"""↩️ <b>DEVOLUÇÃO</b>
            👤 Nome: {nome}
            📦 Item: {item}
            📝 Motivo: {motivo}
            🕒 {data} {hora}""", dedupe_key=f"devolucao_{data}_{hora}_{item}", dedupe_window_sec=60)
            except Exception:
                pass
            ent_nome_dev.delete(0, "end")
            ent_devolucao.delete(0, "end")
            ent_motivo_dev.delete(0, "end")
            carregar_devolucoes()
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao registrar devolução\n{ex}")
    ttk.Button(f_d, text="Registrar Devolução", command=registrar_devolucao).grid(
        row=2, column=0, pady=10, sticky="w", padx=6
    )
    carregar_devolucoes()
    # ---- Funções de UI: toast e agendador de backup ----
    def _show_toast_backup(text: str, level: str = 'info'):
        """Toast de backup (não interfere na lógica de backup)."""
        try:
            show_toast(root, text, level=level, duration_ms=3500, anchor='top-right', max_stack=4)
        except Exception:
            # Fallback minimalista (sem variáveis soltas bg/fg)
            try:
                messagebox.showinfo('Backup', text)
            except Exception:
                pass

    def _backup_timer_tick():
        """Executa os backups e reprograma o próximo disparo (30 min)."""
        try:
            backup_banco()
            backup_bulk_dir(os.path.join(os.getcwd(), "cupons"), "cupons")
            backup_bulk_dir(os.path.join(os.getcwd(), "OS"), "OS")
            backup_bulk_dir(os.path.join(os.getcwd(), "relatorios"), "relatorios")
            try:
                ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                lbl_status_backup.config(text=f"Backup automático concluído: {ts}")
                _show_toast_backup("Backup automático concluído", "ok")
            except Exception:
                pass
        except Exception:
            pass
        finally:
            root.after(1_800_000, _backup_timer_tick)
    # Disparo inicial: 5 min; depois agenda de 30 min
    root.after(300_000, _backup_timer_tick)
    # Atualiza os totais do caixa ao abrir a janela
    try:
        atualizar_caixa()
    except Exception:
        pass

    # ====== STATUS BAR (versão | backup | usuário | data/hora) ======
    statusbar = tk.Frame(root, bg=palette['panel'], highlightbackground=palette['border'], highlightthickness=1)
    statusbar.pack(side='bottom', fill='x', pady=(0, 4))

    lbl_status_left = tk.Label(statusbar, text=f"v{get_local_version()}", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_left.pack(side='left', padx=10, pady=6)

    lbl_status_backup = tk.Label(statusbar, text="Backup: aguardando...", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_backup.pack(side='left', padx=10, pady=6)

    lbl_status_user = tk.Label(statusbar, text=f"Usuário: {username}", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_user.pack(side='right', padx=10, pady=6)

    # --- Licença (tempo restante) na Status Bar ---
    lbl_status_licenca = tk.Label(statusbar, text=get_tempo_restante_licenca_str(), bg=palette['panel'], fg=palette['muted'], font=('Segoe UI', 9))
    lbl_status_licenca.pack(side='left', padx=10, pady=6)
    try:
        bind_licenca_statusbar_auto_update(root, lbl_status_licenca, interval_ms=60000)
    except Exception:
        pass

    lbl_status_clock = tk.Label(statusbar, text="", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_clock.pack(side='right', padx=10, pady=6)

    def _tick_clock():
        try:
            now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            lbl_status_clock.config(text=now)
        except Exception:
            pass
        root.after(1000, _tick_clock)

    _tick_clock()

    def _refresh_statusbar_theme():
        try:
            pal = THEME_DARK if current_theme['name'] == 'dark' else THEME_LIGHT
            statusbar.configure(bg=pal['panel'], highlightbackground=pal['border'])
            for w in (lbl_status_left, lbl_status_backup, lbl_status_user, lbl_status_clock):
                w.configure(bg=pal['panel'], fg=pal['muted'])
        except Exception:
            pass
# ================= TELA DE LOGIN =================

def abrir_login():
    login_win = tk.Tk()
    login_win.title("Login - BESIM COMPANY")
    login_win.geometry("520x360")
    login_win.minsize(520, 360)
    login_win.resizable(False, False)

    setup_global_exception_handlers(login_win)
    _bind_fullscreen_shortcuts(login_win)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Dark fixo
    pal = THEME_DARK

    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _draw_vertical_gradient(canvas, w, h, top="#0b1220", bottom="#111827", steps=220):
        c1 = _hex_to_rgb(top)
        c2 = _hex_to_rgb(bottom)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            y1 = int(h * (i / steps))
            y2 = int(h * ((i + 1) / steps))
            canvas.create_rectangle(0, y1, w, y2, outline="", fill=_rgb_to_hex((r, g, b)))

    bg = tk.Canvas(login_win, highlightthickness=0, bd=0)
    bg.pack(fill="both", expand=True)

    login_win.update_idletasks()
    _draw_vertical_gradient(bg, 520, 360, top="#0b1220", bottom="#111827")

    # Blobs (bolas) — azul, vermelho e cinza (reposicionadas para não tampar o logo)
    bg.create_oval(-140, -120, 180, 220, fill=pal["accent"], outline="")   # azul
    bg.create_oval(360, -140, 700, 220, fill=pal["danger"], outline="")    # vermelho
    bg.create_oval(360, 210, 740, 610, fill=pal["border"], outline="")     # cinza

    # Camada escura para suavizar o fundo (não afeta o card porque ele é desenhado depois)
    bg.create_rectangle(0, 0, 520, 360, fill="#0b1220", outline="", stipple="gray25")

    # Card central
    card_x1, card_y1, card_x2, card_y2 = 110, 62, 410, 298
    bg.create_rectangle(card_x1 + 6, card_y1 + 8, card_x2 + 6, card_y2 + 8,
                        fill="#000000", outline="", stipple="gray50")
    bg.create_rectangle(card_x1, card_y1, card_x2, card_y2,
                        fill=pal["panel"], outline=pal["border"], width=2)
    bg.create_rectangle(card_x1, card_y1, card_x2, card_y1 + 58,
                        fill=pal["panel2"], outline="", width=0)

    # Logo + glow atrás (garantido atrás do logo)
    logo_path = str(P('logo.png'))
    cx, cy = (card_x1 + card_x2)//2, card_y1 + 30

    # Glow (desenhado antes do logo)
    bg.create_oval(cx-92, cy-32, cx+92, cy+32, fill=pal["accent"], outline="")
    bg.create_oval(cx-74, cy-26, cx+74, cy+26, fill=pal["danger"], outline="")
    bg.create_rectangle(cx-118, cy-40, cx+118, cy+40, fill="#000000", outline="", stipple="gray50")

    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((160, 52))
            logo_img = ImageTk.PhotoImage(img)
            bg.create_image(cx, cy, image=logo_img)
            bg.logo_img = logo_img
        except Exception:
            bg.create_text(cx, cy, text="BESIM COMPANY", fill=pal["text"], font=("Segoe UI", 14, "bold"))
    else:
        bg.create_text(cx, cy, text="BESIM COMPANY", fill=pal["text"], font=("Segoe UI", 14, "bold"))

    bg.create_text((card_x1 + card_x2)//2, card_y1 + 72,
                   text="Acesse sua conta para continuar",
                   fill=pal["muted"], font=("Segoe UI", 9))

    frm = tk.Frame(login_win, bg=pal["panel"])
    bg.create_window((card_x1 + card_x2)//2, (card_y1 + card_y2)//2 + 18, window=frm, width=280, height=210)

    style.configure("Accent.TButton", foreground="white", background=pal["accent"], padding=8,
                    font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])

    style.configure("Ghost.TButton", foreground=pal["text"], background=pal["panel2"], padding=8,
                    font=("Segoe UI", 10, "bold"))
    style.map("Ghost.TButton", background=[("active", pal["border"]), ("pressed", pal["panel2"])])

    style.configure("TEntry", padding=6)

    remember_path = os.path.join(os.getcwd(), "remember_user.txt")

    def _load_remembered_user():
        try:
            if os.path.isfile(remember_path):
                with open(remember_path, "r", encoding="utf-8") as f:
                    return (f.read() or "").strip()
        except Exception:
            pass
        return ""

    def _save_remembered_user(username: str):
        try:
            with open(remember_path, "w", encoding="utf-8") as f:
                f.write((username or "").strip())
        except Exception:
            pass

    def _clear_remembered_user():
        try:
            if os.path.isfile(remember_path):
                os.remove(remember_path)
        except Exception:
            pass

    tk.Label(frm, text="Usuário", bg=pal["panel"], fg=pal["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
    ent_user = ttk.Entry(frm)
    ent_user.pack(fill="x", pady=(0, 8))

    tk.Label(frm, text="Senha", bg=pal["panel"], fg=pal["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 2))
    pass_row = tk.Frame(frm, bg=pal["panel"])
    pass_row.pack(fill="x", pady=(0, 4))

    ent_pass = ttk.Entry(pass_row, show="*")
    ent_pass.pack(side="left", fill="x", expand=True)

    show_var = tk.IntVar(value=0)

    def _toggle_pass():
        ent_pass.config(show="" if show_var.get() else "*")

    ttk.Checkbutton(pass_row, text="👁️", variable=show_var, command=_toggle_pass).pack(side="left", padx=(6, 0))

    remember_var = tk.IntVar(value=1)
    remember_row = tk.Frame(frm, bg=pal["panel"])
    remember_row.pack(fill="x", pady=(6, 8))
    ttk.Checkbutton(remember_row, text="Lembrar usuário", variable=remember_var).pack(side="left")

    login_win.ent_user = ent_user
    login_win.ent_pass = ent_pass

    remembered = _load_remembered_user()
    if remembered:
        ent_user.insert(0, remembered)
        ent_pass.focus_set()
    else:
        ent_user.focus_set()

    def tentar_login():
        user = (ent_user.get() or "").strip()
        pw = (ent_pass.get() or "").strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha")
            return

        cursor.execute("SELECT password_hash, COALESCE(force_password_change,0), COALESCE(password_last_changed,'') FROM users WHERE username=?", (user,))
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "Usuário não encontrado")
            return

        if hash_password(pw) == r[0]:
            if remember_var.get() == 1:
                _save_remembered_user(user)
            else:
                _clear_remembered_user()

            must_change = False
            try:
                force_first = int(r[1] or 0) == 1
                last_changed = (r[2] or '').strip()
                if force_first or (not last_changed):
                    must_change = True
            except Exception:
                must_change = True

            try:
                if is_admin(user) and days_since_last_change(user) >= 30:
                    must_change = True
            except Exception:
                must_change = True

            if must_change:
                dlg = ChangePasswordDialog(login_win, user, must_change=True)
                login_win.wait_window(dlg)
                if not dlg.result:
                    return

            login_win.withdraw()
            try:
                abrir_sistema_com_logo(user, login_win)
            except Exception as ex:
                messagebox.showerror("Erro fatal", f"Falha ao abrir a janela principal\n\n{ex}")
                login_win.deiconify()
        else:
            messagebox.showerror("Erro", "Senha incorreta")

    def criar_usuario():
        user = (ent_user.get() or "").strip()
        pw = (ent_pass.get() or "").strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha para criar")
            return
        try:
            today = datetime.datetime.now().strftime("%d/%m/%Y")
            with conn:
                cursor.execute("PRAGMA table_info(users)")
                cols = [c[1] for c in cursor.fetchall()]
                if 'password_last_changed' in cols:
                    cursor.execute(
                        "INSERT INTO users(username, password_hash, is_admin, password_last_changed) VALUES (?,?,0,?)",
                        (user, hash_password(pw), today)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO users(username, password_hash, is_admin) VALUES (?,?,0)",
                        (user, hash_password(pw))
                    )
                cursor.execute(
                    "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                    (user, hash_password(pw), today)
                )
            messagebox.showinfo("OK", "Usuário criado com sucesso")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Usuário já existe")

    btns = tk.Frame(frm, bg=pal["panel"])
    btns.pack(fill="x", pady=(6, 0))
    ttk.Button(btns, text="Entrar", style="Accent.TButton", command=tentar_login).pack(side="left", expand=True, fill="x", padx=(0, 6))
# [REMOVIDO LOGIN] # [REMOVIDO LOGIN]     ttk.Button(btns, text="Criar Usuário", style="Ghost.TButton", command=criar_usuario).pack(side="left", expand=True, fill="x")

    footer_text = f"Developed by André Mariano (v{get_local_version()})  •  Beta Test"
    bg.create_text(260, 334, text=footer_text, fill="#9ca3af", font=("Segoe UI", 9))

    login_win.bind("<Return>", lambda e: tentar_login())

    def on_close_login():
        if messagebox.askyesno("Sair", "Deseja encerrar o sistema?"):
            try:
                show_goodbye_screen(login_win, "Até Logo,\nBom descanso", duration_ms=1500)
            except Exception:
                pass

            def _finalizar_saida():
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    login_win.destroy()
                except Exception:
                    pass

            login_win.after(1600, _finalizar_saida)
            return
        return

    login_win.protocol("WM_DELETE_WINDOW", on_close_login)
    login_win.bind("<Escape>", lambda e: on_close_login())

    login_win.mainloop()

# ===================== MAIN =====================
if __name__ == "__main__":
    try:
        # >>> NOVO: Bloqueio por licença (30 dias)
        if not mostrar_dialogo_licenca():
            try: sys.exit(0)
            except Exception: os._exit(0)

        abrir_login()
    except Exception:
        logging.error("Erro ao iniciar a aplicação", exc_info=True)
        try:
            messagebox.showerror(
                "Erro", "Falha ao iniciar a aplicação. Consulte o arquivo de logs."
            )
        except Exception:
            pass
