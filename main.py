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
        # se o SIDRA retornar 4xx/5xx, cai no except e devolve 500; vamos tratar 400/404 melhor:
        if r.status_code == 400:
            return jsonify({"error": "Requisição inválida ao SIDRA (verifique tabela/variável/período)."}), 400
        if r.status_code == 404:
            return jsonify({"error": "Recurso não encontrado no SIDRA (verifique IDs informados)."}), 400

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

        # URL ABSOLUTA (importante para o GPT Actions baixar sem “adivinhar” o host)
        base_url = request.host_url.rstrip("/")
        download_url = f"{base_url}/download/{file_id}"

        return jsonify({
            "status": "sucesso",
            "mensagem": "Arquivo gerado com sucesso",
            "download_url": download_url,
            "preview": df.head(3).to_dict(orient="records")
        })

    except Exception as e:
        return jsonify({"error": f"Erro ao processar SIDRA: {str(e)}"}), 500
