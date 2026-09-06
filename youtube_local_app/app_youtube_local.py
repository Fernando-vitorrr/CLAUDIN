#!/usr/bin/env python3
"""Interface grafica local para base_youtube_local.py."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


PASTA_APP = Path(__file__).resolve().parent
SCRIPT = PASTA_APP / "base_youtube_local.py"
PASTA_PADRAO = Path.home() / "Google Drive" / "Meu Drive" / "Base YouTube"
CONFIG = PASTA_APP / "config.json"
CONTEXTO_POR_MODELO = {"qwen3.5:4b": 8192, "qwen3.5:9b": 16384, "qwen3.5:27b": 32768}


def ler_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


class Aplicativo:
    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        self.raiz.title("Base de conhecimento do YouTube")
        self.raiz.geometry("820x650")
        self.raiz.minsize(700, 520)
        self.eventos = queue.Queue()
        self.executando = False
        self.processo = None
        self.cfg = ler_config()

        quadro = ttk.Frame(raiz, padding=18)
        quadro.pack(fill="both", expand=True)
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(7, weight=1)

        ttk.Label(
            quadro,
            text="Base de conhecimento do YouTube",
            font=("Segoe UI", 17, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(
            quadro,
            text="Cole um ou mais links, um por linha. Todo o processamento ocorre neste computador.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(quadro, text="Links dos vídeos").grid(row=2, column=0, sticky="w")
        self.links = tk.Text(quadro, height=6, wrap="word")
        self.links.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(4, 12))

        ttk.Label(quadro, text="Pasta da base").grid(row=4, column=0, sticky="w")
        self.pasta = tk.StringVar(
            value=self.cfg.get("pasta") or os.environ.get("YTBASE_DIR", str(PASTA_PADRAO))
        )
        ttk.Entry(quadro, textvariable=self.pasta).grid(row=5, column=0, sticky="ew", pady=(4, 12))
        ttk.Button(quadro, text="Escolher pasta", command=self.escolher_pasta).grid(
            row=5, column=1, padx=(8, 0), pady=(4, 12)
        )
        ttk.Button(quadro, text="Abrir pasta", command=self.abrir_pasta).grid(
            row=5, column=2, padx=(8, 0), pady=(4, 12)
        )

        opcoes = ttk.Frame(quadro)
        opcoes.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        ttk.Label(opcoes, text="Modelo:").pack(side="left")
        self.modelo = tk.StringVar(value=self.cfg.get("modelo", "qwen3.5:9b"))
        caixa_modelo = ttk.Combobox(
            opcoes,
            textvariable=self.modelo,
            values=tuple(CONTEXTO_POR_MODELO),
            width=16,
            state="readonly",
        )
        caixa_modelo.pack(side="left", padx=(6, 14))
        caixa_modelo.bind("<<ComboboxSelected>>", self.ajustar_contexto)

        ttk.Label(opcoes, text="Janela:").pack(side="left")
        self.contexto = tk.StringVar(value=self.cfg.get("contexto", ""))
        ttk.Combobox(
            opcoes,
            textvariable=self.contexto,
            values=("", "8192", "16384", "32768"),
            width=8,
            state="readonly",
        ).pack(side="left", padx=(6, 14))

        ttk.Label(opcoes, text="Formato:").pack(side="left")
        self.formato = tk.StringVar(value=self.cfg.get("formato", "podcast"))
        ttk.Combobox(
            opcoes,
            textvariable=self.formato,
            values=("podcast", "aula"),
            width=9,
            state="readonly",
        ).pack(side="left", padx=(6, 14))
        self.forcar = tk.BooleanVar(value=False)
        ttk.Checkbutton(opcoes, text="Refazer vídeo já processado", variable=self.forcar).pack(
            side="left"
        )

        self.log = tk.Text(quadro, height=15, state="disabled", wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")

        botoes = ttk.Frame(quadro)
        botoes.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(botoes, text="Verificar instalação", command=self.verificar).pack(side="left")
        self.botao_processar = ttk.Button(
            botoes, text="Processar vídeos", command=self.processar
        )
        self.botao_processar.pack(side="right")
        self.botao_cancelar = ttk.Button(
            botoes, text="Cancelar", command=self.cancelar, state="disabled"
        )
        self.botao_cancelar.pack(side="right", padx=(0, 8))

        self.raiz.after(100, self.consumir_eventos)

    def ajustar_contexto(self, _evento=None):
        """A janela acompanha o modelo: 4b nao aguenta a janela do 27b."""
        self.contexto.set(str(CONTEXTO_POR_MODELO.get(self.modelo.get(), 16384)))

    def salvar_config(self):
        try:
            CONFIG.write_text(
                json.dumps(
                    {
                        "pasta": self.pasta.get(),
                        "modelo": self.modelo.get(),
                        "contexto": self.contexto.get(),
                        "formato": self.formato.get(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def cancelar(self):
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
            self.registrar("\nCancelado pelo usuário.\n")

    def escolher_pasta(self):
        escolhida = filedialog.askdirectory(initialdir=self.pasta.get() or str(Path.home()))
        if escolhida:
            self.pasta.set(escolhida)

    def abrir_pasta(self):
        pasta = Path(self.pasta.get()).expanduser()
        pasta.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(pasta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pasta)])
        else:
            subprocess.Popen(["xdg-open", str(pasta)])

    def registrar(self, texto: str):
        self.log.configure(state="normal")
        self.log.insert("end", texto)
        self.log.see("end")
        self.log.configure(state="disabled")

    def montar_comando(self, verificar=False):
        comando = [
            sys.executable,
            "-u",
            str(SCRIPT),
            "--base",
            self.pasta.get(),
            "--modelo",
            self.modelo.get(),
            "--formato",
            self.formato.get(),
        ]
        if self.contexto.get():
            comando += ["--contexto", self.contexto.get()]
        if verificar:
            comando.append("--verificar")
        if self.forcar.get():
            comando.append("--forcar")
        return comando

    def verificar(self):
        if not self.executando:
            self.iniciar(self.montar_comando(verificar=True))

    def processar(self):
        urls = [linha.strip() for linha in self.links.get("1.0", "end").splitlines() if linha.strip()]
        if not urls:
            messagebox.showwarning("Links necessários", "Cole ao menos um link do YouTube.")
            return
        comando = self.montar_comando() + urls
        self.iniciar(comando)

    def iniciar(self, comando):
        self.salvar_config()
        self.executando = True
        self.botao_processar.configure(state="disabled")
        self.botao_cancelar.configure(state="normal")
        self.registrar("\n" + "=" * 60 + "\n")
        threading.Thread(target=self.executar, args=(comando,), daemon=True).start()

    def executar(self, comando):
        try:
            # Sem UTF-8 explicito, titulo de video com acento ou emoji derruba
            # o processo filho com UnicodeEncodeError no console do Windows.
            ambiente = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            self.processo = processo = subprocess.Popen(
                comando,
                cwd=PASTA_APP,
                env=ambiente,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert processo.stdout is not None
            for linha in processo.stdout:
                self.eventos.put(("log", linha))
            codigo = processo.wait()
            self.eventos.put(("fim", codigo))
        except Exception as exc:
            self.eventos.put(("erro", str(exc)))

    def encerrar(self):
        self.executando = False
        self.processo = None
        self.botao_processar.configure(state="normal")
        self.botao_cancelar.configure(state="disabled")

    def consumir_eventos(self):
        try:
            while True:
                tipo, valor = self.eventos.get_nowait()
                if tipo == "log":
                    self.registrar(valor)
                elif tipo == "fim":
                    self.encerrar()
                    if valor == 0:
                        self.registrar("\nConcluído sem erros.\n")
                    else:
                        self.registrar(
                            "\nHouve falhas. Leia o resumo acima antes de "
                            "considerar a base atualizada.\n"
                        )
                elif tipo == "erro":
                    self.encerrar()
                    self.registrar(f"\nERRO: {valor}\n")
        except queue.Empty:
            pass
        self.raiz.after(100, self.consumir_eventos)


if __name__ == "__main__":
    root = tk.Tk()
    Aplicativo(root)
    root.mainloop()
