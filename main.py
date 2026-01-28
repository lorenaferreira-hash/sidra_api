import os
import uuid
import time
import requests
import pandas as pd
from typing import Optional
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# =========================================================
# CONFIGURAÇÕES
# =========================================================
SIDRA_BASE = "https://apisidra.ibge.gov.br/values"
IBGE_META_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
IBGE_MUN_BASE = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

# No Render, usamos caminhos relativos ao diretório de execução
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output_files")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", str(2 * 60 * 60)))
REQ_TIMEOUT = int(os.getenv("REQ_TIMEOUT", "45"))

GRUPOS_ANALISE = {
     "1": {"nome": "Saneamento Básico", "tabelas": {
        "3218": "Domicílios particulares permanentes, por forma de abastecimento de água, segundo a existência de banheiro ou sanitário e esgotamento sanitário, o destino do lixo e a existência de energia elétrica",
        "9547": "Domicílios particulares permanentes, por destino do lixo",
        "9546": "Domicílios particulares permanentes, por tipo de esgotamento sanitário",
        "3166": "Domicílios particulares permanentes, por existência de banheiro ou sanitário e tipo de esgotamento sanitário"
    }},
    "2": {"nome": "Renda", "tabelas": {
        "10315": "Rendimento médio e mediano domiciliar per capita nominal mensal",
        "5438": "Rendimento médio mensal nominal das pessoas de 10 anos ou mais de idade",
        "6784": "Rendimento médio mensal real das pessoas de 14 anos ou mais de idade",
        "2499": "Domicílios com rendimento mensal domiciliar per capita abaixo da linha da pobreza"
    }},
    "3": {"nome": "Demografia", "tabelas": {
        "9514": "População residente, por sexo e idade",
        "475": "População residente por grupos de idade, sexo e situação",
        "202": "População residente, por sexo e situação do domicílio",
        "9923": "População residente, por situação do domicílio",
        "197": "Nascidos vivos, por grupos de idade da mãe",
        "2684": "Óbitos, por causas e faixas etárias",
        "6579": "População residente estimada",
        "1552": "População residente, por situação do domicílio e sexo, segundo a forma de declaração da idade e a idade"
    }},
    "4": {"nome": "Condições de Moradia", "tabelas": {
        "9541": "Domicílios particulares permanentes, por tipo de domicílio",
        "9539": "Domicílios particulares permanentes, por condição de ocupação",
        "2633": "Domicílios particulares permanentes, por existência de energia elétrica",
        "9545": "Domicílios particulares permanentes, por existência de banheiro ou sanitário"
    }},
    "5": {"nome": "Habitação e Urbanização", "tabelas": {
        "2636": "Domicílios particulares permanentes, por número de pessoas por dormitório",
        "2637": "Domicílios particulares permanentes, por existência de áreas públicas e lazer"
    }},
    "6": {"nome": "Educação e Qualidade de Vida", "tabelas": {
        "1570": "Taxa de escolarização de crianças e adolescentes",
        "1571": "Domicílios com crianças e adolescentes em idade escolar"
    }},
    "7": {"nome": "Segurança e Saúde", "tabelas": {
        "5271": "Domicílios com acesso a postos de saúde ou hospitais",
        "5272": "Domicílios com acesso a segurança pública (delegacias e bombeiros)"
    }},
    "8": {"nome": "Mobilidade e Transporte", "tabelas": {
        "1266": "Domicílios com acesso a transporte público",
        "2632": "Domicílios com acesso a vias pavimentadas e ciclovias"
    }},
    "9": {"nome": "Desastres e Vulnerabilidade", "tabelas": {
        "1861": "Domicílios em áreas de risco (inundações e deslizamentos)",
        "9923": "Variações climáticas e vulnerabilidade urbana"
    }}
}

def limpar_input(texto) -> str:
    if texto is None: return ""
    return str(texto).replace("'", "").replace('"', "").strip()

def split_csv(value: str) -> str:
    value = limpar_input(value)
    if not value: return ""
    return ",".join([v.strip() for v in value.split(",") if v.strip()])

def parse_classificacoes(classificacoes: Optional[str]) -> str:
    if not classificacoes: return ""
    c_url_part = ""
    parts = classificacoes.split("|")
    for p in parts:
        if ":" in p:
            c_id, cats = p.split(":", 1)
            c_id = limpar_input(c_id)
            cats = limpar_input(cats)
            if not c_id or not cats: continue
            c_tag = c_id if c_id.startswith("c") else f"c{c_id}"
            c_url_part += f"/{c_tag}/{cats}"
    return c_url_part

def cleanup_old_files():
    try:
        now = time.time()
        for fname in os.listdir(OUTPUT_DIR):
            fpath = os.path.join(OUTPUT_DIR, fname)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath) > FILE_TTL_SECONDS):
                os.remove(fpath)
    except: pass

