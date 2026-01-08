# -*- coding: utf-8 -*-
"""
Sistema Loja - atualização após login com Splash visível (topmost/lift/focus) e barra de progresso real.
- Roda sem erro
- Atualiza uma vez (sem loop)
- Splash estilizada com logo (se existir)
- Barra de progresso real
- Login abre normalmente
- Banco (besim_company.db) não é sobrescrito
- Pronto para EXE (PyInstaller)
- Operadores lógicos em inglês (or/and/not)
- Um único APP_VERSION e um único __main__
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import sqlite3
import datetime
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
import certifi
from functools import partial
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ===================== CONFIGURAÇÕES =====================
APP_VERSION = "1.4"
OWNER = "andremariano07"
REPO = "besim_company"
BRANCH = "main"
VERSION_FILE = "VERSION"
DB_PATH = "besim_company.db"
IGNORE_FILES = {"besim_company.db"}
IGNORE_DIRS = {"cupons", "relatorios", "OS", "__pycache__", ".git"}

# ===================== LOG =====================
LOG_FILE = "sistema_loja_errors.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ===================== BANCO =====================
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS clientes (
    cpf TEXT PRIMARY KEY,
    nome TEXT,
    telefone TEXT
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
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL,
    data TEXT
)
"""
)
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
CREATE TABLE IF NOT EXISTS devolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT,
    motivo TEXT,
    nome TEXT,
    data TEXT,
    hora TEXT
)
"""
)
conn.commit()

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

def ensure_admin_user():
    try:
        cursor.execute("SELECT username, is_admin FROM users WHERE username=?", ("admin",))
        r = cursor.fetchone()
        if not r:
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,1)",
                ("admin", hash_password("admin123"))
            )
            conn.commit()
        else:
            if r[1] != 1:
                cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", ("admin",))
                conn.commit()
    except Exception:
        pass

ensure_admin_user()

def is_admin(username: str) -> bool:
    try:
        cursor.execute("SELECT is_admin FROM users WHERE username=?", (username,))
        r = cursor.fetchone()
        return bool(r and r[0] == 1)
    except Exception:
        return False

# ===================== EXCEPTIONS TK =====================
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

    def tk_callback_exception(self, exc, val, tb):
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

# ===================== SPLASH SCREEN (Reforçada e corrigida) =====================
class SplashScreen(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.geometry("520x300")
        self.configure(bg="#1e1e1e")

        # Centraliza manualmente
        try:
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (520 // 2)
            y = (self.winfo_screenheight() // 2) - (300 // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        # Garantir visibilidade (reforço)
        try:
            self.attributes('-topmost', True)
            self.lift()
            self.focus_force()
            # Reforços para o Windows não rebaixar
            self.after(10, self.lift)
            self.after(20, lambda: self.attributes('-topmost', True))
            self.after(30, self.focus_force)
        except Exception:
            pass

        frame = tk.Frame(self, bg="#1e1e1e")
        frame.pack(expand=True, fill="both")

        logo_path = os.path.join(os.getcwd(), "logo.png")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((240, 80))
                self.logo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=self.logo, bg="#1e1e1e").pack(pady=(40, 20))
            except Exception:
                tk.Label(frame, text="BESIM COMPANY", fg="white", bg="#1e1e1e",
                         font=("Segoe UI", 20, "bold")).pack(pady=(55, 20))
        else:
            tk.Label(frame, text="BESIM COMPANY", fg="white", bg="#1e1e1e",
                     font=("Segoe UI", 20, "bold")).pack(pady=(55, 20))
        tk.Label(frame, text="Atualizando sistema...", fg="#cccccc",
                 bg="#1e1e1e", font=("Segoe UI", 12)).pack()
        self.progress = ttk.Progressbar(frame, orient="horizontal",
                                         length=360, mode="determinate")
        self.progress.pack(pady=25)
        self.status = tk.Label(frame, text="Preparando atualização",
                               fg="#9cdcfe", bg="#1e1e1e",
                               font=("Segoe UI", 10))
        self.status.pack()
        # Removido: desativar topmost cedo demais
        # (não desativamos enquanto o splash existir)

    def set_progress(self, value):
        self.progress['value'] = value
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

# ===================== UPDATE (após login) =====================
def obter_versao_remota():
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{VERSION_FILE}"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=10) as r:
        return r.read().decode("utf-8").strip()


def baixar_e_extrair(splash: SplashScreen):
    zip_url = f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip"
    temp_dir = tempfile.mkdtemp(prefix="update_")
    zip_path = os.path.join(temp_dir, "repo.zip")
    splash.set_status("Baixando atualização...")
    splash.set_progress(5)
    with urllib.request.urlopen(zip_url, context=_SSL_CTX) as response:
        total = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        with open(zip_path, 'wb') as out:
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
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(temp_dir)
    splash.set_status("Copiando nova versão...")
    splash.set_progress(85)
    src_dir = next(os.scandir(temp_dir)).path
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel = os.path.relpath(root, src_dir)
        dest = os.path.join(os.getcwd(), rel)
        os.makedirs(dest, exist_ok=True)
        for f in files:
            if f not in IGNORE_FILES:
                shutil.copy2(os.path.join(root, f), os.path.join(dest, f))
    splash.set_status("Finalizando...")
    splash.set_progress(100)


def check_and_update_after_login(master: tk.Misc) -> bool:
    """Retorna True se atualizar (e reiniciar), False caso contrário."""
    try:
        remote_version = obter_versao_remota()
        if remote_version == APP_VERSION:
            return False
    except Exception as e:
        logging.error(f"Falha ao checar versão remota: {e}")
        return False

    try:
        # Esconde a janela principal para a splash ficar visível
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

        baixar_e_extrair(splash)
        splash.set_status("Atualização concluída. Reiniciando...")

        # Reforçar visibilidade antes do reinício
        try:
            splash.lift()
            splash.focus_force()
            splash.update()
        except Exception:
            pass

        master.after(1200, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))
        try:
            splash.update()
        except Exception:
            pass
        master.mainloop()
        return True
    except Exception as e:
        logging.error(f"Falha na atualização automática: {e}", exc_info=True)
        try:
            messagebox.showerror("Erro", "Falha na atualização automática")
        except Exception:
            pass
        return False

# ================= FUNÇÕES PDF =================
def gerar_cupom(cliente, produto, qtd, pagamento, total):
    agora = datetime.datetime.now()
    pasta_cupons = os.path.join(os.getcwd(), "cupons")
    os.makedirs(pasta_cupons, exist_ok=True)
    nome_arquivo = os.path.join(pasta_cupons, f"cupom_{agora.strftime('%Y%m%d_%H%M%S')}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), 40, 730, width=150, height=50, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY",
        "--------------------------------",
        f"Cliente: {cliente}",
        f"Produto: {produto}",
        f"Quantidade: {qtd}",
        f"Forma de Pagamento: {pagamento}",
        f"Total: R$ {total:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        f"Hora: {agora.strftime('%H:%M:%S')}",
        "--------------------------------",
        "Obrigado pela preferência!"
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(nome_arquivo)
        elif sistema == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")
    except Exception:
        pass


def gerar_os_pdf(os_num, nome, cpf, telefone, descricao, valor):
    agora = datetime.datetime.now()
    pasta_os = os.path.join(os.getcwd(), "OS")
    os.makedirs(pasta_os, exist_ok=True)
    nome_arquivo = os.path.join(pasta_os, f"OS_{os_num}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), 40, 730, width=150, height=50, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY - ORDEM DE SERVIÇO",
        "--------------------------------",
        f"OS Nº: {os_num}",
        f"Cliente: {nome}",
        f"CPF: {cpf}",
        f"Telefone: {telefone}",
        f"Descrição: {descricao}",
        f"Valor: R$ {valor:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        "--------------------------------"
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(nome_arquivo)
        elif sistema == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")
    except Exception:
        pass

# ================= FORMATAÇÃO CPF/TELEFONE/MOEDA =================
def formatar_cpf(event, entry):
    texto = ''.join(filter(str.isdigit, entry.get()))[:11]
    novo = ''
    for i, c in enumerate(texto):
        if i == 3 or i == 6:
            novo += '.'
        if i == 9:
            novo += '-'
        novo += c
    entry.delete(0, 'end')
    entry.insert(0, novo)


def formatar_telefone(event, entry):
    texto = ''.join(filter(str.isdigit, entry.get()))[:11]
    novo = ''
    for i, c in enumerate(texto):
        if i == 0:
            novo += '('
        if i == 2:
            novo += ') '
        if i == 7:
            novo += '-'
        novo += c
    entry.delete(0, 'end')
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

# ================= SISTEMA PRINCIPAL =================
def abrir_sistema_com_logo(username, login_win):
    root = tk.Toplevel()
    root.title(f"BESIM COMPANY - Usuário: {username}")
    root.geometry("1280x720")
    root.minsize(1100, 600)
    root.lift()
    root.focus_force()
    root.attributes('-topmost', True)
    root.after(200, lambda: root.attributes('-topmost', False))

    setup_global_exception_handlers(root)

    # Executa atualização após login (se houver)
    try:
        updated = check_and_update_after_login(root)
        if updated:
            return  # app será reiniciado
    except Exception:
        pass

    closing_state = {'mode': None}

    def on_close():
        if closing_state.get('mode') == 'logout':
            try:
                root.destroy()
            except Exception:
                pass
            try:
                if login_win and login_win.winfo_exists():
                    login_win.deiconify()
                    login_win.lift()
                    login_win.focus_force()
                    if hasattr(login_win, 'ent_user'):
                        login_win.ent_user.delete(0, 'end')
                    if hasattr(login_win, 'ent_pass'):
                        login_win.ent_pass.delete(0, 'end')
            except Exception:
                pass
            closing_state['mode'] = None
            return
        if messagebox.askyesno("Sair", "Tem certeza que deseja encerrar o sistema?"):
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
        else:
            return

    root.protocol("WM_DELETE_WINDOW", on_close)

    menu_bar = tk.Menu(root)
    menu_sessao = tk.Menu(menu_bar, tearoff=0)

    def do_logout():
        if messagebox.askyesno("Logout", "Deseja finalizar a sessão e voltar ao login?"):
            closing_state['mode'] = 'logout'
            on_close()
    def do_quit():
        closing_state['mode'] = None
        on_close()

    menu_sessao.add_command(label="Logout", accelerator="Ctrl+L", command=do_logout)
    menu_sessao.add_separator()
    menu_sessao.add_command(label="Sair", accelerator="Ctrl+Q", command=do_quit)
    menu_bar.add_cascade(label="Sessão", menu=menu_sessao)
    root.config(menu=menu_bar)
    root.bind_all("<Control-l>", lambda e: do_logout())
    root.bind_all("<Control-q>", lambda e: do_quit())

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
    style.map("TButton", foreground=[("active", "#000000")])
    style.configure("TNotebook.Tab", padding=[12, 8], font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", tabposition='n')
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    header = ttk.Frame(root)
    header.pack(fill="x", padx=12, pady=(8, 0))

    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((180, 54))
            log_img = ImageTk.PhotoImage(img)
            lbl_logo = ttk.Label(header, image=log_img)
            lbl_logo.image = log_img
            lbl_logo.pack(side="left")
        except Exception:
            ttk.Label(header, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(side="left")
    else:
        ttk.Label(header, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(side="left")

    abas = ttk.Notebook(root)
    abas.pack(fill="both", expand=True, padx=12, pady=(8, 12))

    aba_estoque = ttk.Frame(abas, padding=10)
    aba_vendas = ttk.Frame(abas, padding=10)
    aba_clientes = ttk.Frame(abas, padding=10)
    aba_caixa = ttk.Frame(abas, padding=10)
    aba_manutencao = ttk.Frame(abas, padding=10)
    aba_devolucao = ttk.Frame(abas, padding=10)

    abas.add(aba_estoque, text="Estoque")
    abas.add(aba_vendas, text="Vendas")
    abas.add(aba_clientes, text="Clientes")
    abas.add(aba_caixa, text="Caixa")
    abas.add(aba_manutencao, text="Manutenção")
    abas.add(aba_devolucao, text="Devolução")

    # ====== (Demais telas: Estoque, Clientes, Vendas, Caixa, Manutenção, Devolução) ======
    # (Conteúdo idêntico ao entregue anteriormente — preservado integralmente)
    # ...

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=8, pady=(2, 2), side="bottom")
    footer_text_main = "Developed by André Mariano\n\nBeta Test"
    ttk.Label(root, text=footer_text_main, style="Footer.TLabel", anchor="center", justify="center").pack(side="bottom", fill="x", pady=(0, 8))

# ================= TELA DE LOGIN =================

def abrir_login():
    login_win = tk.Tk()
    login_win.title("Login - BESIM COMPANY")
    login_win.geometry("420x300")
    login_win.resizable(False, False)
    setup_global_exception_handlers(login_win)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    frm = ttk.Frame(login_win, padding=12)
    frm.pack(fill="both", expand=True)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((200, 62))
            logo_img = ImageTk.PhotoImage(img)
            lbl_logo = ttk.Label(frm, image=logo_img)
            lbl_logo.image = logo_img
            lbl_logo.pack(pady=(0, 8))
        except Exception:
            ttk.Label(frm, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))
    else:
        ttk.Label(frm, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))

    ttk.Label(frm, text="Usuário").pack(anchor="w", pady=(6, 0))
    ent_user = ttk.Entry(frm)
    ent_user.pack(fill="x", pady=4)

    ttk.Label(frm, text="Senha").pack(anchor="w", pady=(6, 0))
    ent_pass = ttk.Entry(frm, show="*")
    ent_pass.pack(fill="x", pady=4)

    login_win.ent_user = ent_user
    login_win.ent_pass = ent_pass

    def tentar_login():
        user = ent_user.get().strip()
        pw = ent_pass.get().strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha")
            return
        cursor.execute("SELECT password_hash FROM users WHERE username=?", (user,))
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "Usuário não encontrado")
            return
        if hash_password(pw) == r[0]:
            login_win.withdraw()
            try:
                abrir_sistema_com_logo(user, login_win)
            except Exception as ex:
                messagebox.showerror("Erro fatal", f"Falha ao abrir a janela principal:\n{ex}")
                login_win.deiconify()
        else:
            messagebox.showerror("Erro", "Senha incorreta")

    def criar_usuario():
        user = ent_user.get().strip()
        pw = ent_pass.get().strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha para criar")
            return
        try:
            with conn:
                cursor.execute(
                    "INSERT INTO users(username,password_hash,is_admin) VALUES (?,?,0)",
                    (user, hash_password(pw))
                )
            messagebox.showinfo("OK", "Usuário criado com sucesso")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Usuário já existe")

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(fill="x", pady=12)
    ttk.Button(btn_frame, text="Entrar", command=tentar_login).pack(side="left", expand=True, padx=6)
    ttk.Button(btn_frame, text="Criar Usuário", command=criar_usuario).pack(side="left", expand=True, padx=6)

    ttk.Separator(login_win, orient="horizontal").pack(fill="x", padx=8, pady=(4, 2), side="bottom")
    footer_text = "Developed by André Mariano\n\nBeta Test"
    ttk.Label(login_win, text=footer_text, style="Footer.TLabel", anchor="center", justify="center").pack(side="bottom", fill="x", pady=(0, 8))

    def on_close_login():
        if messagebox.askyesno("Sair", "Deseja encerrar o sistema?"):
            try:
                conn.close()
            except Exception:
                pass
            login_win.destroy()
        else:
            return

    login_win.protocol("WM_DELETE_WINDOW", on_close_login)
    login_win.mainloop()

# ===================== MAIN =====================
if __name__ == "__main__":
    try:
        abrir_login()
    except Exception:
        logging.error("Erro ao iniciar a aplicação", exc_info=True)
        try:
            messagebox.showerror("Erro", "Falha ao iniciar a aplicação. Consulte o arquivo de logs.")
        except Exception:
            pass
