"""
Chuva na F1: onde mais chove na hora da corrida?

Para cada corrida do calendário de 2026, mede a chance de chover durante as 2 horas
de corrida, na data e no horário daquele GP (em UTC, para não errar com horário de
verão), olhando os últimos 30 anos de clima (1996 a 2025). Usa a reanálise ERA5 pela
API gratuita da Open-Meteo.

Antes, confere se o ERA5 "enxerga" a chuva de verdade: compara a chuva que ele marca
na hora das corridas de 2023 em diante com as corridas que tiveram pneu de chuva (OpenF1).

Como rodar (na pasta deste arquivo):
    python -m pip install -r requirements.txt
    python chuva_calendario.py

A primeira execução baixa os dados (cerca de 20 a 30 minutos, por causa das pausas
entre pedidos) e guarda tudo em dados/. Se a Open-Meteo avisar que o limite do dia
acabou, rode de novo no dia seguinte: o que já foi baixado fica salvo.

Para refazer só as contas e os gráficos, sem baixar nada:
    python chuva_calendario.py --so-analise

Saídas: chuva_ranking.png, chuva_interlagos_ano.png, resultados/*.csv e
resultados/resumo.txt (o mesmo texto impresso no terminal).
Depois, para montar o carrossel do LinkedIn:  python gerar_carrossel.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib import font_manager

# =============================================================================
# 1. CONFIGURAÇÃO: textos, cores e parâmetros (mexa aqui, não no resto)
# =============================================================================

ANO_CALENDARIO = 2026
ANOS_CLIMA = list(range(1996, 2026))   # 30 anos de histórico
ANOS_VALIDACAO = [2023, 2024, 2025, 2026]
DIAS_ANTES_DEPOIS = 3        # usa a data do GP e 3 dias antes e depois (7 dias por ano)
DURACAO_HORAS = 2            # duração considerada da corrida
LIMIAR_MM = 0.5              # "choveu na corrida" = pelo menos 0,5 mm nas 2 horas
LIMIARES_TESTE = [0.2, 0.5, 1.0, 2.0]
LIMIAR_PNEU_CHUVA = 10       # corrida molhada = 10% ou mais das voltas com pneu intermediário ou de chuva
ATRASO_ERA5_DIAS = 6         # o ERA5 chega com cerca de 5 dias de atraso
REPETICOES_BOOTSTRAP = 2000
SEMENTE = 2026

API_OPENF1 = "https://api.openf1.org/v1/"
API_CLIMA = "https://archive-api.open-meteo.com/v1/archive"
MODELO_CLIMA = "era5"        # reanálise ERA5 (ECMWF), grade de cerca de 25 km, desde 1940

PASTA = Path(__file__).resolve().parent
PASTA_DADOS = PASTA / "dados"
PASTA_RESULTADOS = PASTA / "resultados"
PASTA_FONTES = PASTA / "fontes"
ARQUIVO_RANKING_PNG = PASTA / "chuva_ranking.png"
ARQUIVO_ANO_PNG = PASTA / "chuva_interlagos_ano.png"

CORRECOES_PNEU: dict[tuple[int, str], float] = {
    # (ano, pista): % de voltas com pneu de chuva, quando os stints da OpenF1 estão errados.
    # Spa 2025: a OpenF1 marca intermediário só na volta 1, mas a largada (16h20 local, depois de
    # mais de 1 hora de atraso pela chuva) foi de intermediário e os líderes trocaram para slick
    # nas voltas 12 e 13, de 44 (relato da corrida no Motorsport.com). Cerca de 11 de 44 voltas.
    (2025, "Spa-Francorchamps"): 25.0,
}

PAUSA_OPENF1 = 2.1          # a OpenF1 aceita 30 pedidos por minuto
PAUSA_CLIMA = 0.35
TENTATIVAS = 7

# Coordenadas dos circuitos (latitude, longitude)
COORDENADAS = {
    "Sakhir": (26.0325, 50.5106), "Jeddah": (21.6319, 39.1044), "Melbourne": (-37.8497, 144.9680),
    "Shanghai": (31.3389, 121.2197), "Suzuka": (34.8431, 136.5407), "Miami": (25.9581, -80.2389),
    "Imola": (44.3439, 11.7167), "Monte Carlo": (43.7347, 7.4206), "Catalunya": (41.5700, 2.2611),
    "Montreal": (45.5000, -73.5228), "Spielberg": (47.2197, 14.7647), "Silverstone": (52.0786, -1.0169),
    "Hungaroring": (47.5789, 19.2486), "Spa-Francorchamps": (50.4372, 5.9714), "Zandvoort": (52.3888, 4.5409),
    "Monza": (45.6156, 9.2811), "Madring": (40.4637, -3.6163), "Baku": (40.3725, 49.8533),
    "Kuala Lumpur": (2.7608, 101.7381), "Singapore": (1.2914, 103.8640), "Austin": (30.1328, -97.6411),
    "Mexico City": (19.4042, -99.0907), "Interlagos": (-23.7036, -46.6997), "Las Vegas": (36.1147, -115.1730),
    "Lusail": (25.4900, 51.4542), "Yas Marina Circuit": (24.4672, 54.6031),
}

NOMES = {
    "Melbourne": "Melbourne", "Shanghai": "Xangai", "Suzuka": "Suzuka", "Miami": "Miami",
    "Montreal": "Montreal", "Monte Carlo": "Mônaco", "Catalunya": "Barcelona", "Spielberg": "Áustria",
    "Silverstone": "Silverstone", "Spa-Francorchamps": "Spa", "Hungaroring": "Hungria",
    "Zandvoort": "Zandvoort", "Monza": "Monza", "Madring": "Madri", "Baku": "Baku",
    "Kuala Lumpur": "Kuala Lumpur", "Singapore": "Singapura", "Austin": "Austin",
    "Mexico City": "Cidade do México", "Interlagos": "Interlagos", "Las Vegas": "Las Vegas",
    "Lusail": "Catar", "Yas Marina Circuit": "Abu Dhabi", "Sakhir": "Bahrein", "Jeddah": "Jeddah",
    "Imola": "Imola",
}
COM_ARTIGO = {  # para os títulos automáticos
    "Spielberg": "a Áustria", "Hungaroring": "a Hungria", "Lusail": "o Catar", "Monte Carlo": "Mônaco",
    "Mexico City": "a Cidade do México", "Singapore": "Singapura", "Sakhir": "o Bahrein",
}
DESTAQUE = "Interlagos"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                 "outubro", "novembro", "dezembro"]

# Textos dos gráficos
TITULO_RANKING = None  # None = o script sugere a partir do resultado
SUBTITULO_RANKING = (
    "Chance de chover durante as 2 horas de corrida, na data e no horário\n"
    "do GP de 2026, nos últimos 30 anos (1996 a 2025)"
)
TITULO_ANO = None
SUBTITULO_ANO = (
    "Chance de chover em Interlagos entre 14h e 16h, horário da corrida,\n"
    "em cada mês do ano (1996 a 2025)"
)
NOTA_RANKING = (
    "Dados: Open-Meteo (reanálise ERA5) e OpenF1. Chuva = pelo menos 0,5 mm nas 2 horas de corrida,\n"
    "contando a data do GP e 3 dias antes e depois, em cada ano. Bahrein e Jeddah foram canceladas em 2026."
)
NOTA_ANO = "Dados: Open-Meteo (reanálise ERA5). Chuva = pelo menos 0,5 mm entre 14h e 16h."
ASSINATURA = "Gráfico: João Vitor Barberino"

# Cores (identidade da terça)
COR_FUNDO = "#FFFFFF"
COR_TEXTO = "#111111"
COR_TEXTO_SUAVE = "#5C5C5C"
COR_BARRA = "#B3B3B3"
COR_LINHA = "#D6D6D6"
COR_DESTAQUE = "#C8102E"

# =============================================================================
# 2. UTILIDADES
# =============================================================================

_linhas_resumo: list[str] = []


def log(texto: str = "") -> None:
    print(texto)
    _linhas_resumo.append(texto)


def br(x: float, casas: int = 0) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ler_json(arquivo: Path):
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def salvar_json(arquivo: Path, dados) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = arquivo.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arquivo)


def deslocamento(gmt_offset: str) -> timedelta:
    """'-03:00:00' -> timedelta(hours=-3)"""
    sinal = -1 if gmt_offset.startswith("-") else 1
    h, m, *_ = (int(x) for x in gmt_offset.lstrip("+-").split(":"))
    return sinal * timedelta(hours=h, minutes=m)


# =============================================================================
# 3. COLETA (com cópia local)
# =============================================================================

_http = requests.Session()
_http.headers["User-Agent"] = "analise-chuva-f1/1.0 (projeto pessoal com dados publicos)"
_ultimo = {"openf1": 0.0, "clima": 0.0}


class LimiteDiario(Exception):
    pass


def pedir(url: str, params: dict, fonte: str):
    pausa = PAUSA_OPENF1 if fonte == "openf1" else PAUSA_CLIMA
    for tentativa in range(1, TENTATIVAS + 1):
        espera = pausa - (time.time() - _ultimo[fonte])
        if espera > 0:
            time.sleep(espera)
        _ultimo[fonte] = time.time()
        try:
            r = _http.get(url, params=params, timeout=90)
        except requests.RequestException as erro:
            print(f"      falha de conexão ({erro.__class__.__name__}); tentando de novo...")
            time.sleep(5 * tentativa)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None  # sem dados: não guarda cópia, para tentar de novo na próxima execução
        if r.status_code == 429 or r.status_code >= 500:
            texto = r.text.lower()
            if fonte == "clima" and ("daily" in texto or "hourly" in texto):
                raise LimiteDiario("A Open-Meteo avisou que o limite de pedidos acabou (da hora ou do dia).")
            t = min(120, 5 * 2 ** (tentativa - 1))
            print(f"      a API pediu uma pausa (HTTP {r.status_code}); esperando {t} s...")
            time.sleep(t)
            continue
        raise RuntimeError(f"HTTP {r.status_code} em {r.url}: {r.text[:200]}")
    raise RuntimeError(f"A API não respondeu depois de {TENTATIVAS} tentativas: {url} {params}")


def openf1(endpoint: str, params: dict, arquivo: Path, validade_horas: float | None = None):
    if arquivo.exists():
        idade = (time.time() - arquivo.stat().st_mtime) / 3600
        if validade_horas is None or idade < validade_horas:
            dados = ler_json(arquivo)
            if dados is not None:
                return dados
    dados = pedir(API_OPENF1 + endpoint, params, "openf1")
    if dados is None:
        return []
    salvar_json(arquivo, dados)
    return dados


def clima(pista: str, inicio: date, fim: date) -> dict:
    """Chuva por hora, sempre em UTC (mm na hora que termina no horário indicado).

    Tudo é feito em UTC de propósito: com timezone=auto a Open-Meteo usa o fuso de HOJE para
    o período inteiro e ignora o horário de verão, o que desloca a janela em 1 hora nas
    pistas da Europa e da América do Norte."""
    lat, lon = COORDENADAS[pista]
    arquivo = PASTA_DADOS / "clima" / pista.replace(" ", "_") / f"{inicio}_{fim}_UTC.json"
    dados = ler_json(arquivo) if arquivo.exists() else None
    if dados is None:
        dados = pedir(API_CLIMA, {
            "latitude": lat, "longitude": lon, "start_date": str(inicio), "end_date": str(fim),
            "hourly": "precipitation", "models": MODELO_CLIMA, "timezone": "GMT",
        }, "clima")
        if not dados:
            return {}
        if dados.get("utc_offset_seconds", 0) != 0:
            raise RuntimeError(f"A Open-Meteo não devolveu UTC para {pista} {inicio}.")
        salvar_json(arquivo, dados)
    horas = dados.get("hourly", {})
    return dict(zip(horas.get("time", []), horas.get("precipitation", [])))


def chuva_na_janela(chuva_por_hora: dict, inicio: datetime, horas: int = DURACAO_HORAS) -> float | None:
    """Soma a chuva entre 'inicio' e 'inicio + horas' (UTC). Cada valor da API é a chuva da hora
    anterior ao rótulo, então a janela 14h-16h usa os rótulos 15:00 e 16:00. Se a largada não
    for em hora cheia (ex.: 14h20), a primeira e a última hora entram proporcionalmente."""
    base = inicio.replace(minute=0, second=0, microsecond=0)
    frac = (inicio - base).total_seconds() / 3600
    pesos = [1 - frac] + [1.0] * (horas - 1) + ([frac] if frac > 0 else [])
    total = 0.0
    for i, peso in enumerate(pesos, start=1):
        rotulo = (base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00")
        valor = chuva_por_hora.get(rotulo)
        if valor is None:
            return None
        total += peso * valor
    return round(total, 2)


def calendario(ano: int) -> list[dict]:
    validade = 12 if ano >= datetime.now().year else None
    sessoes = openf1("sessions", {"year": ano, "session_name": "Race"},
                     PASTA_DADOS / "openf1" / f"sessoes_{ano}.json", validade)
    corridas = []
    for s in sessoes:
        if s.get("session_name") != "Race" or s.get("is_cancelled"):
            continue
        inicio_utc = datetime.fromisoformat(s["date_start"].replace("Z", "+00:00")).astimezone(timezone.utc)
        inicio_local = (inicio_utc + deslocamento(s.get("gmt_offset", "00:00:00"))).replace(tzinfo=None)
        corridas.append({
            "session_key": s["session_key"], "pista": s["circuit_short_name"], "ano": ano,
            "inicio_utc": inicio_utc.replace(tzinfo=None), "inicio_local": inicio_local,
        })
    corridas.sort(key=lambda c: c["inicio_utc"])
    return corridas


def coletar_climatologia(corridas: list[dict]) -> pd.DataFrame:
    linhas = []
    total = len(corridas) * len(ANOS_CLIMA)
    feito = 0
    for c in corridas:
        if c["pista"] not in COORDENADAS:
            print(f"  AVISO: sem coordenadas para {c['pista']}; corrida ignorada.")
            continue
        # Data e hora da largada de 2026 em UTC, repetidas em cada ano do histórico
        u = c["inicio_utc"]
        for ano in ANOS_CLIMA:
            base = date(ano, u.month, u.day)
            serie = clima(c["pista"], base - timedelta(days=DIAS_ANTES_DEPOIS),
                          base + timedelta(days=DIAS_ANTES_DEPOIS + 1))
            for k in range(-DIAS_ANTES_DEPOIS, DIAS_ANTES_DEPOIS + 1):
                dia = base + timedelta(days=k)
                inicio = datetime(dia.year, dia.month, dia.day, u.hour, u.minute)
                linhas.append({"pista": c["pista"], "ano": ano, "desvio_dias": k,
                               "chuva_mm": chuva_na_janela(serie, inicio)})
            feito += 1
            if feito % 30 == 0:
                print(f"  clima: {feito}/{total} pedidos ({NOMES.get(c['pista'], c['pista'])})")
    return pd.DataFrame(linhas)


def coletar_validacao() -> pd.DataFrame:
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=ATRASO_ERA5_DIAS)
    linhas = []
    for ano in ANOS_VALIDACAO:
        for c in calendario(ano):
            if c["inicio_utc"] > limite or c["pista"] not in COORDENADAS:
                continue
            pasta = PASTA_DADOS / "openf1" / str(ano)
            stints = openf1("stints", {"session_key": c["session_key"]}, pasta / f"{c['session_key']}_stints.json")
            molhadas = total = 0
            for st in stints:
                if st.get("lap_start") is None:  # stint sem volta registrada: conta como 1 volta
                    st = {**st, "lap_start": st.get("lap_end") or 1, "lap_end": st.get("lap_end") or 1}
                n = (st.get("lap_end") or st["lap_start"]) - st["lap_start"] + 1
                total += n
                if st.get("compound") in ("INTERMEDIATE", "WET"):
                    molhadas += n
            pct = round(100 * molhadas / total, 1) if total else np.nan
            chave = (ano, c["pista"])
            if chave in CORRECOES_PNEU:
                pct = CORRECOES_PNEU[chave]
            # Largada real = início da volta 1 (a programada pode atrasar, como em Spa 2025)
            voltas = openf1("laps", {"session_key": c["session_key"], "lap_number": 1},
                            pasta / f"{c['session_key']}_volta1.json")
            inicios = [v["date_start"] for v in voltas if v.get("date_start")]
            inicio = c["inicio_utc"]
            if inicios:
                inicio = datetime.fromisoformat(min(inicios).replace("Z", "+00:00")) \
                    .astimezone(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
            dia = inicio.date()
            serie = clima(c["pista"], dia, dia + timedelta(days=1))
            linhas.append({
                "ano": ano, "pista": c["pista"],
                "largada_programada_utc": c["inicio_utc"].strftime("%Y-%m-%d %H:%M"),
                "largada_real_utc": inicio.strftime("%Y-%m-%d %H:%M"),
                "pct_voltas_pneu_chuva": pct,
                "chuva_mm": chuva_na_janela(serie, inicio),
            })
            print(f"  validação: {ano} {NOMES.get(c['pista'], c['pista'])}")
    return pd.DataFrame(linhas)


def coletar_interlagos_ano(hora_utc: int) -> pd.DataFrame:
    """Todos os dias de cada ano em Interlagos, na hora da largada (em UTC; 14h em Brasília = 17h UTC)."""
    linhas = []
    for ano in ANOS_CLIMA:
        serie = clima(DESTAQUE, date(ano, 1, 1), date(ano + 1, 1, 1))
        dia = date(ano, 1, 1)
        while dia.year == ano:
            inicio = datetime(dia.year, dia.month, dia.day, hora_utc)
            linhas.append({"data": dia.isoformat(), "chuva_mm": chuva_na_janela(serie, inicio)})
            dia += timedelta(days=1)
        print(f"  Interlagos ano a ano: {ano}")
    return pd.DataFrame(linhas)


# =============================================================================
# 4. ANÁLISE
# =============================================================================

def chance_por_pista(janelas: pd.DataFrame, limiar: float = LIMIAR_MM) -> pd.DataFrame:
    j = janelas.dropna(subset=["chuva_mm"]).assign(choveu=lambda d: d["chuva_mm"] >= limiar)
    tab = j.groupby("pista").agg(chance=("choveu", "mean"), amostras=("choveu", "size"),
                                 chuva_media_mm=("chuva_mm", "mean")).reset_index()
    exato = j[j["desvio_dias"] == 0].groupby("pista")["choveu"].sum().rename("anos_com_chuva_no_dia")
    tab = tab.merge(exato, on="pista", how="left")
    return tab.sort_values(["chance", "pista"], ascending=[False, True], kind="stable").reset_index(drop=True)


def medias_sorteadas(janelas: pd.DataFrame, rng) -> tuple[pd.Index, np.ndarray]:
    """Bootstrap por ano: sorteia anos inteiros (os 7 dias de um ano andam juntos) e devolve a
    chance média de cada pista em cada sorteio. Os MESMOS anos valem para todas as pistas."""
    j = janelas.dropna(subset=["chuva_mm"]).assign(choveu=lambda d: d["chuva_mm"] >= LIMIAR_MM)
    por_ano = j.groupby(["pista", "ano"])["choveu"].mean().unstack("ano")
    anos = por_ano.columns.to_numpy()
    sorteios = rng.choice(len(anos), size=(REPETICOES_BOOTSTRAP, len(anos)), replace=True)
    medias = np.nanmean(por_ano.to_numpy()[:, sorteios], axis=2)  # (pistas, repetições)
    return por_ano.index, np.round(medias, 12)


def intervalo_por_anos(pistas: pd.Index, medias: np.ndarray) -> pd.DataFrame:
    """Intervalo de 95% de cada pista e chance de ficar em 1º / entre as 3 primeiras.
    Empates dividem o 1º lugar; no top 3, empatar com a 3ª conta como estar no top 3."""
    lider = medias == medias.max(axis=0)
    prob_primeira = (lider / lider.sum(axis=0)).mean(axis=1)
    posicao_min = 1 + (medias[None, :, :] > medias[:, None, :]).sum(axis=1)
    return pd.DataFrame({
        "pista": pistas,
        "ic_baixo": np.percentile(medias, 2.5, axis=1),
        "ic_alto": np.percentile(medias, 97.5, axis=1),
        "prob_primeira": prob_primeira,
        "prob_top3": (posicao_min <= 3).mean(axis=1),
    })


def diferencas_pareadas(janelas: pd.DataFrame, pistas: pd.Index, medias: np.ndarray,
                        outras: list[str]) -> pd.DataFrame:
    """Diferença (pontos percentuais) e razão entre Interlagos e outras pistas, com intervalo de
    95% calculado nos mesmos sorteios de anos (forma correta de comparar duas pistas)."""
    base = chance_por_pista(janelas).set_index("pista")["chance"]
    i = list(pistas).index(DESTAQUE)
    linhas = []
    for p in outras:
        if p not in pistas:
            continue
        k = list(pistas).index(p)
        dif = medias[i] - medias[k]
        with np.errstate(divide="ignore", invalid="ignore"):
            razao = medias[i] / medias[k]
        linhas.append({
            "pista": p, "diferenca_pp": 100 * (base[DESTAQUE] - base[p]),
            "dif_ic_baixo": 100 * np.percentile(dif, 2.5), "dif_ic_alto": 100 * np.percentile(dif, 97.5),
            "prob_interlagos_maior": float((dif > 0).mean()),
            "razao": base[DESTAQUE] / base[p] if base[p] else np.nan,
            "razao_ic_baixo": np.nanpercentile(razao, 2.5), "razao_ic_alto": np.nanpercentile(razao, 97.5),
        })
    return pd.DataFrame(linhas)


def resumo_validacao(val: pd.DataFrame, limiar: float = LIMIAR_MM) -> dict:
    v = val.dropna(subset=["chuva_mm", "pct_voltas_pneu_chuva"])
    molhada = v["pct_voltas_pneu_chuva"] >= LIMIAR_PNEU_CHUVA
    alarme = v["chuva_mm"] >= limiar
    return {
        "molhadas": int(molhada.sum()), "acertos": int((molhada & alarme).sum()),
        "secas": int((~molhada).sum()), "alarmes_falsos": int((~molhada & alarme).sum()),
        "lista_molhadas": v[molhada], "lista_falsos": v[~molhada & alarme],
    }


# =============================================================================
# 5. GRÁFICOS
# =============================================================================

def preparar_fontes() -> None:
    arquivos = sorted(PASTA_FONTES.glob("*.ttf"))
    if not arquivos:
        print("AVISO: fonte IBM Plex Sans Condensed não encontrada em fontes/; usando a fonte padrão.")
        return
    for a in arquivos:
        font_manager.fontManager.addfont(str(a))
    plt.rcParams["font.family"] = "IBM Plex Sans Condensed"


def sugerir_titulo_ranking(tab: pd.DataFrame) -> str:
    posicao = int(tab.index[tab["pista"] == DESTAQUE][0]) + 1
    if posicao == 1:
        if tab.iloc[0]["prob_primeira"] >= 0.9:
            return "Nenhuma corrida da F1 tem tanta\nchance de chuva quanto Interlagos"
        segunda = COM_ARTIGO.get(tab.iloc[1]["pista"], NOMES.get(tab.iloc[1]["pista"], tab.iloc[1]["pista"]))
        return f"Interlagos tem a maior chance de chuva\nda F1, mas {segunda} vem logo atrás"
    primeira = NOMES.get(tab.iloc[0]["pista"], tab.iloc[0]["pista"])
    if posicao == 2 and tab.iloc[0]["prob_primeira"] < 0.9:
        return f"{primeira} e Interlagos empatam\nno topo da chuva na F1"
    if posicao <= 3:
        return f"Interlagos tem fama de chuva,\nmas {primeira} chove mais"
    return f"Interlagos tem fama de chuva,\nmas é só a {posicao}ª do calendário"


def cabecalho(fig, titulo: str, subtitulo: str) -> None:
    fig.text(0.07, 0.955, titulo, fontsize=38, fontweight="bold", color=COR_TEXTO, va="top", linespacing=1.12)
    fig.text(0.07, 0.83, subtitulo, fontsize=17.5, color=COR_TEXTO_SUAVE, va="top", linespacing=1.4)


def rodape(fig, nota: str) -> None:
    fig.text(0.07, 0.052, nota, fontsize=12.5, color=COR_TEXTO_SUAVE, va="bottom", linespacing=1.4)
    fig.text(0.07, 0.022, ASSINATURA, fontsize=13, color=COR_TEXTO_SUAVE, va="bottom")


def grafico_ranking(tab: pd.DataFrame, titulo: str) -> None:
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=COR_FUNDO)
    cabecalho(fig, titulo, SUBTITULO_RANKING)
    ax = fig.add_axes([0.27, 0.11, 0.62, 0.66])
    n = len(tab)
    maior = tab["chance"].max()
    for i, r in tab.iterrows():
        y = n - 1 - i
        destaque = r["pista"] == DESTAQUE
        cor = COR_DESTAQUE if destaque else COR_BARRA
        ax.barh(y, r["chance"], height=0.68, color=cor)
        ax.text(r["chance"] + maior * 0.015, y, f"{br(r['chance'] * 100)}%", va="center", ha="left",
                fontsize=15.5 if not destaque else 17, color=COR_DESTAQUE if destaque else COR_TEXTO_SUAVE,
                fontweight="bold" if destaque else "normal")
        ax.text(-maior * 0.03, y, NOMES.get(r["pista"], r["pista"]), va="center", ha="right",
                fontsize=15.5 if not destaque else 17, color=COR_DESTAQUE if destaque else COR_TEXTO,
                fontweight="bold" if destaque else "normal")
    ax.set_xlim(0, maior * 1.15)
    ax.set_ylim(-0.6, n - 0.4)
    ax.axis("off")
    rodape(fig, NOTA_RANKING)
    fig.savefig(ARQUIVO_RANKING_PNG, dpi=100, facecolor=COR_FUNDO)
    plt.close(fig)


def grafico_ano(por_mes: pd.Series, mes_gp: int, titulo: str) -> None:
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=COR_FUNDO)
    cabecalho(fig, titulo, SUBTITULO_ANO)
    ax = fig.add_axes([0.07, 0.14, 0.86, 0.58])
    maior = por_mes.max()
    for m in range(1, 13):
        destaque = m == mes_gp
        ax.bar(m, por_mes[m], width=0.72, color=COR_DESTAQUE if destaque else COR_BARRA)
        ax.text(m, por_mes[m] + maior * 0.015, f"{br(por_mes[m] * 100)}%", ha="center", va="bottom",
                fontsize=15 if not destaque else 17, color=COR_DESTAQUE if destaque else COR_TEXTO_SUAVE,
                fontweight="bold" if destaque else "normal")
        ax.text(m, -maior * 0.04, MESES[m - 1], ha="center", va="top", fontsize=16,
                color=COR_DESTAQUE if destaque else COR_TEXTO, fontweight="bold" if destaque else "normal")
    ax.set_xlim(0.4, 12.6)
    ax.set_ylim(0, maior * 1.12)
    ax.axis("off")
    rodape(fig, NOTA_ANO)
    fig.savefig(ARQUIVO_ANO_PNG, dpi=100, facecolor=COR_FUNDO)
    plt.close(fig)


# =============================================================================
# 6. EXECUÇÃO
# =============================================================================

def main() -> None:
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEMENTE)
    arq_janelas = PASTA_RESULTADOS / "janelas.csv"
    arq_val = PASTA_RESULTADOS / "validacao.csv"
    arq_ano = PASTA_RESULTADOS / "interlagos_dias.csv"
    arq_cal = PASTA_RESULTADOS / "calendario.csv"

    log("=" * 72)
    log("INTERLAGOS É A CORRIDA COM MAIS CHANCE DE CHUVA DA F1?")
    log("=" * 72)

    so_analise = "--so-analise" in sys.argv
    if so_analise:
        faltando = [a.name for a in (arq_janelas, arq_val, arq_ano, arq_cal) if not a.exists()]
        if faltando:
            sys.exit(f"Faltam arquivos em resultados/: {', '.join(faltando)}. "
                     "Rode primeiro sem --so-analise para baixar os dados.")
        log("(usando os arquivos já salvos em resultados/, sem baixar nada)")
        janelas, val, dias = pd.read_csv(arq_janelas), pd.read_csv(arq_val), pd.read_csv(arq_ano)
        cal = pd.read_csv(arq_cal)
    else:
        try:
            corridas = calendario(ANO_CALENDARIO)
            cal = pd.DataFrame([{"pista": c["pista"], "inicio_local": c["inicio_local"].strftime("%Y-%m-%d %H:%M"),
                                 "inicio_utc": c["inicio_utc"].strftime("%Y-%m-%d %H:%M")} for c in corridas])
            cal.to_csv(arq_cal, index=False)
            print(f"\nCalendário {ANO_CALENDARIO}: {len(corridas)} corridas (sem as canceladas)")
            print("\n1/3 Validação: o ERA5 enxerga a chuva das corridas de verdade?")
            val = coletar_validacao()
            val.to_csv(arq_val, index=False)
            print(f"\n2/3 Clima na data e hora de cada GP, {ANOS_CLIMA[0]} a {ANOS_CLIMA[-1]}")
            janelas = coletar_climatologia(corridas)
            janelas.to_csv(arq_janelas, index=False)
            hora_interlagos = next(c["inicio_utc"].hour for c in corridas if c["pista"] == DESTAQUE)
            print("\n3/3 Interlagos em todos os dias do ano")
            dias = coletar_interlagos_ano(hora_interlagos)
            dias.to_csv(arq_ano, index=False)
        except LimiteDiario as aviso:
            print(f"\n{aviso} O que já foi baixado está salvo em dados/. Rode de novo amanhã para continuar.")
            return

    # ---- validação
    v = resumo_validacao(val)
    log()
    log(f"VALIDAÇÃO: O ERA5 ENXERGA A CHUVA DAS CORRIDAS? ({ANOS_VALIDACAO[0]} em diante)")
    log(f"  Corridas com pneu de chuva ({LIMIAR_PNEU_CHUVA}%+ das voltas): {v['molhadas']}. "
        f"O ERA5 marcou chuva em {v['acertos']}.")
    for r in v["lista_molhadas"].itertuples():
        log(f"    {r.ano} {NOMES.get(r.pista, r.pista):<17} {br(r.pct_voltas_pneu_chuva)}% das voltas com pneu de chuva"
            f"   ERA5: {br(r.chuva_mm, 1)} mm")
    log(f"  Corridas secas: {v['secas']}. O ERA5 marcou chuva (alarme falso) em {v['alarmes_falsos']}.")
    for r in v["lista_falsos"].itertuples():
        log(f"    {r.ano} {NOMES.get(r.pista, r.pista):<17} ERA5: {br(r.chuva_mm, 1)} mm")

    # ---- conferência: cada pista precisa ter 30 anos x 7 dias de janelas válidas
    amostras = janelas.dropna(subset=["chuva_mm"]).groupby("pista").size()
    esperado = len(ANOS_CLIMA) * (2 * DIAS_ANTES_DEPOIS + 1)
    incompletas = amostras[amostras != esperado]
    if len(incompletas):
        log(f"  AVISO: pistas com janelas faltando (esperado {esperado}): "
            + ", ".join(f"{NOMES.get(p, p)} {n}" for p, n in incompletas.items()))

    # ---- ranking
    pistas, medias = medias_sorteadas(janelas, rng)
    tab = chance_por_pista(janelas).merge(intervalo_por_anos(pistas, medias), on="pista")
    tab.to_csv(PASTA_RESULTADOS / "ranking.csv", index=False)
    comparar = [p for p in tab["pista"].head(6) if p != DESTAQUE] + \
               [p for p in ("Silverstone", "Spa-Francorchamps") if p not in set(tab["pista"].head(6))]
    dif = diferencas_pareadas(janelas, pistas, medias, comparar)
    dif.to_csv(PASTA_RESULTADOS / "diferencas_interlagos.csv", index=False)
    inicio = dict(zip(cal["pista"], cal["inicio_local"]))
    log()
    log(f"CHANCE DE CHUVA NA HORA DA CORRIDA (data e horário de {ANO_CALENDARIO}, {ANOS_CLIMA[0]} a {ANOS_CLIMA[-1]})")
    log(f"  {'pista':<17} {'largada local':<17} {'chance':>7}   {'IC 95%':>13}   {'dia exato':>9}   {'1º lugar':>8}")
    for i, r in tab.iterrows():
        log(f"  {NOMES.get(r.pista, r.pista):<17} {inicio.get(r.pista, '')[5:]:<17} {br(r.chance * 100):>6}%"
            f"   {br(r.ic_baixo * 100):>4}% a {br(r.ic_alto * 100):>3}%   {int(r.anos_com_chuva_no_dia):>3} de 30"
            f"   {br(r.prob_primeira * 100):>6}%")
    posicao = int(tab.index[tab["pista"] == DESTAQUE][0]) + 1
    li = tab[tab["pista"] == DESTAQUE].iloc[0]
    log()
    log(f"  Interlagos: {posicao}º lugar, {br(li.chance * 100)}% (de {br(li.ic_baixo * 100)}% a {br(li.ic_alto * 100)}%)."
        f" Primeiro lugar em {br(li.prob_primeira * 100)}% e entre os 3 primeiros em {br(li.prob_top3 * 100)}%"
        f" dos sorteios de anos.")
    log()
    log("  Interlagos contra as outras (mesmos sorteios de anos, intervalo de 95%)")
    for r in dif.itertuples():
        sinal = "+" if round(r.diferenca_pp) >= 0 else "-"
        log(f"    {NOMES.get(r.pista, r.pista):<17} diferença {sinal}{br(abs(r.diferenca_pp))} pp"
            f" (de {br(r.dif_ic_baixo)} a {br(r.dif_ic_alto)} pp);"
            f" {br(r.razao, 2)} vezes (de {br(r.razao_ic_baixo, 2)} a {br(r.razao_ic_alto, 2)});"
            f" Interlagos maior em {br(r.prob_interlagos_maior * 100)}% dos sorteios")

    log()
    log("  O resultado muda com o critério de chuva?")
    for limiar in LIMIARES_TESTE:
        t = chance_por_pista(janelas, limiar)
        pos = int(t.index[t["pista"] == DESTAQUE][0]) + 1
        top = ", ".join(f"{NOMES.get(p, p)} {br(c * 100)}%" for p, c in zip(t["pista"][:3], t["chance"][:3]))
        log(f"    {br(limiar, 1)} mm: Interlagos em {pos}º ({br(t.loc[pos - 1, 'chance'] * 100)}%). Top 3: {top}")

    # ---- Interlagos no ano
    d = dias.dropna(subset=["chuva_mm"]).assign(mes=lambda x: pd.to_datetime(x["data"]).dt.month,
                                                choveu=lambda x: x["chuva_mm"] >= LIMIAR_MM)
    por_mes = d.groupby("mes")["choveu"].mean()
    mes_gp = int(pd.to_datetime(inicio[DESTAQUE]).month)
    log()
    log("INTERLAGOS EM CADA MÊS (chance de chuva no horário da corrida)")
    log("  " + "  ".join(f"{MESES[m - 1]} {br(por_mes[m] * 100)}%" for m in range(1, 13)))
    log(f"  Mês do GP ({MESES[mes_gp - 1]}): {br(por_mes[mes_gp] * 100)}%. "
        f"Mais chuvoso: {MESES[por_mes.idxmax() - 1]} ({br(por_mes.max() * 100)}%). "
        f"Mais seco: {MESES[por_mes.idxmin() - 1]} ({br(por_mes.min() * 100)}%).")

    # ---- gráficos
    preparar_fontes()
    titulo = TITULO_RANKING or sugerir_titulo_ranking(tab)
    grafico_ranking(tab, titulo)
    mes_max = int(por_mes.idxmax())
    titulo_ano = TITULO_ANO or (
        f"Chove em {br(por_mes[mes_gp] * 100)}% das tardes de {MESES_EXTENSO[mes_gp - 1]}\n"
        f"em Interlagos. Em {MESES_EXTENSO[mes_max - 1]}, em {br(por_mes[mes_max] * 100)}%"
    )
    grafico_ano(por_mes, mes_gp, titulo_ano)
    log()
    log("GRÁFICOS")
    log(f"  {ARQUIVO_RANKING_PNG.name} (principal) e {ARQUIVO_ANO_PNG.name} (apoio)")
    log(f"  Título sugerido: {titulo.replace(chr(10), ' ')}")

    (PASTA_RESULTADOS / "resumo.txt").write_text("\n".join(_linhas_resumo), encoding="utf-8")
    print(f"\nResumo salvo em {PASTA_RESULTADOS / 'resumo.txt'}")


if __name__ == "__main__":
    main()