def build_base_url() -> str:
    proto = request.headers.get("X-Forwarded-Proto", "https")
    host = request.headers.get("Host", request.host)
    return f"{proto}://{host}".rstrip("/")

def rename_columns_sidra(df: pd.DataFrame) -> pd.DataFrame:
    traducao = {
        "NC": "Nivel_Territorial_Cod", "NN": "Nivel_Territorial_Nome",
        "MC": "Unidade_Medida_Cod", "MN": "Unidade_Medida_Nome",
        "V":  "Valor", "D1C": "Municipio_Cod", "D1N": "Municipio_Nome",
        "D2C": "Variavel_Cod", "D2N": "Variavel_Nome",
        "D3C": "Periodo_Cod", "D3N": "Periodo_Nome",
    }
    for i in range(4, 25):
        traducao[f"D{i}C"] = f"Classificacao_{i-3}_Cod"
        traducao[f"D{i}N"] = f"Classificacao_{i-3}_Nome"
    return df.rename(columns=traducao)

@app.get("/")
def home():
    return jsonify({"status": "ok", "msg": "IBGE SIDRA API Corrigida"}), 200

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.get("/grupos")
def listar_grupos():
    return jsonify({k: v["nome"] for k, v in GRUPOS_ANALISE.items()}), 200

@app.get("/grupos/<grupo_id>/tabelas")
def listar_tabelas_grupo(grupo_id):
    grupo = GRUPOS_ANALISE.get(grupo_id)
    return jsonify(grupo["tabelas"]) if grupo else (jsonify({"error": "Grupo não encontrado"}), 404)

@app.get("/municipio/buscar")
def buscar_municipio():
    nome = request.args.get("nome", "").lower()
    if not nome: return jsonify([]), 200
    try:
        r = requests.get(IBGE_MUN_BASE, timeout=15)
        r.raise_for_status()
        res = [{"id": m["id"], "nome": m["nome"], "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"]} 
               for m in r.json() if nome in m["nome"].lower()]
        return jsonify(res[:10]), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.get("/metadados/<tabela_id>")
def obter_metadados(tabela_id):
    try:
        r = requests.get(f"{IBGE_META_BASE}/{tabela_id}/metadados", timeout=15)
        if r.status_code == 404: return jsonify({"error": "Tabela não encontrada"}), 404
        data = r.json()
        payload = {
            "id": data.get("id"),
            "nome": data.get("nome"),
            "variaveis": [{"id": v["id"], "nome": v["nome"]} for v in data.get("variaveis", [])],
            "classificacoes": [{"id": c["id"], "nome": c["nome"], "categorias": [{"id": cat["id"], "nome": cat["nome"]} for cat in c.get("categorias", [])]} for c in data.get("classificacoes", [])]
        }
        return jsonify(payload), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.get("/gerar_excel")
def gerar_excel():
    cleanup_old_files()
    tabela = request.args.get("tabela", "")
    municipio = request.args.get("municipio", "")
    periodos = split_csv(request.args.get("periodos", "all")) or "all"
    variaveis = split_csv(request.args.get("variaveis", "allxp")) or "allxp"
    classificacoes = request.args.get("classificacoes", "")

    if not tabela or not municipio:
        return jsonify({"error": "Parâmetros 'tabela' e 'municipio' são obrigatórios"}), 400

    c_url_part = parse_classificacoes(classificacoes)
    url = f"{SIDRA_BASE}/t/{tabela}/n6/{municipio}/v/{variaveis}/p/{periodos}{c_url_part}"

    try:
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        dados_json = r.json()

        if not dados_json or len(dados_json) < 2:
            return jsonify({"error": "O SIDRA não retornou dados para esta consulta.", "sidra_url": url}), 400

        df = pd.DataFrame(dados_json[1:], columns=dados_json[0])
        df = rename_columns_sidra(df)

        file_id = f"{tabela}_{municipio}_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = os.path.join(OUTPUT_DIR, file_id)
        df.to_excel(file_path, index=False)

        download_url = f"{build_base_url()}/download/{file_id}"

        return jsonify({
            "status": "sucesso",
            "download_url": download_url,
            "preview": df.head(5).to_dict(orient="records")
        }), 200
    except Exception as e: return jsonify({"error": f"Erro SIDRA: {str(e)}"}), 500

@app.get("/download/<file_id>")
def download_arquivo(file_id):
    file_path = os.path.join(OUTPUT_DIR, os.path.basename(file_id))
    if not os.path.exists(file_path): return jsonify({"error": "Arquivo expirado ou não encontrado"}), 404
    return send_file(file_path, as_attachment=True, download_name=file_id)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

