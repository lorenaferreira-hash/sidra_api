import os
import uuid
import time
import requests
import pandas as pd
from typing import Optional, Dict, List
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ROBÔ SIDRA PREMIUM V5.6 API")

# Habilitar CORS para evitar bloqueios de navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurações de Diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Dicionário Original Integrado [cite: 25, 31]
GRUPOS_ANALISE = {
    "1": {"nome": "Saneamento Básico", "tabelas": {"3218": "Abastecimento de Água/Esgoto", "9547": "Destino do Lixo", "9546": "Esgotamento Sanitário", "3166": "Banheiro e Esgoto"}},
    "2": {"nome": "Renda", "tabelas": {"10315": "Rendimento per capita", "5438": "Rendimento nominal", "6784": "Rendimento real", "2499": "Linha da pobreza"}},
    "3": {"nome": "Demografia", "tabelas": {"9514": "População por idade", "475": "População situação/sexo", "202": "População residente", "6579": "Estimativa Populacional"}},
    "4": {"nome": "Moradia", "tabelas": {"9541": "Tipo de domicílio", "9539": "Condição de ocupação", "2633": "Energia elétrica"}},
    "5": {"nome": "Habitação", "tabelas": {"2636": "Pessoas por dormitório", "2637": "Áreas públicas/lazer"}},
    "6": {"nome": "Educação", "tabelas": {"1570": "Taxa escolarização", "1571": "Crianças idade escolar"}},
    "7": {"nome": "Saúde", "tabelas": {"5271": "Acesso a hospitais", "5272": "Segurança pública"}},
    "8": {"nome": "Mobilidade", "tabelas": {"1266": "Transporte público", "2632": "Vias pavimentadas"}},
    "9": {"nome": "Desastres", "tabelas": {"1861": "Áreas de risco", "9923": "Vulnerabilidade urbana"}}
}

# --- FUNÇÕES DE SUPORTE ---
def cleanup_files():
    """Remove arquivos com mais de 1 hora para economizar espaço no Render."""
    now = time.time()
    for f in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, f)
        if os.path.getmtime(path) < now - 3600:
            os.remove(path)

# --- ENDPOINTS ---

@app.get("/")
def root():
    return {"status": "online", "versao": "5.6 Premium", "servico": "SIDRA IBGE API"}

@app.get("/grupos")
def listar_grupos():
    """Retorna os grupos conforme o robô original[cite: 42]."""
    return {k: v["nome"] for k, v in GRUPOS_ANALISE.items()}

@app.get("/grupos/{grupo_id}/tabelas")
def listar_tabelas(grupo_id: str):
    """Lista as tabelas do grupo selecionado[cite: 42]."""
    grupo = GRUPOS_ANALISE.get(grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo inválido")
    return grupo["tabelas"]

@app.get("/municipio/buscar")
def buscar_municipio(nome: str):
    """Busca o ID do município para evitar o erro de 'parâmetro nome ausente'."""
    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    r = requests.get(url)
    nome_norm = nome.lower().strip()
    res = [{"id": m["id"], "nome": f"{m['nome']} ({m['microrregiao']['mesorregiao']['UF']['sigla']})"} 
           for m in r.json() if nome_norm in m["nome"].lower()]
    return res[:10]

@app.get("/metadados/{tabela_id}")
def obter_metadados(tabela_id: str):
    """Extrai anos, variáveis e classificações para o GPT guiar o usuário[cite: 43]."""
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela_id}/metadados"
    r = requests.get(url)
    if r.status_code != 200: raise HTTPException(status_code=404, detail="Tabela não encontrada")
    data = r.json()
    return {
        "variaveis": [{"id": v["id"], "nome": v["nome"]} for v in data.get("variaveis", [])],
        "classificacoes": [{"id": c["id"], "nome": c["nome"], "categorias": [{"id": cat["id"], "nome": cat["nome"]} for cat in c.get("categorias", [])]} for c in data.get("classificacoes", [])]
    }

@app.get("/gerar_excel")
def gerar_excel(background_tasks: BackgroundTasks, tabela: str, municipio: str, periodos: str = "all", variaveis: str = "allxp", classificacoes: str = ""):
    """Gera o arquivo e retorna a URL de download para o GPT[cite: 33]."""
    background_tasks.add_task(cleanup_files)
    
    # Construção da URL SIDRA [cite: 33]
    c_url = ""
    if classificacoes:
        for part in classificacoes.split("|"):
            if ":" in part:
                cid, cats = part.split(":")
                c_url += f"/c{cid.replace('c','')}/{cats}"

    sidra_url = f"https://apisidra.ibge.gov.br/values/t/{tabela}/n6/{municipio}/v/{variaveis}/p/{periodos}{c_url}"
    
    try:
        r = requests.get(sidra_url, timeout=45)
        if r.status_code != 200 or len(r.json()) < 2:
            return {"error": "SIDRA não retornou dados. Verifique os parâmetros."}
        
        df = pd.DataFrame(r.json()[1:], columns=r.json()[0])
        
        # Renomeação amigável conforme script original [cite: 36, 37]
        df.columns = [str(c).replace("D1N", "Município").replace("D2N", "Variável").replace("D3N", "Ano").replace("V", "Valor") for c in df.columns]
        
        file_id = f"sidra_{uuid.uuid4().hex[:6]}.xlsx"
        file_path = os.path.join(OUTPUT_DIR, file_id)
        df.to_excel(file_path, index=False)
        
        return {"download_url": f"/download/{file_id}", "linhas": len(df)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/download/{file_id}")
def download(file_id: str):
    path = os.path.join(OUTPUT_DIR, file_id)
    if os.path.exists(path):
        return FileResponse(path, filename=file_id)
    raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado")
