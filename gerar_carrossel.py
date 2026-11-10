"""
Gera o carrossel do LinkedIn (4 páginas, 1080 x 1350) a partir dos resultados do
chuva_calendario.py. Rode DEPOIS dele:

    python chuva_calendario.py          (ou --so-analise, se os dados já foram baixados)
    python gerar_carrossel.py

Saída: carrossel/saida/pagina_1.png ... pagina_4.png e carrossel/saida/carrossel_chuva_f1.pdf

O desenho fica em carrossel/carrossel.html (modelo B, "Bandeirada noturna"). Todos os
números vêm de resultados/. Os títulos são texto editorial; o script confere se eles
continuam verdadeiros com os dados e avisa no terminal se não forem.

Para testar outro modelo de design:  python gerar_carrossel.py --modelo A   (A a E)

Primeira vez (uma vez só, baixa o navegador que tira as "fotos" das páginas):
    python -m playwright install chromium
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from PIL import Image

PASTA = Path(__file__).resolve().parent
RESULTADOS = PASTA / "resultados"
HTML = PASTA / "carrossel" / "carrossel.html"
SAIDA = PASTA / "carrossel" / "saida"

LIMIAR_MM = 0.5
ANO_CALENDARIO = 2026
ANOS = (1996, 2025)
DESTAQUE = "Interlagos"
MODELOS = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}

# Nomes como aparecem no carrossel
NOMES = {
    "Melbourne": "Melbourne", "Shanghai": "Xangai", "Suzuka": "Suzuka", "Miami": "Miami",
    "Montreal": "Montreal", "Monte Carlo": "Mônaco", "Catalunya": "Barcelona", "Spielberg": "Áustria",
    "Silverstone": "Silverstone", "Spa-Francorchamps": "Spa", "Hungaroring": "Hungria",
    "Zandvoort": "Zandvoort", "Monza": "Monza", "Madring": "Madri", "Baku": "Baku",
    "Kuala Lumpur": "Malásia", "Singapore": "Singapura", "Austin": "Austin",
    "Mexico City": "Cidade do México", "Interlagos": "Interlagos", "Las Vegas": "Las Vegas",
    "Lusail": "Catar", "Yas Marina Circuit": "Abu Dhabi",
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                 "setembro", "outubro", "novembro", "dezembro"]


def pct(x: float) -> int:
    """Porcentagem arredondada como na escola (0,5 sobe)."""
    return int(x * 100 + 0.5)


def ler(nome: str) -> pd.DataFrame:
    arquivo = RESULTADOS / nome
    if not arquivo.exists():
        sys.exit(f"Falta resultados/{nome}. Rode antes: python chuva_calendario.py")
    return pd.read_csv(arquivo)


def montar_dados() -> tuple[dict, list[str]]:
    ranking = ler("ranking.csv")
    dias = ler("interlagos_dias.csv")
    cal = ler("calendario.csv")
    dif = ler("diferencas_interlagos.csv")

    chance = dict(zip(ranking["pista"], ranking["chance"]))
    top10 = [[NOMES.get(p, p), pct(c)] for p, c in zip(ranking["pista"][:10], ranking["chance"][:10])]
    fundo = ranking.sort_values("chance").head(3)["pista"].map(lambda p: NOMES.get(p, p)).tolist()

    d = dias.dropna(subset=["chuva_mm"]).copy()
    d["mes"] = pd.to_datetime(d["data"]).dt.month
    por_mes = (d["chuva_mm"] >= LIMIAR_MM).groupby(d["mes"]).mean()
    meses = [[MESES[m - 1], pct(por_mes[m])] for m in range(1, 13)]
    mes_gp = int(pd.to_datetime(cal.loc[cal["pista"] == DESTAQUE, "inicio_local"].iloc[0]).month)
    m_min, m_max = int(por_mes.idxmin()), int(por_mes.idxmax())

    dados = {
        "top10": top10,
        "interlagos": pct(chance[DESTAQUE]),
        "spa": pct(chance["Spa-Francorchamps"]),
        "corridas": int(len(ranking)),
        "anos": ANOS[1] - ANOS[0] + 1, "ano_ini": ANOS[0], "ano_fim": ANOS[1], "ano_cal": ANO_CALENDARIO,
        "meses": meses,
        "mes_gp": MESES[mes_gp - 1], "mes_gp_extenso": MESES_EXTENSO[mes_gp - 1],
        "min": [MESES_EXTENSO[m_min - 1], pct(por_mes[m_min])],
        "max": [MESES_EXTENSO[m_max - 1], pct(por_mes[m_max])],
        "perto_de_zero": f"{fundo[0]}, {fundo[1]} e {fundo[2]}",
    }

    # Os títulos continuam verdadeiros?
    avisos = []
    razao = chance[DESTAQUE] / chance["Spa-Francorchamps"]
    if razao < 1.9:
        avisos.append(f'Capa "Interlagos tem o dobro": a razão Interlagos/Spa agora é {razao:.2f}. Troque o título.')
    dois = list(ranking["pista"][:2])
    if DESTAQUE not in dois:
        avisos.append(f'Página 2 "Empate no topo": Interlagos não está entre as duas primeiras ({dois}).')
    else:
        outra = [p for p in dois if p != DESTAQUE][0]
        linha = dif[dif["pista"] == outra]
        if linha.empty or not (linha["dif_ic_baixo"].iloc[0] < 0 < linha["dif_ic_alto"].iloc[0]):
            avisos.append(f'Página 2 "Empate no topo": a diferença para {NOMES.get(outra, outra)} '
                          "deixou de estar dentro da margem de erro.")
    return dados, avisos


def desenhar(dados: dict, modelo: str) -> list[Path]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta o Playwright. Rode: python -m pip install -r requirements.txt "
                 "e depois: python -m playwright install chromium")
    SAIDA.mkdir(parents=True, exist_ok=True)
    arquivos = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1400, "height": 1500})
        pagina.add_init_script(f"window.DADOS = {json.dumps(dados, ensure_ascii=False)};"
                               f" window.MODELO = {MODELOS[modelo]};")
        pagina.goto(HTML.as_uri())
        pagina.evaluate("() => document.fonts.ready.then(() => true)")
        # Mostra as páginas no tamanho real (1080 px de largura)
        pagina.evaluate("""() => { const z = document.getElementById('c-zoom');
            z.max = 1080; z.value = 1080; z.dispatchEvent(new Event('input')); }""")
        pagina.evaluate("() => document.fonts.ready.then(() => true)")
        pagina.wait_for_timeout(500)
        for i, quadro in enumerate(pagina.query_selector_all(".quadro .palco"), start=1):
            destino = SAIDA / f"pagina_{i}.png"
            quadro.screenshot(path=str(destino))
            arquivos.append(destino)
        navegador.close()
    return arquivos


def main() -> None:
    modelo = "B"
    if "--modelo" in sys.argv:
        modelo = sys.argv[sys.argv.index("--modelo") + 1].upper()
        if modelo not in MODELOS:
            sys.exit("Use --modelo A, B, C, D ou E.")

    dados, avisos = montar_dados()
    print("Números do carrossel:")
    print(f"  Capa: Interlagos {dados['interlagos']}%, Spa {dados['spa']}%")
    print("  Ranking: " + ", ".join(f"{n} {v}%" for n, v in dados["top10"]))
    print("  Meses: " + ", ".join(f"{m} {v}%" for m, v in dados["meses"]))
    for a in avisos:
        print(f"  ATENÇÃO: {a}")

    arquivos = desenhar(dados, modelo)
    imagens = [Image.open(a).convert("RGB") for a in arquivos]
    pdf = SAIDA / "carrossel_chuva_f1.pdf"
    imagens[0].save(pdf, save_all=True, append_images=imagens[1:], resolution=100)
    print(f"\n{len(arquivos)} páginas em {SAIDA} (modelo {modelo}) e o PDF {pdf.name}, pronto para o LinkedIn.")


if __name__ == "__main__":
    main()
