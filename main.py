import requests
import pandas as pd
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional, List, Dict
import uuid

app = FastAPI(title="IBGE SIDRA GPT API", description="API para consulta de dados do IBGE SIDRA")

# Mapeamento de Grupos de Análise e Tabelas (Copiado do original)
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

OUTPUT_DIR = "/home/ubuntu/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def limpar_input(texto):
    if not texto: return ""
    return str(texto).replace("'", "").replace('"', "").strip()

@app.get("/municipio/buscar")
def buscar_municipio(nome: str):
    """Busca o código IBGE de um município pelo nome."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            municipios = response.json()
            # Busca aproximada
            nome_busca = nome.lower().strip()
            resultados = []
            for m in municipios:
                if nome_busca in m["nome"].lower():
                    resultados.append({
                        "id": m["id"],
                        "nome": m["nome"],
                        "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
                    })
            return resultados[:10] # Retorna os 10 primeiros
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/grupos")
def listar_grupos():
    """Retorna apenas os nomes dos grupos de análise."""
    return {k: v["nome"] for k, v in GRUPOS_ANALISE.items()}

@app.get("/grupos/{grupo_id}/tabelas")
def listar_tabelas_grupo(grupo_id: str):
    """Retorna as tabelas de um grupo específico."""
    grupo = GRUPOS_ANALISE.get(grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    return grupo["tabelas"]

@app.get("/metadados/{tabela_id}")
def obter_metadados(tabela_id: str):
    """Obtém variáveis, períodos e classificações de uma tabela."""
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela_id}/metadados"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            # Simplificar para o GPT não se perder
            return {
                "id": data.get("id"),
                "nome": data.get("nome"),
                "variaveis": [{"id": v["id"], "nome": v["nome"]} for v in data.get("variaveis", [])],
                "classificacoes": [{"id": c["id"], "nome": c["nome"], "categorias": [{"id": cat["id"], "nome": cat["nome"]} for cat in c.get("categorias", [])]} for c in data.get("classificacoes", [])]
            }
        raise HTTPException(status_code=404, detail="Tabela não encontrada")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/periodos/{tabela_id}")
def obter_periodos(tabela_id: str):
    """Obtém os períodos disponíveis para uma tabela."""
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela_id}/periodos"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
        return []
    except:
        return []

@app.get("/gerar_excel")
def gerar_excel(
    tabela: str,
    municipio: str,
    periodos: str = "all",
    variaveis: str = "allxp",
    classificacoes: Optional[str] = None # Formato: c1:cat1,cat2|c2:cat3
):
    """
    Gera um arquivo Excel com os dados do SIDRA.
    classificacoes deve ser enviado como string no formato: cID:catID1,catID2|cID2:catID3
    """
    tabela = limpar_input(tabela)
    municipio = limpar_input(municipio)
    
    c_url_part = ""
    if classificacoes:
        parts = classificacoes.split("|")
        for p in parts:
            if ":" in p:
                c_id, cats = p.split(":")
                # Garantir que começa com 'c' se não tiver
                c_tag = c_id if c_id.startswith('c') else f"c{c_id}"
                c_url_part += f"/{c_tag}/{cats}"

    url = f"https://apisidra.ibge.gov.br/values/t/{tabela}/n6/{municipio}/v/{variaveis}/p/{periodos}{c_url_part}"
    
    try:
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        dados_json = response.json()
        
        if not dados_json or len(dados_json) < 2:
            msg = "A API não retornou dados."
            if isinstance(dados_json, dict) and 'message' in dados_json:
                msg = dados_json['message']
            raise HTTPException(status_code=400, detail=msg)
            
        df = pd.DataFrame(dados_json[1:], columns=dados_json[0])
        
        tradução = {
            'NC': 'Nivel_Territorial_Cod', 'NN': 'Nivel_Territorial_Nome',
            'MC': 'Unidade_Medida_Cod', 'MN': 'Unidade_Medida_Nome',
            'V':  'Valor', 'D1C': 'Municipio_Cod', 'D1N': 'Municipio_Nome',
            'D2C': 'Variavel_Cod', 'D2N': 'Variavel_Nome',
            'D3C': 'Ano_Cod', 'D3N': 'Ano_Nome'
        }
        for i in range(4, 20):
            tradução[f'D{i}C'] = f'Classificacao_{i-3}_Cod'
            tradução[f'D{i}N'] = f'Classificacao_{i-3}_Nome'

        df.rename(columns=tradução, inplace=True)
        
        file_id = f"{tabela}_{municipio}_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = os.path.join(OUTPUT_DIR, file_id)
        df.to_excel(file_path, index=False)
        
        return {
            "status": "sucesso",
            "mensagem": "Arquivo gerado com sucesso",
            "download_url": f"/download/{file_id}",
            "preview": df.head(3).to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar SIDRA: {str(e)}")

@app.get("/download/{file_id}")
def download_arquivo(file_id: str):
    file_path = os.path.join(OUTPUT_DIR, file_id)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=file_id, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    raise HTTPException(status_code=404, detail="Arquivo não encontrado")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
