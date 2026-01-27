import os
import uuid
import requests
import pandas as pd
from typing import Optional
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# -----------------------------
# Mapeamento de Grupos e Tabelas
# -----------------------------
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

# -----------------------------
# Pastas (sem /home/ubuntu!)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output_files")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def limpar_input(texto):
    if not texto:
        return ""
    return str(texto).replace("'", "").replace('"', "").strip()

def parse_classificacoes(classificacoes: Optional[str]) -> str:
    """
    Entrada: "c1:1,2|c2:3"
    Saída: "/c1/1,2/c2/3"
    """
    if not classificacoes:
        return ""
    c_url_part = ""
    parts = classificacoes.split("|")
    for p in parts:
        if ":" in p:
            c_id, cats = p.split(":", 1)
            c_id = c_id.strip()
            cats = cats.strip()
            c_tag = c_id if c_id.startswith("c") else f"c{c_id}"
            c_url_part += f"/{c_tag}/{cats}"
    return c_url_part


# -----------------------------
# Rotas
# -----------------------------
@app.get("/")
def home():
    return jsonify({"status": "ok", "msg": "IBGE SIDRA API (Flask/WSGI)"})


@app.get("/municipio/buscar")
def buscar_municipio():
    nome = request.args.get("nome", "").strip()
    if not nome:
        return jsonify([])

    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        municipios = r.json()

        nome_busca = nome.lower()
        resultados = []
        for m in municipios:
            if nome_busca in m["nome"].lower():
                resultados.append({
                    "id": m["id"],
                    "nome": m["nome"],
                    "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
                })

        return jsonify(resultados[:10])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/grupos")
def listar_grupos():
    return jsonify({k: v["nome"] for k, v in GRUPOS_ANALISE.items()})


@app.get("/grupos/<grupo_id>/tabelas")
def listar_tabelas_grupo(grupo_id):
    grupo = GRUPOS_ANALISE.get(grupo_id)
    if not grupo:
        return jsonify({"error": "Grupo não encontrado"}), 404
    return jsonify(grupo["tabelas"])


@app.get("/metadados/<tabela_id>")
def obter_metadados(tabela_id):
    tabela_id = limpar_input(tabela_id)
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela_id}/metadados"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return jsonify({"error": "Tabela não encontrada"}), 404

        data = r.json()
        payload = {
            "id": data.get("id"),
            "nome": data.get("nome"),
            "variaveis": [{"id": v["id"], "nome": v["nome"]} for v in data.get("variaveis", [])],
            "classificacoes": [
                {
                    "id": c["id"],
                    "nome": c["nome"],
                    "categorias": [{"id": cat["id"], "nome": cat["nome"]} for cat in c.get("categorias", [])]
                }
                for c in data.get("classificacoes", [])
            ]
        }
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/periodos/<tabela_id>")
def obter_periodos(tabela_id):
    tabela_id = limpar_input(tabela_id)
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela_id}/periodos"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify([])
    except:
        return jsonify([])


@app.get("/gerar_excel")
def gerar_excel():
    tabela = limpar_input(request.args.get("tabela", ""))
    municipio = limpar_input(request.args.get("municipio", ""))
    periodos = limpar_input(request.args.get("periodos", "all")) or "all"
    variaveis = limpar_input(request.args.get("variaveis", "allxp")) or "allxp"
    classificacoes = request.args.get("classificacoes")  # "c1:1,2|c2:3"

    if not tabela or not municipio:
        return jsonify({"error": "Parâmetros obrigatórios: tabela e municipio"}), 400

    c_url_part = parse_classificacoes(classificacoes)

    url = f"https://apisidra.ibge.gov.br/values/t/{tabela}/n6/{municipio}/v/{variaveis}/p/{periodos}{c_url_part}"

    try:
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        dados_json = r.json()

        if not dados_json or len(dados_json) < 2:
            msg = "A API não retornou dados."
            if isinstance(dados_json, dict) and "message" in dados_json:
                msg = dados_json["message"]
            return jsonify({"error": msg}), 400

        df = pd.DataFrame(dados_json[1:], columns=dados_json[0])

        traducao = {
            "NC": "Nivel_Territorial_Cod", "NN": "Nivel_Territorial_Nome",
            "MC": "Unidade_Medida_Cod", "MN": "Unidade_Medida_Nome",
            "V": "Valor",
            "D1C": "Municipio_Cod", "D1N": "Municipio_Nome",
            "D2C": "Variavel_Cod", "D2N": "Variavel_Nome",
            "D3C": "Ano_Cod", "D3N": "Ano_Nome",
        }
        for i in range(4, 20):
            traducao[f"D{i}C"] = f"Classificacao_{i-3}_Cod"
            traducao[f"D{i}N"] = f"Classificacao_{i-3}_Nome"

        df.rename(columns=traducao, inplace=True)

        file_id = f"{tabela}_{municipio}_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = os.path.join(OUTPUT_DIR, file_id)
        df.to_excel(file_path, index=False)

        return jsonify({
            "status": "sucesso",
            "mensagem": "Arquivo gerado com sucesso",
            "download_url": f"/download/{file_id}",
            "preview": df.head(3).to_dict(orient="records")
        })

    except Exception as e:
        return jsonify({"error": f"Erro ao processar SIDRA: {str(e)}"}), 500


@app.get("/download/<file_id>")
def download_arquivo(file_id):
    safe_name = os.path.basename(file_id)
    file_path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(file_path):
        return jsonify({"error": "Arquivo não encontrado"}), 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    # Rodar localmente (no seu PC)
    app.run(host="0.0.0.0", port=8000, debug=True)
